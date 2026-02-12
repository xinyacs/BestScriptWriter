"""
数据库连接配置模块

只负责数据库引擎和会话工厂的创建，不包含业务逻辑
"""

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import declarative_base

from core import settings

# 创建异步数据库引擎
async_engine = create_async_engine(
    settings.async_database_url,
    pool_pre_ping=True,  # 连接前检查连接是否有效
    pool_size=10,
    max_overflow=20,
    echo=settings.DEBUG,  # 在调试模式下打印 SQL
    future=True,
)

# 创建异步会话工厂
AsyncSessionLocal = async_sessionmaker(
    async_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)

# 创建基础模型类
Base = declarative_base()


