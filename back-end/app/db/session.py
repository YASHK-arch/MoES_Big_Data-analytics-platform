from typing import Any, AsyncGenerator, Dict, Tuple

from sqlalchemy import pool
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings


def get_engine_kwargs() -> Dict[str, Any]:
    kwargs: Dict[str, Any] = {
        "echo": settings.DATABASE_ECHO,
        "future": True,
        "pool_pre_ping": True,
    }
    if settings.DB_DISABLE_POOL:
        kwargs["poolclass"] = pool.NullPool
    else:
        kwargs["pool_size"] = settings.DB_POOL_SIZE
        kwargs["max_overflow"] = settings.DB_MAX_OVERFLOW
        kwargs["pool_timeout"] = settings.DB_POOL_TIMEOUT
        kwargs["pool_recycle"] = settings.DB_POOL_RECYCLE
    return kwargs


def create_engine_and_session_factory() -> Tuple[AsyncEngine, async_sessionmaker[AsyncSession]]:
    eng = create_async_engine(
        settings.DATABASE_URL,
        **get_engine_kwargs(),
    )
    factory = async_sessionmaker(
        bind=eng,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )
    return eng, factory


engine, async_session_factory = create_engine_and_session_factory()


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency for providing asynchronous database sessions to FastAPI endpoints."""
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
