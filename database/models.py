
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import String, Text, DateTime, JSON, Integer, ForeignKey
from datetime import datetime, timezone
import uuid

from database.base import Base, async_engine


def new_id() -> str:
    return uuid.uuid4().hex  # task_id

class ScriptTask(Base):
    __tablename__ = "tasks"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)

    # Step1 产物
    input_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 多图：存储本地路径列表
    image_paths: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)

    # Step2 产物
    params: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # compass 选择（用户绑定或自动推断后缓存），供 L1/L2 复用
    compass: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    status: Mapped[str] = mapped_column(String(32), default="CREATED")  # CREATED / PARAMS_READY / L1_RUNNING / L1_DONE / L2_RUNNING / DONE / ERROR
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class TaskRun(Base):
    __tablename__ = "task_runs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    task_id: Mapped[str] = mapped_column(String(32), ForeignKey("tasks.id"), index=True)

    phase: Mapped[str] = mapped_column(String(16))  # l1 / l2
    status: Mapped[str] = mapped_column(String(32), default="RUNNING")  # RUNNING / DONE / ERROR

    parent_run_id: Mapped[str | None] = mapped_column(String(32), ForeignKey("task_runs.id"), nullable=True)

    params_snapshot: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    compass_snapshot: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    result_json: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class TaskProgressEvent(Base):
    __tablename__ = "task_progress_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[str] = mapped_column(String(32), ForeignKey("tasks.id"), index=True)
    run_id: Mapped[str] = mapped_column(String(32), ForeignKey("task_runs.id"), index=True)

    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    phase: Mapped[str] = mapped_column(String(16))
    type: Mapped[str] = mapped_column(String(32))
    data: Mapped[dict | None] = mapped_column(JSON, nullable=True)


