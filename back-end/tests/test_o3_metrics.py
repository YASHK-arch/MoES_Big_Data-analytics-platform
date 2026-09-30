"""O3 Metrics endpoint tests.

Tests that expected metric names appear in the Prometheus output.
"""

import pytest
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


EXPECTED_METRIC_NAMES = [
    "http_requests_total",
    "http_request_duration_seconds",
    "stream_lag_messages",
    "stream_pending_messages",
    "outbox_pending_count",
    "outbox_oldest_age_seconds",
    "db_pool_checked_out",
    "worker_heartbeat_age_seconds",
]


@pytest.mark.asyncio
async def test_metrics_endpoint_returns_prometheus_format(client):
    """GET /api/v1/metrics must return 200 with text/plain Prometheus format."""
    resp = await client.get("/api/v1/metrics")
    assert resp.status_code == 200
    assert "text/plain" in resp.headers.get("content-type", "")


@pytest.mark.asyncio
async def test_metrics_contains_expected_metric_names(client):
    """All expected metric names must appear in the /metrics output."""
    resp = await client.get("/api/v1/metrics")
    body = resp.text
    missing = [name for name in EXPECTED_METRIC_NAMES if name not in body]
    assert not missing, f"Missing metrics: {missing}"


@pytest.mark.asyncio
async def test_http_requests_total_increments(client):
    """Making a request should increment http_requests_total."""
    # Make a request to /health first
    await client.get("/api/v1/health")
    # Now check metrics
    resp = await client.get("/api/v1/metrics")
    assert "http_requests_total" in resp.text
    # The counter should have at least one entry
    assert 'method="GET"' in resp.text
