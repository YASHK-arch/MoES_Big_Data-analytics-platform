import os

os.environ["DB_DISABLE_POOL"] = "true"

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import pool, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

TEST_DB_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@localhost:5432/weather_platform_test",
)
os.environ["DATABASE_URL"] = TEST_DB_URL
os.environ["REDIS_URL"] = os.environ.get("TEST_REDIS_URL", "redis://localhost:6379/15")
os.environ["ENVIRONMENT"] = "test"

from app.core.config import settings  # noqa: E402

settings.ENVIRONMENT = "test"
settings.DB_DISABLE_POOL = True
settings.DATABASE_URL = TEST_DB_URL
settings.REDIS_URL = os.environ["REDIS_URL"]

from app.db import session as db_session_module  # noqa: E402

db_session_module.engine, db_session_module.async_session_factory = db_session_module.create_engine_and_session_factory()

from app.core.security import create_access_token, get_password_hash  # noqa: E402
from app.main import app  # noqa: E402
from app.models.user import User  # noqa: E402


@pytest_asyncio.fixture
async def db_session():
    """Create an isolated async database session per test with NullPool."""
    test_engine = create_async_engine(
        settings.DATABASE_URL,
        poolclass=pool.NullPool,
    )
    session_factory = async_sessionmaker(
        bind=test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    async with session_factory() as session:
        yield session

    await test_engine.dispose()


@pytest_asyncio.fixture(autouse=True)
async def seed_test_operator(db_session: AsyncSession):
    """Ensure the default operator user exists in DB for test cases."""
    stmt = select(User).where(User.email == "operator@weather-platform.gov.in")
    res = await db_session.execute(stmt)
    user = res.scalar_one_or_none()
    if not user:
        user = User(
            email="operator@weather-platform.gov.in",
            full_name="Default Test Operator",
            hashed_password=get_password_hash("EmergencyOps2026!"),
            role="OPERATOR",
            is_active=True,
        )
        db_session.add(user)
        await db_session.commit()


@pytest_asyncio.fixture
async def api_client():
    """Async HTTP test client bound to FastAPI application with default operator authorization."""
    token = create_access_token(subject="operator@weather-platform.gov.in", role="OPERATOR")
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport,
        base_url="http://testserver",
        headers={"Authorization": f"Bearer {token}"},
    ) as client:
        yield client


async def _clear_limiter_async(limiter) -> None:
    limiter.clear()
    try:
        import time
        from app.core.redis import redis_client

        bucket = int(time.time() // limiter.window_seconds)
        keys = [
            f"ratelimit:{k}:{bucket}"
            for k in (set(limiter._history.keys()) | getattr(limiter, "_active_keys", set()))
        ]
        if keys:
            await redis_client.delete(*keys)
    except Exception:
        pass
    if hasattr(limiter, "_active_keys"):
        limiter._active_keys.clear()


@pytest_asyncio.fixture(autouse=True)
async def reset_rate_limiters():
    """Ensure rate limiters do not leak state between test cases."""
    from app.core.rate_limiter import login_rate_limiter, report_rate_limiter

    await _clear_limiter_async(report_rate_limiter)
    await _clear_limiter_async(login_rate_limiter)
    yield
    await _clear_limiter_async(report_rate_limiter)
    await _clear_limiter_async(login_rate_limiter)

