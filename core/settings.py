import os
from pathlib import Path

try:
    from dotenv import load_dotenv  # type: ignore
except Exception:
    load_dotenv = None


_ROOT_DIR = Path(__file__).resolve().parents[1]
_DOTENV_PATH = _ROOT_DIR / ".env"
if load_dotenv is not None:
    load_dotenv(dotenv_path=_DOTENV_PATH, override=False)


def _env_bool(key: str, default: bool) -> bool:
    v = os.getenv(key)
    if v is None:
        return default
    return v.strip().lower() in {"1", "true", "yes", "y", "on"}


# App 基础信息
APP_NAME = os.getenv("APP_NAME", "SuperDraft")
APP_VERSION = os.getenv("APP_VERSION", "0.01")
DEBUG = _env_bool("DEBUG", True)


# Server
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8000"))



# 数据库
async_database_url = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./app.db")



# LLM / OpenAI 兼容接口
OPENAI_HOST = os.getenv("OPENAI_HOST", "")
OPENAI_KEY = os.getenv("OPENAI_KEY", "")


# Agent / Workflow 模型选择
# - L0_AGENT_MODEL: 代理模型 0
# - L1_AGENT_MODEL: 代理模型 1
L0_AGENT_MODEL = os.getenv("L0_AGENT_MODEL", "qwen/qwen3-235b-a22b")
L1_AGENT_MODEL = os.getenv("L1_AGENT_MODEL", "moonshotai/kimi-k2.5")


# 文件上传与解析
# - FILE_UPLOAD_DIR: 上传文件落盘目录（用于 save_image 等）
# - FILE_MAX_BYTES: 单文件大小限制（bytes）
# - FILE_PARSE_TIMEOUT_S: 单次解析超时（秒）
# - FILE_MAX_CONCURRENCY: 解析最大并发（默认=CPU 核心数；兜底 4）
# - FILE_IMAGE_PREFIX: 判定图片的 MIME 前缀（安全策略会用到）
# - FILE_MAX_IMAGES: 单次请求最多允许上传的图片数量
# - FILE_MAX_IMAGE_BYTES: 单张图片大小限制（bytes）
# - FILE_IMAGE_STREAM_CHUNK_BYTES: 图片落盘时的分块大小（bytes），用于控制内存占用
FILE_UPLOAD_DIR = Path(os.getenv("FILE_UPLOAD_DIR", "./uploads"))
FILE_MAX_BYTES = int(os.getenv("FILE_MAX_BYTES", str(25 * 1024 * 1024)))
FILE_PARSE_TIMEOUT_S = int(os.getenv("FILE_PARSE_TIMEOUT_S", "20"))
FILE_MAX_CONCURRENCY = int(os.getenv("FILE_MAX_CONCURRENCY", str(os.cpu_count() or 4)))
FILE_IMAGE_PREFIX = os.getenv("FILE_IMAGE_PREFIX", "image/")
FILE_MAX_IMAGES = int(os.getenv("FILE_MAX_IMAGES", "6"))
FILE_MAX_IMAGE_BYTES = int(os.getenv("FILE_MAX_IMAGE_BYTES", str(10 * 1024 * 1024)))
FILE_IMAGE_STREAM_CHUNK_BYTES = int(os.getenv("FILE_IMAGE_STREAM_CHUNK_BYTES", str(1024 * 1024)))