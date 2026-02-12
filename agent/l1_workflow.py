from agent.l1_writer_agents import L1ScreenwriterAgent, L1SectionAdjustAgent, L1SectionSplitAgent
import json
import sys
import time
from collections.abc import Callable
from schema.base import L1VideoScript, ProgressEvent, ScriptSection
from core.compass import CompassSelection, build_compass_prompt


async def l1_script_infer(
    content: str,
    max_duration: int,
    target_audience="青年人",
    platform="抖音",
    language="中文",
    images: list[str] | None = None,
    compass: CompassSelection | None = None,
    *,
    max_iters: int = 10,
    retries_per_iter: int = 2,
    on_progress: Callable[[ProgressEvent], None] | None = None,
    show_progress: bool = True,

    include_stage_result: bool = True,

) -> L1VideoScript:
    compass_prompt = build_compass_prompt(root_dir="./compass", platform=platform, selection=compass)
    base_agent = L1ScreenwriterAgent(compass_prompt=compass_prompt)

    stages: list[L1VideoScript] = []
    previous_json: str | None = None
    current_second: int = 0

    user_progress = on_progress
    printer = _default_progress_printer() if (show_progress and user_progress is None) else None

    def _emit(event_type: str, data: dict) -> None:
        if user_progress is not None:
            user_progress(ProgressEvent(phase="l1", type=event_type, data=data))
        if printer is not None:
            printer({"type": event_type, **data})

    _emit(
        "start",
        {
            "max_iters": max_iters,
            "retries_per_iter": retries_per_iter,
            "current_second": current_second,
            "images_count": len(images) if images else 0,
        },
    )

    for _ in range(max_iters):
        stage_index = len(stages) + 1
        last_err: Exception | None = None
        for _try in range(retries_per_iter + 1):
            try:
                _emit(
                    "iter_start",
                    {
                        "stage": stage_index,
                        "try": _try + 1,
                        "retries_per_iter": retries_per_iter,
                        "current_second": current_second,
                        "max_duration": max_duration,
                        "images_count": len(images) if images else 0,
                    },
                )

                result = await base_agent.write_infer(
                    content=content,
                    max_duration=max_duration,
                    previous=previous_json,
                    target_audience=target_audience,
                    platform=platform,
                    language=language,
                    current_second=current_second,
                    images=images,
                )
                stages.append(result)

                stage_duration = sum((x.duration for x in (result.body or [])), 0)
                current_second += stage_duration

                # pass previous as json string to the next iteration
                previous_json = json.dumps(result.model_dump(), ensure_ascii=False)

                evt = {
                    "stage": stage_index,
                    "need_write_next": result.need_write_next,
                    "title": getattr(result, "title", None),
                    "keywords_count": len(getattr(result, "keywords", []) or []),
                    "body_count": len(getattr(result, "body", []) or []),
                    "stage_duration": stage_duration,
                    "current_second": current_second,
                    "max_duration": max_duration,
                }
                if include_stage_result:
                    result_dict = result.model_dump()
                    evt["result"] = result_dict
                    evt["result_json"] = json.dumps(result_dict, ensure_ascii=False)
                _emit("iter_success", evt)

                if not result.need_write_next:
                    merged = _merge_l1_stages(stages)

                    merged = await _split_overlong_sections(
                        merged,
                        max_section_duration=60,
                        compass_prompt=compass_prompt,
                        on_progress=_emit,
                    )

                    _emit(
                        "done",
                        {
                            "stages": len(stages),
                            "merged_keywords_count": len(merged.keywords),
                            "merged_body_count": len(merged.body),
                        },
                    )
                    if printer is not None:
                        printer({"type": "newline"})
                    return merged
                break
            except Exception as e:
                last_err = e
                _emit(
                    "iter_error",
                    {
                        "stage": stage_index,
                        "try": _try + 1,
                        "error": repr(e),
                    },
                )
        else:
            if last_err is not None:
                if printer is not None:
                    printer({"type": "newline"})
                raise last_err

    if printer is not None:
        printer({"type": "newline"})
    raise RuntimeError(f"workflow exceeded max_iters={max_iters}")


async def _split_overlong_sections(
    script: L1VideoScript,
    *,
    max_section_duration: int = 60,
    compass_prompt: str = "",
    on_progress: Callable[[str, dict], None] | None = None,
) -> L1VideoScript:
    def emit(event_type: str, data: dict) -> None:
        if on_progress is not None:
            on_progress(event_type, data)

    splitter = L1SectionSplitAgent(compass_prompt=compass_prompt)

    async def split_one(section: ScriptSection, depth: int = 0) -> list[ScriptSection]:
        if section.duration <= max_section_duration:
            return [section]

        if depth >= 6:
            return [section]

        emit(
            "section_split_start",
            {"duration": section.duration, "max": max_section_duration, "depth": depth},
        )
        parts = await splitter.write_infer(section=section, max_section_duration=max_section_duration)
        flattened: list[ScriptSection] = []
        for p in parts:
            flattened.extend(await split_one(p, depth + 1))
        emit(
            "section_split_done",
            {
                "original_duration": section.duration,
                "parts": len(flattened),
                "depth": depth,
            },
        )
        return flattened

    new_body: list[ScriptSection] = []
    for sec in script.body or []:
        new_body.extend(await split_one(sec, 0))

    new_total = sum(s.duration for s in new_body)
    return L1VideoScript(
        title=script.title,
        total_duration=new_total,
        keywords=list(script.keywords or []),
        body=new_body,
        need_write_next=False,
        notes=script.notes,
    )


async def l1_apply_section_instruction(
    *,
    script: L1VideoScript,
    section_index: int,
    instruction: str,
    compass_prompt: str = "",
) -> L1VideoScript:
    if section_index < 0 or section_index >= len(script.body):
        raise IndexError(f"section_index out of range: {section_index}")

    agent = L1SectionAdjustAgent(compass_prompt=compass_prompt)
    new_section = await agent.write_infer(section=script.body[section_index], instruction=instruction)

    new_body = list(script.body)
    new_body[section_index] = new_section
    new_total = sum(s.duration for s in new_body)
    return L1VideoScript(
        title=script.title,
        total_duration=new_total,
        keywords=list(script.keywords or []),
        body=new_body,
        need_write_next=False,
        notes=script.notes,
    )


def _default_progress_printer() -> Callable[[dict], None]:
    start_ts = time.time()
    state = {"last_len": 0}

    def _write_line(s: str) -> None:
        pad = " " * max(0, state["last_len"] - len(s))
        sys.stdout.write("\r" + s + pad)
        sys.stdout.flush()
        state["last_len"] = len(s)

    def _printer(evt: dict) -> None:
        et = evt.get("type")
        if et == "newline":
            sys.stdout.write("\n")
            sys.stdout.flush()
            state["last_len"] = 0
            return

        elapsed = int(time.time() - start_ts)
        if et == "start":
            _write_line(f"[workflow] start | elapsed={elapsed}s")
            return

        if et == "iter_start":
            stage = evt.get("stage")
            t = evt.get("try")
            retries = evt.get("retries_per_iter")
            cs = evt.get("current_second")
            md = evt.get("max_duration")
            _write_line(
                f"[workflow] stage {stage} | try {t}/{(retries + 1)} | "
                f"current={cs}/{md}s | elapsed={elapsed}s"
            )
            return

        if et == "iter_success":
            stage = evt.get("stage")
            nxt = evt.get("need_write_next")
            cs = evt.get("current_second")
            md = evt.get("max_duration")
            _write_line(
                f"[workflow] stage {stage} ok | need_next={nxt} | "
                f"current={cs}/{md}s | elapsed={elapsed}s"
            )
            return

        if et == "iter_error":
            stage = evt.get("stage")
            t = evt.get("try")
            _write_line(
                f"[workflow] stage {stage} error on try {t} | elapsed={elapsed}s"
            )
            return

        if et == "done":
            stages = evt.get("stages")
            _write_line(
                f"[workflow] done | stages={stages} | elapsed={elapsed}s"
            )

    return _printer


def _merge_l1_stages(stages: list[L1VideoScript]) -> L1VideoScript:
    if not stages:
        raise ValueError("stages is empty")

    base = stages[0]

    # keywords: dedupe (preserve order)
    seen: set[str] = set()
    merged_keywords: list[str] = []
    for stage in stages:
        for kw in stage.keywords:
            if kw not in seen:
                seen.add(kw)
                merged_keywords.append(kw)

    merged_body = []
    for stage in stages:
        merged_body.extend(stage.body)

    return L1VideoScript(
        title=base.title,
        total_duration=base.total_duration,
        keywords=merged_keywords,
        body=merged_body,
        need_write_next=False,
        notes=base.notes,
    )