from __future__ import annotations

import uuid
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from core.dependences import get_db
from database.models import TaskRun

router = APIRouter(prefix="/l1", tags=["L1"])


class L1BodyItemCreate(BaseModel):
    section: str
    rationale: str
    duration: int = Field(..., ge=1)


class L1ReorderRequest(BaseModel):
    from_section_id: str
    to_section_id: str
    position: str = Field(..., description="before or after")


class L1InsertRequest(BaseModel):
    item: L1BodyItemCreate
    index: Optional[int] = Field(default=None, ge=0)
    after_item_id: Optional[str] = None


class L1DeleteRequest(BaseModel):
    item_id: str


class L1ItemUpdateRequest(BaseModel):
    item_id: str
    section: Optional[str] = None
    rationale: Optional[str] = None
    duration: Optional[int] = Field(default=None, ge=1)


async def _get_latest_l1_run(db: AsyncSession, task_id: str) -> TaskRun:
    run = (
        await db.execute(
            select(TaskRun)
            .where(TaskRun.task_id == task_id, TaskRun.phase == "l1")
            .order_by(desc(TaskRun.created_at))
            .limit(1)
        )
    ).scalar_one_or_none()

    if run is None or run.result_json is None:
        raise HTTPException(status_code=404, detail="未找到可编辑的 L1 结果（请先运行 L1）")

    return run


def _ensure_item_ids(l1_json: dict) -> dict:
    out = dict(l1_json)
    body = []
    for it in list(out.get("body") or []):
        if not isinstance(it, dict):
            continue
        it2 = dict(it)
        if not it2.get("item_id"):
            it2["item_id"] = uuid.uuid4().hex
        body.append(it2)
    out["body"] = body
    return out


def _recalc_total_duration(l1_json: dict) -> dict:
    out = dict(l1_json)
    body = list(out.get("body") or [])
    total = 0
    for it in body:
        if isinstance(it, dict):
            total += int(it.get("duration") or 0)
    out["total_duration"] = total
    return out


@router.post("/task/{task_id}/item/update")
async def update_l1_item(task_id: str, req: L1ItemUpdateRequest, db: AsyncSession = Depends(get_db)):
    run = await _get_latest_l1_run(db, task_id)
    l1_json = _recalc_total_duration(_ensure_item_ids(dict(run.result_json)))
    body: List[dict] = list(l1_json.get("body") or [])

    idx = next((i for i, x in enumerate(body) if isinstance(x, dict) and x.get("item_id") == req.item_id), None)
    if idx is None:
        raise HTTPException(status_code=404, detail=f"item_id 不存在: {req.item_id}")

    it = dict(body[idx])
    if req.section is not None:
        it["section"] = req.section
    if req.rationale is not None:
        it["rationale"] = req.rationale
    if req.duration is not None:
        it["duration"] = int(req.duration)

    body[idx] = it
    l1_json["body"] = body
    l1_json = _recalc_total_duration(l1_json)

    new_run = TaskRun(
        task_id=task_id,
        phase="l1",
        status="DONE",
        parent_run_id=run.id,
        params_snapshot=run.params_snapshot,
        compass_snapshot=run.compass_snapshot,
        result_json=l1_json,
        error_message=None,
    )
    db.add(new_run)
    await db.commit()
    await db.refresh(new_run)

    return {"task_id": task_id, "run_id": new_run.id, "l1": l1_json}


@router.post("/task/{task_id}/reorder")
async def reorder_l1(task_id: str, req: L1ReorderRequest, db: AsyncSession = Depends(get_db)):
    run = await _get_latest_l1_run(db, task_id)
    l1_json = _recalc_total_duration(_ensure_item_ids(dict(run.result_json)))
    body: List[dict] = list(l1_json.get("body") or [])

    from_id = req.from_section_id
    to_id = req.to_section_id

    from_idx = next((i for i, x in enumerate(body) if isinstance(x, dict) and x.get("item_id") == from_id), None)
    if from_idx is None:
        raise HTTPException(status_code=404, detail=f"from_section_id 不存在: {from_id}")

    to_idx = next((i for i, x in enumerate(body) if isinstance(x, dict) and x.get("item_id") == to_id), None)
    if to_idx is None:
        raise HTTPException(status_code=404, detail=f"to_section_id 不存在: {to_id}")

    position = (req.position or "").strip().lower()
    if position not in ("before", "after"):
        raise HTTPException(status_code=422, detail="position 必须是 before 或 after")

    if from_idx == to_idx:
        return {"task_id": task_id, "run_id": run.id, "l1": l1_json}

    moving = body.pop(from_idx)
    if from_idx < to_idx:
        to_idx -= 1

    insert_at = to_idx if position == "before" else to_idx + 1
    if insert_at < 0:
        insert_at = 0
    if insert_at > len(body):
        insert_at = len(body)
    body.insert(insert_at, moving)

    l1_json["body"] = body
    l1_json = _recalc_total_duration(l1_json)

    new_run = TaskRun(
        task_id=task_id,
        phase="l1",
        status="DONE",
        parent_run_id=run.id,
        params_snapshot=run.params_snapshot,
        compass_snapshot=run.compass_snapshot,
        result_json=l1_json,
        error_message=None,
    )
    db.add(new_run)
    await db.commit()
    await db.refresh(new_run)

    return {"task_id": task_id, "run_id": new_run.id, "l1": l1_json}


@router.post("/task/{task_id}/insert")
async def insert_l1_item(task_id: str, req: L1InsertRequest, db: AsyncSession = Depends(get_db)):
    run = await _get_latest_l1_run(db, task_id)
    l1_json = _recalc_total_duration(_ensure_item_ids(dict(run.result_json)))
    body: List[dict] = list(l1_json.get("body") or [])

    new_item = {
        "item_id": uuid.uuid4().hex,
        "section": req.item.section,
        "rationale": req.item.rationale,
        "duration": int(req.item.duration),
    }

    insert_at: Optional[int] = None
    if req.index is not None:
        insert_at = int(req.index)
        if insert_at < 0 or insert_at > len(body):
            raise HTTPException(status_code=422, detail=f"index 越界: {insert_at}")
    elif req.after_item_id:
        after_idx = next(
            (i for i, x in enumerate(body) if isinstance(x, dict) and x.get("item_id") == req.after_item_id),
            None,
        )
        if after_idx is None:
            raise HTTPException(status_code=404, detail=f"after_item_id 不存在: {req.after_item_id}")
        insert_at = after_idx + 1
    else:
        insert_at = len(body)

    body.insert(insert_at, new_item)
    l1_json["body"] = body
    l1_json = _recalc_total_duration(l1_json)

    new_run = TaskRun(
        task_id=task_id,
        phase="l1",
        status="DONE",
        parent_run_id=run.id,
        params_snapshot=run.params_snapshot,
        compass_snapshot=run.compass_snapshot,
        result_json=l1_json,
        error_message=None,
    )
    db.add(new_run)
    await db.commit()
    await db.refresh(new_run)

    return {"task_id": task_id, "run_id": new_run.id, "l1": l1_json}


@router.post("/task/{task_id}/delete")
async def delete_l1_item(task_id: str, req: L1DeleteRequest, db: AsyncSession = Depends(get_db)):
    run = await _get_latest_l1_run(db, task_id)
    l1_json = _recalc_total_duration(_ensure_item_ids(dict(run.result_json)))
    body: List[dict] = list(l1_json.get("body") or [])

    new_body = [x for x in body if not (isinstance(x, dict) and x.get("item_id") == req.item_id)]
    if len(new_body) == len(body):
        raise HTTPException(status_code=404, detail=f"item_id 不存在: {req.item_id}")

    l1_json["body"] = new_body
    l1_json = _recalc_total_duration(l1_json)

    new_run = TaskRun(
        task_id=task_id,
        phase="l1",
        status="DONE",
        parent_run_id=run.id,
        params_snapshot=run.params_snapshot,
        compass_snapshot=run.compass_snapshot,
        result_json=l1_json,
        error_message=None,
    )
    db.add(new_run)
    await db.commit()
    await db.refresh(new_run)

    return {"task_id": task_id, "run_id": new_run.id, "l1": l1_json}
