from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi import Request
from starlette.middleware.cors import CORSMiddleware
from starlette.templating import Jinja2Templates

from core import settings
from router.v1_router import combine_router
from router.various.various_router import router as various_router

from database.base import async_engine
from database.models import Base


HOST = getattr(settings, "HOST", None) or "0.0.0.0"
PORT = int(getattr(settings, "PORT", None) or 8000)


templates = Jinja2Templates(directory="templates")


async def startup_event():
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def shutdown_event():
    pass


@asynccontextmanager
async def lifespan(app: FastAPI):

    await startup_event()
    yield
    await shutdown_event()
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    debug=settings.DEBUG,
    lifespan=lifespan,
)
ALLOWED_ORIGINS = [
    "http://localhost:5173",    # Vite 默认地址
    "http://10.0.0.44:5173",
    "http://dict.yourcompany.com" # 生产环境域名
]
# 配置 CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

# Include routers
app.include_router(combine_router)

