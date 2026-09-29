"""Tests for Redis single-flight dashboard caching and key generation."""

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

from app.core.cache import generate_cache_key, get_or_compute


def test_generate_cache_key_different_filters_different_keys():
    """Verify different query filters generate different sha256 cache keys while maintaining sorting stability."""
    key1 = generate_cache_key("dashboard:summary", {"category": "FLOOD", "time_range": "24h"})
    key2 = generate_cache_key("dashboard:summary", {"time_range": "24h", "category": "FLOOD"})
    key3 = generate_cache_key("dashboard:summary", {"category": "CYCLONE", "time_range": "24h"})

    # Order of dict keys does not matter
    assert key1 == key2
    # Different filter values produce different keys
    assert key1 != key3


@pytest.mark.asyncio
async def test_second_request_hits_cache_without_recomputing():
    """Verify that a second identical request within TTL hits the cache without calling compute_fn."""
    mock_compute = AsyncMock(return_value={"total_count": 42, "status": "computed"})

    endpoint = f"test:endpoint:{uuid.uuid4().hex[:8]}"
    params = {"time_range": "24h"}

    # 1. First call computes and caches
    res1 = await get_or_compute(endpoint, params, mock_compute, ttl=10)
    assert res1 == {"total_count": 42, "status": "computed"}
    assert mock_compute.await_count == 1

    # 2. Second identical request within TTL hits cache
    res2 = await get_or_compute(endpoint, params, mock_compute, ttl=10)
    assert res2 == {"total_count": 42, "status": "computed"}
    # compute_fn was NOT called a second time
    assert mock_compute.await_count == 1

    # 3. Request with different filter calls compute_fn
    different_params = {"time_range": "7d"}
    res3 = await get_or_compute(endpoint, different_params, mock_compute, ttl=10)
    assert res3 == {"total_count": 42, "status": "computed"}
    assert mock_compute.await_count == 2


@pytest.mark.asyncio
async def test_cache_fails_open_on_redis_error():
    """Verify cache executes compute_fn directly if Redis raises an error."""
    mock_compute = AsyncMock(return_value={"total_count": 99})

    with patch("app.core.redis.redis_client.get", new_callable=AsyncMock) as mock_get:
        mock_get.side_effect = ConnectionError("Redis is offline")
        result = await get_or_compute("test:failopen", {"key": "val"}, mock_compute)
        assert result == {"total_count": 99}
        assert mock_compute.await_count == 1


@pytest.mark.asyncio
async def test_api_dashboard_summary_caching(api_client: AsyncClient):
    """Verify API endpoints return valid response and hit cache across sequential requests."""
    res1 = await api_client.get("/api/v1/dashboard/summary?time_range=24h")
    assert res1.status_code == 200
    data1 = res1.json()

    res2 = await api_client.get("/api/v1/dashboard/summary?time_range=24h")
    assert res2.status_code == 200
    data2 = res2.json()

    assert data1["data"]["total_count"] == data2["data"]["total_count"]
