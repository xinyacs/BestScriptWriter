from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from jinja2 import Template
from pydantic import BaseModel, Field

from agent.base import BaseAgent
from core import settings
from core.compass import CompassSelection, build_compass_prompt


PromptTarget = Literal["seedrance2", "sora2", "veo3"]


class PromptExportResult(BaseModel):
    prompt: str = Field(..., description="Prompt text for the target platform")


_SYSTEM_PROMPT = Template(
    "## Role\n"
    "You are a professional text-to-video prompt engineer.\n\n"
    "## Goal\n"
    "Generate ONE concise prompt for the target platform.\n\n"
    "## Constraints\n"
    "- Output JSON only, matching response schema.\n"
    "- You must respect the MAX_CHARS provided by the user message (strict).\n"
    "- Use the same language as the input content.\n"
    "- Do not include markdown.\n"
    "- Do not include any extra keys.\n\n"
    "## Compass\n"
    "{{ compass_prompt }}\n"
)


_USER_PROMPT = Template(
    "TARGET={{ target }}\n"
    "MAX_CHARS={{ max_chars }}\n\n"
    "SECTION_JSON={{ section_json }}\n\n"
    "SUB_SECTION_JSON={{ sub_json }}\n"
)


class PromptExportAgent(BaseAgent):
    def __init__(
        self,
        *,
        compass: dict | None = None,
        compass_root_dir: str = "./compass",
    ):
        self._compass = compass or {}
        self._compass_root_dir = compass_root_dir
        super().__init__(settings.L0_AGENT_MODEL, _SYSTEM_PROMPT.render(compass_prompt=""))

    def _load_prompt_compass_text(self, *, target: PromptTarget) -> str:
        name_map = {
            "seedrance2": "seedrance_compass.md",
            "sora2": "sora_compass.md",
            "veo3": "veo_compass.md",
        }
        fname = name_map.get(target)
        if not fname:
            return ""

        p = Path(self._compass_root_dir) / "prompt" / fname
        if not p.exists() or not p.is_file():
            return ""
        try:
            return p.read_text(encoding="utf-8").strip()
        except Exception:
            return ""

    def _build_compass_prompt(self, *, target: PromptTarget) -> str:
        selection = CompassSelection(
            director=self._compass.get("director"),
            style=self._compass.get("style"),
        )
        base = build_compass_prompt(
            root_dir=self._compass_root_dir,
            platform=None,
            selection=selection,
        ).strip()

        extra = self._load_prompt_compass_text(target=target)
        if extra:
            return (base + "\n\n" + extra).strip() if base else extra
        return base

    async def export(
        self,
        *,
        target: PromptTarget,
        max_chars: int,
        section: dict,
        sub_section: dict,
    ) -> str:
        compass_prompt = self._build_compass_prompt(target=target)
        self.prompt = _SYSTEM_PROMPT.render(compass_prompt=compass_prompt or "")
        msg = _USER_PROMPT.render(
            target=target,
            max_chars=max_chars,
            section_json=json.dumps(section, ensure_ascii=False, indent=2),
            sub_json=json.dumps(sub_section, ensure_ascii=False, indent=2),
        )
        result = await self.infer(message=msg, response_model=PromptExportResult, need_thinking=False)
        p = (result.prompt or "").strip()
        if len(p) > int(max_chars):
            p = p[: int(max_chars)].rstrip()
        return p
