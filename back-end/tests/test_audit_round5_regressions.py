import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_geo_incidents_dropped_unused_readiness(api_client: AsyncClient) -> None:
    """Verify GET /api/v1/geo/incidents returns valid FeatureCollection with unused readiness dropped."""
    resp = await api_client.get("/api/v1/geo/incidents", params={"limit": 5})
    assert resp.status_code == 200
    data = resp.json()
    assert data["type"] == "FeatureCollection"
    assert "features" in data

    if data["features"]:
        feat = data["features"][0]
        assert feat["type"] == "Feature"
        assert "geometry" in feat
        assert "properties" in feat
        props = feat["properties"]

        # Required properties used by map / frontend
        for req in ["id", "tracking_id", "title", "category_code", "severity", "credibility_score", "verification_status", "occurred_at"]:
            assert req in props, f"Missing required property {req}"

        # Dropped property
        assert "readiness" not in props, "Property 'readiness' should be omitted to reduce payload"


@pytest.mark.asyncio
async def test_geo_incidents_caching_and_ttl_0_bypass(api_client: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify GET /api/v1/geo/incidents caches in Redis, honors ETag/304, and bypasses when TTL=0."""
    from app.core.config import settings

    # 1. First request with caching enabled (TTL=10)
    monkeypatch.setattr(settings, "DASHBOARD_CACHE_TTL_SECONDS", 10)
    resp1 = await api_client.get("/api/v1/geo/incidents", params={"limit": 5})
    assert resp1.status_code == 200
    etag = resp1.headers.get("ETag")
    assert etag is not None

    # 2. 304 Not Modified when sending ETag
    resp_304 = await api_client.get("/api/v1/geo/incidents", params={"limit": 5}, headers={"If-None-Match": etag})
    assert resp_304.status_code == 304

    # 3. Second request should hit cache and return 200 with same ETag
    resp2 = await api_client.get("/api/v1/geo/incidents", params={"limit": 5})
    assert resp2.status_code == 200
    assert resp2.headers.get("ETag") == etag

    # 4. TTL=0 bypass test
    monkeypatch.setattr(settings, "DASHBOARD_CACHE_TTL_SECONDS", 0)
    resp_bypass = await api_client.get("/api/v1/geo/incidents", params={"limit": 5})
    assert resp_bypass.status_code == 200
    assert resp_bypass.headers.get("ETag") is not None

