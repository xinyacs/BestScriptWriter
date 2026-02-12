from collections.abc import Callable

from agent.l1_workflow import l1_script_infer
from agent.l2_workflow import l2_script_infer
from agent.compass_agent import CompassChoicesAgent
from schema.base import TotalVideoScript, ProgressEvent
from core.compass import CompassSelection


async def total_script_infer(
    content: str,
    max_duration: int,
    target_audience="青年人",
    platform="抖音",
    language="中文",
    images: list[str] | None = None,
    compass: CompassSelection | None = None,
    *,
    l1_max_iters: int = 10,
    l1_retries_per_iter: int = 2,
    l2_batch_num: int = 2,
    l2_retries_per_stage: int = 1,
    on_progress: Callable[[ProgressEvent], None] | None = None,
) -> TotalVideoScript:
    # total workflow:
    # 1) L1: 生成宏观章节（L1VideoScript）
    # 2) L2: 将每个章节扩写成可拍摄分镜（Section 列表）
    # 3) 返回统一结构：{title, keywords, sections}

    def progress(evt: ProgressEvent) -> None:
        if on_progress is None:
            return
        on_progress(evt)

    if compass is None:
        inferred = await CompassChoicesAgent().infer_compass(content=content)
        compass = inferred
        if on_progress is not None:
            progress(
                ProgressEvent(
                    phase="compass",
                    type="inferred",
                    data={
                        "director": inferred.director,
                        "style": inferred.style,
                    },
                )
            )

    l1 = await l1_script_infer(
        content=content,
        max_duration=max_duration,
        target_audience=target_audience,
        platform=platform,
        language=language,
        images=images,
        compass=compass,
        max_iters=l1_max_iters,
        retries_per_iter=l1_retries_per_iter,
        on_progress=(lambda e: progress(ProgressEvent(phase="l1", type=e.type, data=e.data))) if on_progress else None,
        show_progress=False,
        include_stage_result=False,
    )

    sections = await l2_script_infer(
        base_script=l1,
        content=content,
        batch_num=l2_batch_num,
        target_audience=target_audience,
        platform=platform,
        language=language,
        images=images,
        compass=compass,
        on_progress=(lambda e: progress(ProgressEvent(phase="l2", type=e.type, data=e.data))) if on_progress else None,
        include_stage_result=False,
        retries_per_stage=l2_retries_per_stage,
    )

    # keywords dedupe (preserve order)
    seen = set()
    keywords = []
    for kw in l1.keywords:
        if kw not in seen:
            seen.add(kw)
            keywords.append(kw)

    return TotalVideoScript(
        title=l1.title,
        total_duration=l1.total_duration,
        keywords=keywords,
        sections=sections,
        notes=l1.notes,
    )
