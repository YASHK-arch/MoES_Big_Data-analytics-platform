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
