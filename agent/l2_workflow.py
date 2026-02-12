from agent.l2_writer_agents import L2ScreenwriterAgent
from schema.base import L1VideoScript
from schema.base import Section
from schema.base import ProgressEvent
from core.compass import CompassSelection, build_compass_prompt

import json
import asyncio
from collections.abc import Callable


async def l2_script_infer(
    base_script: L1VideoScript,
    content: str,
    batch_num=1,
    target_audience="青年人",
    platform="抖音",
    language="中文",
    images: list[str] | None = None,
    compass: CompassSelection | None = None,
    *,
    on_progress: Callable[[ProgressEvent], None] | None = None,
    include_stage_result: bool = False,
    retries_per_stage: int = 1,
) -> list[Section]:
    # L2: 将 L1 的章节（base_script.body）进一步拆成“可拍摄的分镜/镜头脚本”。
    #
    # 重要约定：
    # - L2 输出是 Section；默认 1 个 L1 ScriptSection -> 1 个 L2 Section。
    # - batch_num 用于控制并发（一次最多同时跑多少个 L2 请求），而不是控制 L2 输出数量。
    #
    # on_progress 回调事件：
    # - start: {type, total_chapters, batch_num, images_count}
    # - stage_start: {type, stage, chapter_index}
    # - stage_success: {type, stage, chapter_index, stage_duration, result/result_json?}
    # - stage_error: {type, stage, chapter_index, error, try}

    compass_prompt = build_compass_prompt(root_dir="./compass", platform=platform, selection=compass)
    agent = L2ScreenwriterAgent(compass_prompt=compass_prompt)
    user_progress = on_progress

    def _emit(event_type: str, data: dict) -> None:
        if user_progress is None:
            return
        user_progress(ProgressEvent(phase="l2", type=event_type, data=data))

    chapters = list(base_script.body or [])
    if not chapters:
        return []

    if batch_num is None or int(batch_num) <= 0:
        batch_num = 1
    batch_num = int(batch_num)

    _emit(
        "start",
        {
            "total_chapters": len(chapters),
            "batch_num": batch_num,
            "images_count": len(images) if images else 0,
        },
    )

    semaphore = asyncio.Semaphore(batch_num)

    async def _run_one(chapter_index: int) -> tuple[int, Section]:
        async with semaphore:
            # 单个 L1 ScriptSection -> 单个 L2 Section
            # 只传递目标 ScriptSection 和其时长，移除无关字段
            target_chapter = chapters[chapter_index]
            chapter_payload = {
                "chapter": target_chapter.model_dump(),
            }
            chapter_text = json.dumps(chapter_payload, ensure_ascii=False)

            stage_no = chapter_index + 1
            _emit(
                "stage_start",
                {
                    "stage": stage_no,
                    "chapter_index": chapter_index,
                },
            )

            last_err: Exception | None = None
            for t in range(retries_per_stage + 1):
                try:
                    section = await agent.write_infer(
                        content=content,
                        max_duration=target_chapter.duration,
                        chapter=chapter_text,
                        target_audience=target_audience,
                        platform=platform,
                        language=language,
                        images=images,
                    )

                    stage_duration = 0
                    for seg in section.sub_sections or []:
                        stage_duration += int(seg.duration_s)

                    evt = {
                        "stage": stage_no,
                        "chapter_index": chapter_index,
                        "stage_duration": stage_duration,
                    }
                    if include_stage_result:
                        d = section.model_dump()
                        evt["result"] = d
                        evt["result_json"] = json.dumps(d, ensure_ascii=False)
                    _emit("stage_success", evt)

                    return chapter_index, section
                except Exception as e:
                    last_err = e
                    _emit(
                        "stage_error",
                        {
                            "stage": stage_no,
                            "chapter_index": chapter_index,
                            "try": t + 1,
                            "error": repr(e),
                        },
                    )

            if last_err is not None:
                raise last_err
            raise RuntimeError("unreachable")

    pairs = await asyncio.gather(*[_run_one(i) for i in range(len(chapters))])
    pairs.sort(key=lambda x: x[0])
    return [s for _, s in pairs]
