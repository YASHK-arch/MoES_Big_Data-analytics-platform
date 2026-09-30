"""Tests for database connection pooling and connection reuse."""

from unittest.mock import patch

import pytest
from sqlalchemy import text

from app.core.config import settings
from app.db.session import create_engine_and_session_factory, get_engine_kwargs


def test_db_pool_kwargs_configuration():
    """Verify pool parameters and NullPool fallback when DB_DISABLE_POOL is toggled."""
    with patch.object(settings, "DB_DISABLE_POOL", True):
        kwargs = get_engine_kwargs()
        from sqlalchemy import pool

        assert kwargs["poolclass"] is pool.NullPool

    with patch.object(settings, "DB_DISABLE_POOL", False):
        with patch.object(settings, "DB_POOL_SIZE", 12):
            with patch.object(settings, "DB_MAX_OVERFLOW", 25):
                with patch.object(settings, "DB_POOL_TIMEOUT", 35):
                    with patch.object(settings, "DB_POOL_RECYCLE", 1900):
                        kwargs = get_engine_kwargs()
                        assert "poolclass" not in kwargs
                        assert kwargs["pool_size"] == 12
                        assert kwargs["max_overflow"] == 25
                        assert kwargs["pool_timeout"] == 35
                        assert kwargs["pool_recycle"] == 1900
                        assert kwargs["pool_pre_ping"] is True


@pytest.mark.asyncio
async def test_sequential_requests_reuse_connection_when_pool_enabled():
    """Verify that two sequential requests reuse the same PostgreSQL connection backend PID when pooling is enabled."""
    with patch.object(settings, "DB_DISABLE_POOL", False):
        pool_engine, pool_factory = create_engine_and_session_factory()
        try:
            # First request / session
            async with pool_factory() as session1:
                res1 = await session1.execute(text("SELECT pg_backend_pid()"))
                pid1 = res1.scalar()

            # Second sequential request / session
            async with pool_factory() as session2:
                res2 = await session2.execute(text("SELECT pg_backend_pid()"))
                pid2 = res2.scalar()

            # When pool is enabled, the connection returned to the pool is reused by the next request
            assert pid1 is not None
            assert pid2 is not None
            assert pid1 == pid2, f"Expected same connection PID to be reused, got {pid1} and {pid2}"
        finally:
            await pool_engine.dispose()
