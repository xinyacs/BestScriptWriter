from typing import AsyncIterator
from jinja2 import Template
from agent.base import BaseAgent, TModel
from schema.base import Section
from util.base import render_prompt_template
from core import settings

PROMPT_TEMPLATE = Template(
    "## 系统参数 "
        "- `platform`（string，可选，默认 TikTok）：{{ platform | default('TikTok') }} "
        "- `target_audience`（string，可选，默认 18-35岁都市青年）：{{ target_audience | default('18-35岁都市青年') }} "
        "- `max_duration`（int 秒，可选，默认 60）：{{ max_duration | default(60) }} 秒 "
        "- `language`（string，可选，默认 中文）：{{ language | default('中文') }} "
    "## 故事原文(Content) "
        "{{ content }} "
    "## 本节内容 "
        "<Chapter> {{ chapter }} </Chapter>"
)

class L2ScreenwriterAgent(BaseAgent):

    def __init__(self, *, compass_prompt: str = ""):
        # Render prompt template (empty path for now, can be updated later)
        self.prompt = render_prompt_template(
            "./tips/level_one_source.txt",
            params={},
            strict=False,
        )
        if compass_prompt:
            self.prompt = f"{self.prompt}\n\n{compass_prompt}".strip() + "\n"
        super().__init__(settings.L1_AGENT_MODEL, self.prompt)

    async def write_infer(self,content:str,max_duration:int,chapter:str=None,target_audience="青年人",platform="抖音",language="中文",images: list[str] | None = None):
        if chapter is None or len(chapter.strip())==0:
            raise Exception("sorry the chapter is none")

        user_infer_prompt = PROMPT_TEMPLATE.render(
            platform=platform,
            target_audience=target_audience,
            max_duration=max_duration,
            language=language,
            content=content,
            chapter=chapter
        )
        return await self.infer(
            message=user_infer_prompt,
            response_model=Section,
            images=images,
            need_thinking=False
        )
