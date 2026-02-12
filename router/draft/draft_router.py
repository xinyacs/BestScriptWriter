import asyncio
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
import uuid
import io

from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select, update, desc
from sqlalchemy.ext.asyncio import AsyncSession

from core.dependences import get_db
from core import settings
from database.base import AsyncSessionLocal
from database.models import ScriptTask, TaskRun, TaskProgressEvent
from util.files_util import save_image, file_to_text
from agent.l1_workflow import l1_script_infer
from agent.l2_workflow import l2_script_infer
from schema.base import L1VideoScript, ProgressEvent
from core.compass import CompassSelection
from agent.compass_agent import CompassChoicesAgent
from util.xlsx_export import export_l2_sections_to_xlsx_bytes

router = APIRouter(tags=["Draft"])


# Request model for setting task parameters
class TaskParamsRequest(BaseModel):
    platformFormat: str
    outputLang: str
    durationSec: int
    tone: str
    audience: str
    style: List[str]
    additionalInstructions: Optional[str] = None


class TaskCompassRequest(BaseModel):
    director: Optional[str] = None
    style: Optional[List[str]] = None


@router.post("/create_draft")
async def create_draft(
    # 直接传文本
    text: Optional[str] = Form(None),
    # 传文档文件（会转成字符串）
    doc: Optional[UploadFile] = File(None),
    # 传图片文件（多图）
    images: Optional[List[UploadFile]] = File(None),
    db: AsyncSession = Depends(get_db),

):
    """
        Step1：输入内容（text/doc/image）-> 存 SQLite -> 返回 task_id
    """
    if (text is None or not text.strip()) and doc is None:
        raise HTTPException(status_code=422, detail="至少提供 text / doc 之一（用于生成输入文本），images 可选")

    max_images = getattr(settings, "FILE_MAX_IMAGES", 6)
    if images and len(images) > max_images:
        raise HTTPException(status_code=413, detail=f"图片数量过多：{len(images)}，限制 {max_images}")

    final_text = text or ""
    if doc is not None:
        doc_text = await file_to_text(doc)
        final_text = final_text + (("\n\n" if final_text else "") + doc_text)

    image_paths = []
    if images:
        for img in images:
            image_paths.append(await save_image(img))

    task = ScriptTask(
        input_text=final_text or None,
        image_paths=image_paths or None,
        status="CREATED",
    )
    db.add(task)
    await db.commit()
    await db.refresh(task)

    return {
        "task_id": task.id,
        "status": task.status,
        "has_text": bool(task.input_text),
        "has_image": bool(task.image_paths),
        "image_count": len(task.image_paths or []),
    }


@router.get("/task/{task_id}")
async def get_task(task_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(ScriptTask).where(ScriptTask.id == task_id))
    task = result.scalar_one_or_none()
    if task is None:
        raise HTTPException(status_code=404, detail=f"task_id 不存在: {task_id}")

    l1_run = (
        await db.execute(
            select(TaskRun)
            .where(TaskRun.task_id == task_id, TaskRun.phase == "l1")
            .order_by(desc(TaskRun.created_at))
            .limit(1)
        )
    ).scalar_one_or_none()

    l2_run = (
        await db.execute(
            select(TaskRun)
            .where(TaskRun.task_id == task_id, TaskRun.phase == "l2")
            .order_by(desc(TaskRun.created_at))
            .limit(1)
        )
    ).scalar_one_or_none()

    return {
        "task_id": task.id,
        "input_text": task.input_text,
        "image_paths": task.image_paths,
        "params": task.params,
        "compass": task.compass,
        "status": task.status,
        "l1": None
        if l1_run is None
        else {
            "run_id": l1_run.id,
            "status": l1_run.status,
            "result": l1_run.result_json,
            "error_message": l1_run.error_message,
            "created_at": l1_run.created_at.isoformat() if l1_run.created_at else None,
            "updated_at": l1_run.updated_at.isoformat() if l1_run.updated_at else None,
        },
        "l2": None
        if l2_run is None
        else {
            "run_id": l2_run.id,
            "status": l2_run.status,
            "result": l2_run.result_json,
            "error_message": l2_run.error_message,
            "created_at": l2_run.created_at.isoformat() if l2_run.created_at else None,
            "updated_at": l2_run.updated_at.isoformat() if l2_run.updated_at else None,
        },
        "created_at": task.created_at.isoformat() if task.created_at else None,
        "updated_at": task.updated_at.isoformat() if task.updated_at else None,
    }


@router.get("/task/{task_id}/export_xlsx")
async def export_task_xlsx(task_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(ScriptTask).where(ScriptTask.id == task_id))
    task = result.scalar_one_or_none()
    if task is None:
        raise HTTPException(status_code=404, detail=f"task_id 不存在: {task_id}")

    l1_run = (
        await db.execute(
            select(TaskRun)
            .where(TaskRun.task_id == task_id, TaskRun.phase == "l1")
            .order_by(desc(TaskRun.created_at))
            .limit(1)
        )
    ).scalar_one_or_none()

    l2_run = (
        await db.execute(
            select(TaskRun)
            .where(TaskRun.task_id == task_id, TaskRun.phase == "l2")
            .order_by(desc(TaskRun.created_at))
            .limit(1)
        )
    ).scalar_one_or_none()

    sections = []
    if l2_run is not None and isinstance(l2_run.result_json, list):
        sections = list(l2_run.result_json or [])

    script_title = None
    if l1_run is not None and isinstance(l1_run.result_json, dict):
        script_title = l1_run.result_json.get("title")
    if not script_title:
        script_title = f"视频脚本（task={task_id}）"

    try:
        data = export_l2_sections_to_xlsx_bytes(
            sections=sections,
            title=str(script_title),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=repr(e))

    buf = io.BytesIO(data)
    buf.seek(0)

    filename = f"task_{task_id}.xlsx"
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.post("/task/{task_id}/compass")
async def set_task_compass(task_id: str, compass: TaskCompassRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(ScriptTask).where(ScriptTask.id == task_id))
    task = result.scalar_one_or_none()
    if task is None:
        raise HTTPException(status_code=404, detail=f"task_id 不存在: {task_id}")

    payload = {"director": compass.director, "style": compass.style}
    await db.execute(
        update(ScriptTask)
        .where(ScriptTask.id == task_id)
        .values(compass=payload)
    )
    await db.commit()

    run = TaskRun(
        task_id=task_id,
        phase="compass",
        status="DONE",
        parent_run_id=None,
        params_snapshot=task.params,
        compass_snapshot=payload,
        result_json=payload,
        error_message=None,
    )
    db.add(run)
    await db.commit()
    await db.refresh(run)

    await _append_progress_event(task_id, run.id, ProgressEvent(phase="compass", type="bound", data=payload))

    result = await db.execute(select(ScriptTask).where(ScriptTask.id == task_id))
    updated_task = result.scalar_one()
    return {
        "task_id": updated_task.id,
        "compass": updated_task.compass,
        "status": updated_task.status,
        "updated_at": updated_task.updated_at.isoformat() if updated_task.updated_at else None,
    }


@router.get("/task/{task_id}/progress")
async def get_task_progress(
    task_id: str,
    run_id: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(ScriptTask).where(ScriptTask.id == task_id))
    task = result.scalar_one_or_none()
    if task is None:
        raise HTTPException(status_code=404, detail=f"task_id 不存在: {task_id}")

    if run_id is None:
        latest = (
            await db.execute(
                select(TaskRun)
                .where(TaskRun.task_id == task_id)
                .order_by(desc(TaskRun.created_at))
                .limit(1)
            )
        ).scalar_one_or_none()
        run_id = latest.id if latest else None

    run = None
    if run_id is not None:
        run = (await db.execute(select(TaskRun).where(TaskRun.id == run_id))).scalar_one_or_none()

    if run_id is None or run is None:
        return {
            "task_id": task.id,
            "run_id": None,
            "task_status": task.status,
            "run_status": None,
            "phase": None,
            "error_message": None,
            "event": None,
        }

    latest_evt = (
        await db.execute(
            select(TaskProgressEvent)
            .where(
                TaskProgressEvent.task_id == task_id,
                TaskProgressEvent.run_id == run_id,
            )
            .order_by(TaskProgressEvent.id.desc())
            .limit(1)
        )
    ).scalar_one_or_none()

    event = None
    if latest_evt is not None:
        event = {
            "id": latest_evt.id,
            "ts": latest_evt.ts.isoformat() if latest_evt.ts else None,
            "phase": latest_evt.phase,
            "type": latest_evt.type,
            "data": latest_evt.data or {},
        }

    return {
        "task_id": task.id,
        "run_id": run.id,
        "task_status": task.status,
        "run_status": run.status,
        "phase": run.phase,
        "error_message": run.error_message,
        "event": event,
    }


@router.post("/task/{task_id}/params")
async def set_task_params(
    task_id: str,
    params: TaskParamsRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Step2：为指定任务设置参数（平台格式、输出语言、时长、风格等）
    """
    # 检查任务是否存在
    result = await db.execute(select(ScriptTask).where(ScriptTask.id == task_id))
    task = result.scalar_one_or_none()
    if task is None:
        raise HTTPException(status_code=404, detail=f"task_id 不存在: {task_id}")
    
    # 更新任务参数和状态
    params_dict = params.model_dump()
    await db.execute(
        update(ScriptTask)
        .where(ScriptTask.id == task_id)
        .values(
            params=params_dict,
            status="PARAMS_READY"
        )
    )
    await db.commit()
    
    # 重新获取更新后的任务
    result = await db.execute(select(ScriptTask).where(ScriptTask.id == task_id))
    updated_task = result.scalar_one()
    
    return {
        "task_id": updated_task.id,
        "status": updated_task.status,
        "params": updated_task.params,
        "updated_at": updated_task.updated_at.isoformat() if updated_task.updated_at else None,
    }


async def _append_progress_event(task_id: str, run_id: str, evt: ProgressEvent) -> None:
    async with AsyncSessionLocal() as session:
        row = TaskProgressEvent(
            task_id=task_id,
            run_id=run_id,
            ts=datetime.now(timezone.utc),
            phase=evt.phase,
            type=evt.type,
            data=evt.data,
        )
        session.add(row)
        await session.commit()


async def _ensure_task_compass(task_id: str) -> CompassSelection | None:
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(ScriptTask).where(ScriptTask.id == task_id))
        task = result.scalar_one_or_none()
        if task is None:
            return None

        if task.compass:
            try:
                return CompassSelection(
                    director=(task.compass or {}).get("director"),
                    style=(task.compass or {}).get("style"),
                )
            except Exception:
                return None

        inferred = await CompassChoicesAgent().infer_compass(content=task.input_text or "")
        task.compass = {"director": inferred.director, "style": inferred.style}
        await session.commit()

    # compass 推断事件是审计信息；写入到“最新 run”的 progress 里由调用方负责
    return inferred


@router.post("/task/{task_id}/run_l1")
async def run_l1(task_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(ScriptTask).where(ScriptTask.id == task_id))
    task = result.scalar_one_or_none()
    if task is None:
        raise HTTPException(status_code=404, detail=f"task_id 不存在: {task_id}")

    if task.status == "L1_RUNNING":
        return {"task_id": task.id, "status": task.status}

    if not task.params:
        raise HTTPException(status_code=422, detail="请先设置 params，再启动 L1")

    run = TaskRun(
        task_id=task_id,
        phase="l1",
        status="RUNNING",
        parent_run_id=None,
        params_snapshot=task.params,
        compass_snapshot=task.compass,
        result_json=None,
        error_message=None,
    )
    db.add(run)
    await db.execute(update(ScriptTask).where(ScriptTask.id == task_id).values(status="L1_RUNNING"))
    await db.commit()
    await db.refresh(run)

    async def _job() -> None:
        try:
            async with AsyncSessionLocal() as session:
                result = await session.execute(select(ScriptTask).where(ScriptTask.id == task_id))
                t = result.scalar_one_or_none()
                if t is None:
                    return
                params = t.params or {}
                content = t.input_text or ""
                images = list(t.image_paths) if t.image_paths else None

            compass = await _ensure_task_compass(task_id)

            def _on_progress(e: ProgressEvent) -> None:
                asyncio.create_task(_append_progress_event(task_id, run.id, e))

            script = await l1_script_infer(
                content=content,
                max_duration=int(params.get("durationSec") or 60),
                target_audience=str(params.get("audience") or "general"),
                platform=str(params.get("platformFormat") or "抖音"),
                language=str(params.get("outputLang") or "中文"),
                images=images,
                compass=compass,
                on_progress=_on_progress,
                show_progress=False,
                include_stage_result=False,
            )

            async with AsyncSessionLocal() as session:
                await session.execute(update(ScriptTask).where(ScriptTask.id == task_id).values(status="L1_DONE"))

                dumped = script.model_dump()
                body = list(dumped.get("body") or [])
                for it in body:
                    if isinstance(it, dict) and not it.get("item_id"):
                        it["item_id"] = uuid.uuid4().hex
                dumped["body"] = body

                await session.execute(
                    update(TaskRun)
                    .where(TaskRun.id == run.id)
                    .values(status="DONE", result_json=dumped, error_message=None)
                )
                await session.commit()
        except Exception as e:
            async with AsyncSessionLocal() as session:
                await session.execute(update(ScriptTask).where(ScriptTask.id == task_id).values(status="ERROR"))
                await session.execute(
                    update(TaskRun)
                    .where(TaskRun.id == run.id)
                    .values(status="ERROR", error_message=repr(e))
                )
                await session.commit()

    asyncio.create_task(_job())
    return {"task_id": task.id, "run_id": run.id, "status": "L1_RUNNING"}


@router.post("/task/{task_id}/run_l2")
async def run_l2(task_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(ScriptTask).where(ScriptTask.id == task_id))
    task = result.scalar_one_or_none()
    if task is None:
        raise HTTPException(status_code=404, detail=f"task_id 不存在: {task_id}")

    if task.status == "L2_RUNNING":
        return {"task_id": task.id, "status": task.status}

    latest_l1 = (
        await db.execute(
            select(TaskRun)
            .where(TaskRun.task_id == task_id, TaskRun.phase == "l1", TaskRun.status == "DONE")
            .order_by(desc(TaskRun.created_at))
            .limit(1)
        )
    ).scalar_one_or_none()
    if latest_l1 is None or latest_l1.result_json is None:
        raise HTTPException(status_code=422, detail="请先完成 L1（没有可用的 L1 run 结果），再启动 L2")

    if not task.params:
        raise HTTPException(status_code=422, detail="params 为空，无法启动 L2")

    run = TaskRun(
        task_id=task_id,
        phase="l2",
        status="RUNNING",
        parent_run_id=latest_l1.id,
        params_snapshot=task.params,
        compass_snapshot=task.compass,
        result_json=None,
        error_message=None,
    )
    db.add(run)
    await db.execute(update(ScriptTask).where(ScriptTask.id == task_id).values(status="L2_RUNNING"))
    await db.commit()
    await db.refresh(run)

    async def _job() -> None:
        try:
            async with AsyncSessionLocal() as session:
                result = await session.execute(select(ScriptTask).where(ScriptTask.id == task_id))
                t = result.scalar_one_or_none()
                if t is None:
                    return
                params = t.params or {}
                base_script = L1VideoScript.model_validate(latest_l1.result_json)
                content = t.input_text or ""
                images = list(t.image_paths) if t.image_paths else None

            compass = await _ensure_task_compass(task_id)

            def _on_progress(e: ProgressEvent) -> None:
                asyncio.create_task(_append_progress_event(task_id, run.id, e))

            sections = await l2_script_infer(
                base_script=base_script,
                content=content,
                batch_num=2,
                target_audience=str(params.get("audience") or "general"),
                platform=str(params.get("platformFormat") or "抖音"),
                language=str(params.get("outputLang") or "中文"),
                images=images,
                compass=compass,
                on_progress=_on_progress,
                include_stage_result=False,
            )

            async with AsyncSessionLocal() as session:
                dumped_sections = [s.model_dump() for s in sections]
                l1_body = []
                if isinstance(latest_l1.result_json, dict):
                    l1_body = list(latest_l1.result_json.get("body") or [])

                for i, sec in enumerate(dumped_sections):
                    if not isinstance(sec, dict):
                        continue

                    if not sec.get("item_id"):
                        l1_item_id = None
                        if i < len(l1_body) and isinstance(l1_body[i], dict):
                            l1_item_id = l1_body[i].get("item_id")
                        sec["item_id"] = l1_item_id or uuid.uuid4().hex

                    sub = list(sec.get("sub_sections") or [])
                    used = {sec.get("item_id")} if sec.get("item_id") else set()
                    for seg in sub:
                        if not isinstance(seg, dict):
                            continue

                        seg_id = seg.get("item_id")
                        if (not seg_id) or (seg_id in used):
                            seg_id = uuid.uuid4().hex
                            seg["item_id"] = seg_id
                        used.add(seg_id)
                    sec["sub_sections"] = sub

                await session.execute(update(ScriptTask).where(ScriptTask.id == task_id).values(status="DONE"))
                await session.execute(
                    update(TaskRun)
                    .where(TaskRun.id == run.id)
                    .values(status="DONE", result_json=dumped_sections, error_message=None)
                )
                await session.commit()
        except Exception as e:
            async with AsyncSessionLocal() as session:
                await session.execute(update(ScriptTask).where(ScriptTask.id == task_id).values(status="ERROR"))
                await session.execute(
                    update(TaskRun)
                    .where(TaskRun.id == run.id)
                    .values(status="ERROR", error_message=repr(e))
                )
                await session.commit()

    asyncio.create_task(_job())
    return {"task_id": task.id, "run_id": run.id, "status": "L2_RUNNING"}
