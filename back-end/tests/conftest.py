"""Shared pytest fixtures for the weather platform test suite."""

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import pool, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.core.security import create_access_token, get_password_hash
from app.main import app
from app.models.user import User


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
