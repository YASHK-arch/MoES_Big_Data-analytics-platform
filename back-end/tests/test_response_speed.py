"""Tests for response speed optimizations: GZip compression, ORJSONResponse, and GeoJSON ETag caching."""

import pytest
from fastapi.responses import ORJSONResponse
from httpx import ASGITransport, AsyncClient

from app.main import app


def test_orjson_response_is_default_response_class():
    """Verify ORJSONResponse is configured as the default response class for FastAPI."""
    assert app.router.default_response_class is ORJSONResponse


@pytest.mark.asyncio
async def test_gzip_compression_applied_on_large_payload():
    """Verify GZipMiddleware compresses response when Accept-Encoding: gzip is sent."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        # Request openapi schema or large endpoint which exceeds 1000 bytes
        response = await client.get("/api/v1/openapi.json", headers={"Accept-Encoding": "gzip"})
        assert response.status_code == 200
        assert response.headers.get("content-encoding") == "gzip"


@pytest.mark.asyncio
async def test_geojson_etag_and_cache_control(api_client: AsyncClient):
    """Verify GeoJSON endpoints return Cache-Control and ETag headers, and honor If-None-Match with 304."""
    # First request
    res1 = await api_client.get("/api/v1/geo/incidents")
    assert res1.status_code == 200
    etag = res1.headers.get("etag")
    cache_control = res1.headers.get("cache-control")

    assert etag is not None
    assert "public" in cache_control
    assert "max-age=30" in cache_control

    # Second request with matching If-None-Match
    res2 = await api_client.get("/api/v1/geo/incidents", headers={"If-None-Match": etag})
    assert res2.status_code == 304
    assert res2.headers.get("etag") == etag
    assert "public, max-age=30" in res2.headers.get("cache-control", "")
