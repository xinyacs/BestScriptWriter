"""
依赖注入模块

集中管理所有 FastAPI 依赖注入函数
"""

from typing import AsyncGenerator, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from database.base import AsyncSessionLocal


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    获取异步数据库会话依赖注入

    用于 FastAPI 的路由依赖，自动处理事务提交和回滚

    使用示例:
        from app.core.dependencies import get_db
        from sqlalchemy.ext.asyncio import AsyncSession

        @router.get("/items")
        async def get_items(db: AsyncSession = Depends(get_db)):
            # 使用 db 进行数据库操作
            pass
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def get_db_session() -> AsyncSession:
    """
    直接获取数据库会话（不自动提交）

    用于需要手动控制事务的场景

    使用示例:
        async with await get_db_session() as session:
            # 手动控制事务
            await session.commit()
    """
    return AsyncSessionLocal()

