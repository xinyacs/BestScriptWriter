from __future__ import annotations

import uuid
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from core.dependences import get_db
from database.models import TaskRun, ScriptTask
from agent.prompt_export_agent import PromptExportAgent

router = APIRouter(prefix="/l2", tags=["L2"])


_TARGET_MAX_CHARS = {
    "seedrance2": 1000,
    "sora2": 2000,
    "veo3": 2000,
}


def _recalc_section_duration(section: dict) -> dict:
    out = dict(section)
    sub = list(out.get("sub_sections") or [])
    total = 0
    for seg in sub:
        if isinstance(seg, dict):
            total += int(seg.get("duration_s") or 0)
    out["duration"] = total
    return out


def _ensure_sub_item_ids(section: dict) -> dict:
    out = dict(section)
    if not out.get("item_id"):
        out["item_id"] = uuid.uuid4().hex
    used = {out.get("item_id")} if out.get("item_id") else set()
    sub = []
    for seg in list(out.get("sub_sections") or []):
        if not isinstance(seg, dict):
            continue
        seg2 = dict(seg)
        seg_id = seg2.get("item_id")
        if (not seg_id) or (seg_id in used):
            seg_id = uuid.uuid4().hex
            seg2["item_id"] = seg_id
        used.add(seg_id)
        sub.append(seg2)
    out["sub_sections"] = sub
    return out


async def _get_latest_l2_run(db: AsyncSession, task_id: str) -> TaskRun:
    run = (
        await db.execute(
            select(TaskRun)
            .where(TaskRun.task_id == task_id, TaskRun.phase == "l2", TaskRun.status == "DONE")
            .order_by(desc(TaskRun.created_at))
            .limit(1)
        )
    ).scalar_one_or_none()

    if run is None or run.result_json is None:
        raise HTTPException(status_code=404, detail="未找到可编辑的 L2 结果（请先运行 L2）")
    if not isinstance(run.result_json, list):
        raise HTTPException(status_code=500, detail="L2 结果格式异常：result_json 不是 list")

    return run


def _find_section_index(sections: list, section_id: str) -> int:
    for i, sec in enumerate(sections):
        if isinstance(sec, dict) and sec.get("item_id") == section_id:
            return i
    return -1


def _find_sub_index(sub_sections: list, sub_item_id: str) -> int:
    for i, seg in enumerate(sub_sections):
        if isinstance(seg, dict) and seg.get("item_id") == sub_item_id:
            return i
    return -1


class L2SubItemCreate(BaseModel):
    title: str
    duration_s: int = Field(..., ge=1)
    shot: str
    camera_move: str
    location: str
    props: List[str] = Field(default_factory=list)
    visual: str
    onscreen_text: str = ""
    audio: str = ""
    music: str = ""
    transition: str = ""
    compliance_notes: str = ""


class L2SubItemInsertRequest(BaseModel):
    section_id: str
    item: L2SubItemCreate
    index: Optional[int] = Field(default=None, ge=0)
    after_item_id: Optional[str] = None


class L2SubItemDeleteRequest(BaseModel):
    section_id: str
    sub_item_id: str


class L2SubItemUpdateRequest(BaseModel):
    section_id: str
    sub_item_id: str
    title: Optional[str] = None
    duration_s: Optional[int] = Field(default=None, ge=1)
    shot: Optional[str] = None
    camera_move: Optional[str] = None
    location: Optional[str] = None
    props: Optional[List[str]] = None
    visual: Optional[str] = None
    onscreen_text: Optional[str] = None
    audio: Optional[str] = None
    music: Optional[str] = None
    transition: Optional[str] = None
    compliance_notes: Optional[str] = None


class L2SubItemReorderRequest(BaseModel):
    section_id: str
    from_sub_item_id: str
    to_sub_item_id: str
    position: str = Field(..., description="before or after")


@router.get("/task/{task_id}/sub_sections/prompt", response_class=PlainTextResponse)
async def export_sub_item_prompt(
    task_id: str,
    *,
    section_id: str,
    sub_item_id: str,
    target: str,
    db: AsyncSession = Depends(get_db),
):
    target_key = (target or "").strip().lower()
    if target_key not in _TARGET_MAX_CHARS:
        raise HTTPException(status_code=422, detail="target 必须是 seedrance2 / sora2 / veo3")
    max_chars = int(_TARGET_MAX_CHARS[target_key])

    task = (
        await db.execute(select(ScriptTask).where(ScriptTask.id == task_id))
    ).scalar_one_or_none()
    if task is None:
        raise HTTPException(status_code=404, detail=f"task_id 不存在: {task_id}")

    run = await _get_latest_l2_run(db, task_id)
    sections = list(run.result_json or [])

    sec_idx = _find_section_index(sections, section_id)
    if sec_idx < 0:
        raise HTTPException(status_code=404, detail=f"section_id 不存在: {section_id}")

    sec = _ensure_sub_item_ids(dict(sections[sec_idx]))
    sub = list(sec.get("sub_sections") or [])
    sub_idx = _find_sub_index(sub, sub_item_id)
    if sub_idx < 0:
        raise HTTPException(status_code=404, detail=f"sub_item_id 不存在: {sub_item_id}")

    seg = dict(sub[sub_idx])

    compass_dict = task.compass or {}

    agent = PromptExportAgent(
        compass=compass_dict,
        compass_root_dir="./compass",
    )
    prompt = await agent.export(
        target=target_key,  # type: ignore[arg-type]
        max_chars=max_chars,
        section=sec,
        sub_section=seg,
    )

    if len(prompt) > max_chars:
        prompt = prompt[:max_chars].rstrip()
    return prompt


@router.post("/task/{task_id}/sub_sections/insert")
async def insert_sub_item(task_id: str, req: L2SubItemInsertRequest, db: AsyncSession = Depends(get_db)):
    run = await _get_latest_l2_run(db, task_id)
    sections = list(run.result_json or [])

    sec_idx = _find_section_index(sections, req.section_id)
    if sec_idx < 0:
        raise HTTPException(status_code=404, detail=f"section_id 不存在: {req.section_id}")

    sec = _ensure_sub_item_ids(dict(sections[sec_idx]))
    sub = list(sec.get("sub_sections") or [])

    new_item = {"item_id": uuid.uuid4().hex, **req.item.model_dump()}

    insert_at: Optional[int] = None
    if req.index is not None:
        insert_at = int(req.index)
        if insert_at < 0 or insert_at > len(sub):
            raise HTTPException(status_code=422, detail=f"index 越界: {insert_at}")
    elif req.after_item_id:
        after_idx = _find_sub_index(sub, req.after_item_id)
        if after_idx < 0:
            raise HTTPException(status_code=404, detail=f"after_item_id 不存在: {req.after_item_id}")
        insert_at = after_idx + 1
    else:
        insert_at = len(sub)

    sub.insert(insert_at, new_item)
    sec["sub_sections"] = sub
    sec = _recalc_section_duration(sec)

    sections[sec_idx] = sec

    new_run = TaskRun(
        task_id=task_id,
        phase="l2",
        status="DONE",
        parent_run_id=run.id,
        params_snapshot=run.params_snapshot,
        compass_snapshot=run.compass_snapshot,
        result_json=sections,
        error_message=None,
    )
    db.add(new_run)
    await db.commit()
    await db.refresh(new_run)

    return {"task_id": task_id, "run_id": new_run.id, "sections": sections}


@router.post("/task/{task_id}/sub_sections/delete")
async def delete_sub_item(task_id: str, req: L2SubItemDeleteRequest, db: AsyncSession = Depends(get_db)):
    run = await _get_latest_l2_run(db, task_id)
    sections = list(run.result_json or [])

    sec_idx = _find_section_index(sections, req.section_id)
    if sec_idx < 0:
        raise HTTPException(status_code=404, detail=f"section_id 不存在: {req.section_id}")

    sec = _ensure_sub_item_ids(dict(sections[sec_idx]))
    sub = list(sec.get("sub_sections") or [])

    idx = _find_sub_index(sub, req.sub_item_id)
    if idx < 0:
        raise HTTPException(status_code=404, detail=f"sub_item_id 不存在: {req.sub_item_id}")

    sub.pop(idx)
    if not sub:
        raise HTTPException(status_code=422, detail="sub_sections 不能为空（至少保留 1 个镜头）")

    sec["sub_sections"] = sub
    sec = _recalc_section_duration(sec)

    sections[sec_idx] = sec

    new_run = TaskRun(
        task_id=task_id,
        phase="l2",
        status="DONE",
        parent_run_id=run.id,
        params_snapshot=run.params_snapshot,
        compass_snapshot=run.compass_snapshot,
        result_json=sections,
        error_message=None,
    )
    db.add(new_run)
    await db.commit()
    await db.refresh(new_run)

    return {"task_id": task_id, "run_id": new_run.id, "sections": sections}


@router.post("/task/{task_id}/sub_sections/update")
async def update_sub_item(task_id: str, req: L2SubItemUpdateRequest, db: AsyncSession = Depends(get_db)):
    run = await _get_latest_l2_run(db, task_id)
    sections = list(run.result_json or [])

    sec_idx = _find_section_index(sections, req.section_id)
    if sec_idx < 0:
        raise HTTPException(status_code=404, detail=f"section_id 不存在: {req.section_id}")

    sec = _ensure_sub_item_ids(dict(sections[sec_idx]))
    sub = list(sec.get("sub_sections") or [])

    idx = _find_sub_index(sub, req.sub_item_id)
    if idx < 0:
        raise HTTPException(status_code=404, detail=f"sub_item_id 不存在: {req.sub_item_id}")

    it = dict(sub[idx])
    patch = req.model_dump(exclude_none=True)
    patch.pop("section_id", None)
    patch.pop("sub_item_id", None)
    it.update(patch)

    sub[idx] = it
    sec["sub_sections"] = sub
    sec = _recalc_section_duration(sec)

    sections[sec_idx] = sec

    new_run = TaskRun(
        task_id=task_id,
        phase="l2",
        status="DONE",
        parent_run_id=run.id,
        params_snapshot=run.params_snapshot,
        compass_snapshot=run.compass_snapshot,
        result_json=sections,
        error_message=None,
    )
    db.add(new_run)
    await db.commit()
    await db.refresh(new_run)

    return {"task_id": task_id, "run_id": new_run.id, "sections": sections}


@router.post("/task/{task_id}/sub_sections/reorder")
async def reorder_sub_item(task_id: str, req: L2SubItemReorderRequest, db: AsyncSession = Depends(get_db)):
    run = await _get_latest_l2_run(db, task_id)
    sections = list(run.result_json or [])

    sec_idx = _find_section_index(sections, req.section_id)
    if sec_idx < 0:
        raise HTTPException(status_code=404, detail=f"section_id 不存在: {req.section_id}")

    sec = _ensure_sub_item_ids(dict(sections[sec_idx]))
    sub = list(sec.get("sub_sections") or [])

    from_idx = _find_sub_index(sub, req.from_sub_item_id)
    if from_idx < 0:
        raise HTTPException(status_code=404, detail=f"from_sub_item_id 不存在: {req.from_sub_item_id}")

    to_idx = _find_sub_index(sub, req.to_sub_item_id)
    if to_idx < 0:
        raise HTTPException(status_code=404, detail=f"to_sub_item_id 不存在: {req.to_sub_item_id}")

    position = (req.position or "").strip().lower()
    if position not in ("before", "after"):
        raise HTTPException(status_code=422, detail="position 必须是 before 或 after")

    if from_idx == to_idx:
        return {"task_id": task_id, "run_id": run.id, "sections": sections}

    moving = sub.pop(from_idx)
    if from_idx < to_idx:
        to_idx -= 1

    insert_at = to_idx if position == "before" else to_idx + 1
    if insert_at < 0:
        insert_at = 0
    if insert_at > len(sub):
        insert_at = len(sub)

    sub.insert(insert_at, moving)
    sec["sub_sections"] = sub
    sec = _recalc_section_duration(sec)

    sections[sec_idx] = sec

    new_run = TaskRun(
        task_id=task_id,
        phase="l2",
        status="DONE",
        parent_run_id=run.id,
        params_snapshot=run.params_snapshot,
        compass_snapshot=run.compass_snapshot,
        result_json=sections,
        error_message=None,
    )
    db.add(new_run)
    await db.commit()
    await db.refresh(new_run)

    return {"task_id": task_id, "run_id": new_run.id, "sections": sections}
