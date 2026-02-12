from typing import AsyncIterator
from jinja2 import Template
from agent.base import BaseAgent, TModel
from pydantic import BaseModel, Field

from schema.base import L1VideoScript, ScriptSection
from util.base import render_prompt_template
from core import settings

PROMPT_TEMPLATE = Template(
    "## 续写参数"
    "- `current_second`（int，当前累计时长）：{{ current_second | default(0) }} "
    "## 系统参数 "
    "- `platform`（string，可选，默认 TikTok）：{{ platform | default('TikTok') }} "
    "- `target_audience`（string，可选，默认 18-35岁都市青年）：{{ target_audience | default('18-35岁都市青年') }} "
    "- `max_duration`（int 秒，可选，默认 60）：{{ max_duration | default(60) }} 秒 "
    "- `language`（string，可选，默认 中文）：{{ language | default('中文') }} "
    "## 故事原文(Content) "
    "{{ content }} "
    "## 衔接续写(Previous) "
    "<Previous> {{ previous }} </Previous>"
)

class L1ScreenwriterAgent(BaseAgent):
    #     ## 系统参数
    #     - `platform`（string，可选，默认
    #     "TikTok"）:{{PlatForm}}
    #     - `target_audience`（string，可选，默认
    #     "18-35岁都市青年"）:{{User}}
    #     - `max_duration`（int秒，可选，默认60）:{{Second}}
    #     秒
    #     - `language`（string，可选，默认
    #     "中文"）。{{Language}}
    #
    #     ## 故事原文(Content)
    #     {{Content}}
    #
    # ## 衔接续写(Previous)
    # < Previous >
    # {{Previous}
    #  < / Previous >

    def __init__(self, *, compass_prompt: str = ""):
        # Render prompt template (empty path for now, can be updated later)
        self.prompt = render_prompt_template(
            "./tips/level_zero.txt",
            params={},
            strict=False,
        )
        if compass_prompt:
            self.prompt = f"{self.prompt}\n\n{compass_prompt}".strip() + "\n"
        super().__init__(settings.L0_AGENT_MODEL, self.prompt)

    async def write_infer(self,content:str,max_duration:int,previous=None,target_audience="青年人",platform="抖音",language="中文",current_second=0,images: list[str] | None = None):
        user_infer_prompt = PROMPT_TEMPLATE.render(
            platform=platform,
            target_audience=target_audience,
            max_duration=max_duration,
            language=language,
            content=content,
            previous=previous,
            current_second=current_second
        )
        return await self.infer(
            message=user_infer_prompt,
            response_model=L1VideoScript,
            images=images,
            need_thinking=False
        )


_SECTION_ADJUST_TEMPLATE = Template(
    "## 任务\n"
    "你是资深编剧/导演助手。你会接收一个 ScriptSection 与用户的修改指令。\n"
    "你必须在不破坏原目标的前提下，严格按指令修改该段落内容，并输出一个新的 ScriptSection（JSON）。\n\n"
    "## 约束\n"
    "- 只修改这一段，不要生成全剧本。\n"
    "- duration 必须是整数秒，>=1。若用户未要求改变时长，保持原 duration 不变。\n"
    "- rationale 必须解释你如何落实指令。\n\n"
    "## 原始 ScriptSection(JSON)\n"
    "{{ section_json }}\n\n"
    "## 用户修改指令\n"
    "{{ instruction }}\n"
)


class L1SectionAdjustAgent(BaseAgent):
    def __init__(self, *, compass_prompt: str = ""):
        prompt = render_prompt_template(
            "./tips/level_zero.txt",
            params={},
            strict=False,
        )
        if compass_prompt:
            prompt = f"{prompt}\n\n{compass_prompt}".strip() + "\n"
        super().__init__(settings.L0_AGENT_MODEL, prompt)

    async def write_infer(
        self,
        *,
        section: ScriptSection,
        instruction: str,
    ) -> ScriptSection:
        msg = _SECTION_ADJUST_TEMPLATE.render(
            section_json=section.model_dump_json(indent=2),
            instruction=instruction,
        )
        return await self.infer(
            message=msg,
            response_model=ScriptSection,
            need_thinking=False,
        )


class _SplitSectionsResponse(BaseModel):
    sections: list[ScriptSection] = Field(default_factory=list)


_SECTION_SPLIT_TEMPLATE = Template(
    "## 任务\n"
    "你会接收一个单独的 ScriptSection（其 duration 可能 > 60 秒）。\n"
    "请将其拆分成多个连续的 ScriptSection，使得每个 section.duration <= {{ max_section_duration }}。\n\n"
    "## 约束\n"
    '- 输出 JSON，格式为 {"sections": [ScriptSection, ...]}。\n'
    "- sections 数量 >= 2。\n"
    "- 拆分后的 sections.duration 之和必须等于原 section.duration。\n"
    "- 内容应保持连贯，不要重复大段内容。\n"
    "- rationale 说明各段如何承接，以及为何这么拆。\n\n"
    "## 原始 ScriptSection(JSON)\n"
    "{{ section_json }}\n"
)


class L1SectionSplitAgent(BaseAgent):
    def __init__(self, *, compass_prompt: str = ""):
        prompt = render_prompt_template(
            "./tips/level_zero.txt",
            params={},
            strict=False,
        )
        if compass_prompt:
            prompt = f"{prompt}\n\n{compass_prompt}".strip() + "\n"
        super().__init__(settings.L0_AGENT_MODEL, prompt)

    async def write_infer(
        self,
        *,
        section: ScriptSection,
        max_section_duration: int = 60,
    ) -> list[ScriptSection]:
        msg = _SECTION_SPLIT_TEMPLATE.render(
            section_json=section.model_dump_json(indent=2),
            max_section_duration=max_section_duration,
        )
        resp = await self.infer(
            message=msg,
            response_model=_SplitSectionsResponse,
            need_thinking=False,
        )
        return resp.sections
