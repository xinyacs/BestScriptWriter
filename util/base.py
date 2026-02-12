import re
import json
from pathlib import Path
from typing import Any, Dict


_PLACEHOLDER_RE = re.compile(r"\{\{\s*(\w+)\s*\}\}")


def render_prompt_template(
    template_path: str | Path,
    params: Dict[str, Any],
    *,
    strict: bool = False,
    json_indent: int | None = 2,
) -> str:
    """
    读取 txt 模板并进行参数渲染（类 jinja2 / jina2）

    参数:
        template_path: 模板文件路径
        params: 渲染参数，如 {"Content": "...", "Previous": "...", "args": {...}}
        strict: 是否严格模式（True = 缺参直接报错）
        json_indent: dict / list 渲染为 JSON 时的缩进（None = 单行）

    返回:
        渲染完成的字符串
    """
    template_path = Path(template_path)
    if not template_path.exists():
        raise FileNotFoundError(f"Template not found: {template_path}")

    template_text = template_path.read_text(encoding="utf-8")

    def _render_value(value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, (dict, list)):
            return json.dumps(
                value,
                ensure_ascii=False,
                indent=json_indent,
            )
        return str(value)

    def _replace(match: re.Match) -> str:
        key = match.group(1)
        if key not in params:
            if strict:
                raise KeyError(f"Missing template parameter: '{key}'")
            return ""
        return _render_value(params[key])

    return _PLACEHOLDER_RE.sub(_replace, template_text)


