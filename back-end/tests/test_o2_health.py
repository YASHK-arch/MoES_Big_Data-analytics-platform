"""O2 Health endpoint tests.

Tests:
  - GET /health returns 200 with no external deps
  - GET /ready returns 200 when DB+Redis are up
  - GET /ready returns 503 when Redis is unreachable (mocked)
  - GET /health/workers lists expected workers
"""

import pytest
from unittest.mock import AsyncMock, patch
from httpx import AsyncClient, ASGITransport

from app.main import create_application


@pytest.fixture
def app():
    return create_application()


@pytest.fixture
async def client(app):
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac


@pytest.mark.asyncio
async def test_health_liveness(client):
    """GET /health must return 200 without touching DB or Redis."""
    resp = await client.get("/api/v1/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["data"]["status"] == "healthy"


@pytest.mark.asyncio
async def test_ready_ok(client):
    """GET /ready returns 200 when DB and Redis are reachable."""
    resp = await client.get("/api/v1/ready")
    assert resp.status_code == 200
    body = resp.json()
    assert body["data"]["status"] == "ready"
    assert body["data"]["checks"]["database"] == "ok"
    assert body["data"]["checks"]["redis"] == "ok"


@pytest.mark.asyncio
async def test_ready_503_when_redis_down(client):
    """GET /ready returns 503 naming 'redis' when Redis PING raises."""
    with patch(
        "app.api.v1.health.redis_client.ping",
        new_callable=AsyncMock,
        side_effect=ConnectionRefusedError("Redis unreachable"),
    ):
        resp = await client.get("/api/v1/ready")
    assert resp.status_code == 503
    body = resp.json()
    assert body["data"]["failing_check"] == "redis"


@pytest.mark.asyncio
async def test_ready_503_when_db_down(client):
    """GET /ready returns 503 naming 'database' when DB execute raises."""
    with patch(
        "app.api.v1.health.async_session_factory",
        side_effect=Exception("DB unreachable"),
    ):
        resp = await client.get("/api/v1/ready")
    assert resp.status_code == 503
    body = resp.json()
    assert body["data"]["failing_check"] == "database"


@pytest.mark.asyncio
async def test_worker_health_lists_expected_workers(client):
    """GET /health/workers lists all 6 expected worker names."""
    expected = {"outbox", "dispatcher", "ingestion", "observation", "evidence", "scheduler"}
    resp = await client.get("/api/v1/health/workers")
    assert resp.status_code == 200
    body = resp.json()
    assert set(body["data"]["workers"].keys()) == expected


@pytest.mark.asyncio
async def test_heartbeat_redis_key_written():
    """heartbeat_loop writes Redis key worker:heartbeat:<name> with TTL 30s."""
    import asyncio
    from app.workers.heartbeat import heartbeat_loop
    from app.core.redis import redis_client

    stop_event = asyncio.Event()
    # Run one iteration only
    task = asyncio.create_task(heartbeat_loop("test_worker", stop_event))
    await asyncio.sleep(0.2)
    stop_event.set()
    await task

    ttl = await redis_client.ttl("worker:heartbeat:test_worker")
    assert ttl > 0, f"Expected TTL > 0, got {ttl}"
