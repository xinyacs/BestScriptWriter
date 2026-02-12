import instructor
from collections.abc import AsyncIterator
import base64
import json
import mimetypes
import os
import re
from urllib.parse import urlparse
from typing import Any, TypeVar

from instructor.cache import AutoCache
from pydantic import BaseModel

from core import settings
from openai import AsyncOpenAI

#OpenAi client
_raw_client = AsyncOpenAI(
    base_url=settings.OPENAI_HOST,
    api_key=settings.OPENAI_KEY,
)

client = instructor.from_openai(
    _raw_client,
    cache=AutoCache(
        maxsize=10_000
    )
)


TModel = TypeVar("TModel", bound=BaseModel)


class BaseAgent:
    def __init__(self, model: str, prompt: str):
        self.model = model
        self.prompt = prompt

    async def infer(
        self,
        message: str,
        response_model: type[TModel],
        *,
        images: list[str] | None = None,
        stream: bool = False,
        max_retries: int = 3,
        need_thinking=False
    ) -> TModel | AsyncIterator[TModel]:
        user_content: str | list[dict[str, Any]] = message
        if images:
            parts: list[dict[str, Any]] = [{"type": "text", "text": message}]
            for img in images:
                parts.append(_to_image_part(img))
            user_content = parts

        messages = [
            {"role": "system", "content": self.prompt},
            {"role": "user", "content": user_content},
        ]
        print(messages)
        if stream:
            return client.create(
                model=self.model,
                response_model=response_model,
                messages=messages,
                max_retries=max_retries,
                stream=True,
                extra_body={"chat_template_kwargs": {"thinking": need_thinking}},
            )

        try:
            return await client.create(
                model=self.model,
                response_model=response_model,
                messages=messages,
                max_retries=max_retries,
                extra_body={"chat_template_kwargs": {"thinking": need_thinking}},
            )
        except Exception as e:
            msg = str(e)
            if "invalid grammar request" not in msg.lower():
                raise
            schema = _get_model_json_schema(response_model)
            fallback_messages = [
                {"role": "system", "content": self.prompt},
                {
                    "role": "system",
                    "content": "You must output ONLY a valid JSON object that matches the given JSON schema.",
                },
                {"role": "system", "content": f"JSON_SCHEMA: {json.dumps(schema, ensure_ascii=False)}"},
                {"role": "user", "content": user_content},
            ]
            resp = await _raw_client.chat.completions.create(
                model=self.model,
                messages=fallback_messages,
                response_format={"type": "json_object"},
                extra_body={"chat_template_kwargs": {"thinking": need_thinking}},
            )
            content = (resp.choices[0].message.content or "").strip()
            return _parse_json_content_to_model(content, response_model)


def _is_http_url(s: str) -> bool:
    try:
        p = urlparse(s)
        return p.scheme in {"http", "https"} and bool(p.netloc)
    except Exception:
        return False


def _to_image_part(image: str) -> dict[str, Any]:
    if _is_http_url(image):
        return {"type": "image_url", "image_url": {"url": image}}

    path = os.path.expanduser(image)
    mime, _ = mimetypes.guess_type(path)
    if not mime:
        mime = "image/png"
    with open(path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("ascii")
    data_url = f"data:{mime};base64,{b64}"
    return {"type": "image_url", "image_url": {"url": data_url}}


def _get_model_json_schema(model: type[BaseModel]) -> dict[str, Any]:
    if hasattr(model, "model_json_schema"):
        return model.model_json_schema()
    return model.schema()  # type: ignore[attr-defined]


def _parse_json_content_to_model(content: str, model: type[TModel]) -> TModel:
    if hasattr(model, "model_validate_json"):
        try:
            return model.model_validate_json(content)  # type: ignore[return-value]
        except Exception:
            pass
    try:
        data = json.loads(content)
        if hasattr(model, "model_validate"):
            return model.model_validate(data)  # type: ignore[return-value]
        return model.parse_obj(data)  # type: ignore[return-value]
    except Exception:
        m = re.search(r"\{[\s\S]*\}", content)
        if not m:
            raise
        candidate = m.group(0)
        if hasattr(model, "model_validate_json"):
            return model.model_validate_json(candidate)  # type: ignore[return-value]
        return model.parse_raw(candidate)  # type: ignore[return-value]
