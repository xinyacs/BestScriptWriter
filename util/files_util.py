import asyncio
import uuid

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from typing import Optional, Tuple
from pathlib import Path
import json

from starlette.concurrency import run_in_threadpool

from core import settings

TEXT_EXTS = {".txt", ".md", ".csv", ".json"}
DOCX_EXTS = {".docx"}
PDF_EXTS = {".pdf"}
UPLOAD_DIR = settings.FILE_UPLOAD_DIR
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

IMAGE_PREFIX = settings.FILE_IMAGE_PREFIX

MAX_BYTES = settings.FILE_MAX_BYTES
PARSE_TIMEOUT_S = settings.FILE_PARSE_TIMEOUT_S
MAX_CONCURRENCY = settings.FILE_MAX_CONCURRENCY
_parse_sem = asyncio.Semaphore(MAX_CONCURRENCY)


def _ext(filename: str | None) -> str:
    return Path(filename).suffix.lower() if filename else ""


async def save_image(file: UploadFile) -> str:
    if not (file.content_type or "").startswith(IMAGE_PREFIX):
        raise HTTPException(status_code=400, detail=f"不是图片类型: {file.content_type}")

    ext = _ext(file.filename) or ".png"
    name = f"{uuid.uuid4().hex}{ext}"
    path = UPLOAD_DIR / name

    max_image_bytes = getattr(settings, "FILE_MAX_IMAGE_BYTES", None) or MAX_BYTES
    chunk_size = getattr(settings, "FILE_IMAGE_STREAM_CHUNK_BYTES", 1024 * 1024)

    total = 0
    try:
        with path.open("wb") as f:
            while True:
                chunk = await file.read(chunk_size)
                if not chunk:
                    break
                total += len(chunk)
                if total > max_image_bytes:
                    raise HTTPException(
                        status_code=413,
                        detail=f"图片过大：{total/(1024*1024):.1f}MB，限制 {max_image_bytes/(1024*1024):.0f}MB",
                    )
                f.write(chunk)

        if total == 0:
            raise HTTPException(status_code=400, detail="图片为空")

        return str(path)
    except Exception:
        try:
            if path.exists():
                path.unlink()
        except Exception:
            pass
        raise


def _decode_text(raw: bytes) -> str:
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("latin-1", errors="replace")


def _markitdown_convert(filename: str, raw: bytes) -> str:
    """
    同步函数：给 run_in_threadpool 调用
    """
    try:
        from markitdown import MarkItDown
    except Exception as e:
        raise RuntimeError(
            "MarkItDown 未安装：pip install markitdown"
        ) from e

    # MarkItDown 支持从文件路径/URL/bytes等多种输入方式。
    # 这里用临时文件最通用，避免不同版本 API 差异导致踩坑。
    import tempfile, os

    md = MarkItDown()

    suffix = _ext(filename) or ""
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(raw)
        tmp.flush()
        tmp_path = tmp.name

    try:
        result = md.convert(tmp_path)
        # 不同版本 result 可能是对象/字符串；做兼容
        text = getattr(result, "text_content", None) or getattr(result, "text", None) or str(result)
        return text.strip()
    finally:
        try:
            os.remove(tmp_path)
        except Exception:
            pass


async def file_to_text(file: UploadFile) -> str:
    ext = _ext(file.filename)
    raw = await file.read()

    if (file.content_type or "").startswith(IMAGE_PREFIX):
        raise HTTPException(status_code=400, detail="出于安全考虑，不支持将图片转换为文本")

    # 1) 大小限制（性能/安全）
    if len(raw) > MAX_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"文件过大：{len(raw)/(1024*1024):.1f}MB，限制 {MAX_BYTES/(1024*1024):.0f}MB",
        )

    # 2) 纯文本类：仍走快速路径（更快、更省）
    if ext in TEXT_EXTS:
        s = _decode_text(raw)
        if ext == ".json":
            try:
                obj = json.loads(s)
                return json.dumps(obj, ensure_ascii=False, indent=2)
            except Exception:
                return s
        return s

    # 3) 其他：统一走 MarkItDown（PDF/DOCX/PPTX/XLSX/图片...）
    #    加并发限制 + 超时，避免阻塞/拖垮服务
    async with _parse_sem:
        try:
            return await asyncio.wait_for(
                run_in_threadpool(_markitdown_convert, file.filename, raw),
                timeout=PARSE_TIMEOUT_S,
            )
        except asyncio.TimeoutError:
            raise HTTPException(
                status_code=408,
                detail=f"解析超时（>{PARSE_TIMEOUT_S}s），建议缩小文件或改为后台任务队列",
            )
        except RuntimeError as e:
            # MarkItDown 未安装等
            raise HTTPException(status_code=500, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"解析失败: {type(e).__name__}: {e}")