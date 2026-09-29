"""Comprehensive API integration tests for Dashboard Summary and Analytics Trends endpoints."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token
from app.main import app
from app.models.category import EventCategory
from app.models.report import WeatherReport
from app.models.source import Source


@pytest.fixture
async def api_client():
    """Async HTTP test client bound to FastAPI application with operator authorization."""
    token = create_access_token(subject="operator@weather-platform.gov.in", role="OPERATOR")
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport,
        base_url="http://testserver",
        headers={"Authorization": f"Bearer {token}"},
    ) as client:
        yield client


@pytest.mark.asyncio
async def test_dashboard_summary_api_success_and_filters(
    api_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Test GET /api/v1/dashboard/summary default and filter combinations."""
    # Ensure source and category exist
    source_res = await db_session.execute(select(Source).limit(1))
    source = source_res.scalar_one_or_none()
    if not source:
        source = Source(
            id=uuid.uuid4(),
            source_code="TEST_DASH_API_SRC",
            source_type="CITIZEN",
            name="Test Dashboard Source",
            base_trust_score=0.5,
            is_active=True,
        )
        db_session.add(source)
        await db_session.flush()

    cat_res = await db_session.execute(
        select(EventCategory).where(EventCategory.category_code == "FLOOD_WATERLOGGING")
    )
    category = cat_res.scalar_one_or_none()
    if not category:
        category = EventCategory(
            id=uuid.uuid4(),
            category_code="FLOOD_WATERLOGGING",
            title="Flooding & Waterlogging",
            severity_default="HIGH",
            color_hex="#3b82f6",
            icon_name="droplets",
        )
        db_session.add(category)
        await db_session.flush()

    now = datetime.now(timezone.utc)
    tag = f"DASH-API-{uuid.uuid4().hex[:6].upper()}"

    r1 = WeatherReport(
        id=uuid.uuid4(),
        tracking_id=f"{tag}-1",
        source_id=source.id,
        category_id=category.id,
        reported_category="FLOOD_WATERLOGGING",
        severity="SEVERE",
        title=f"Dashboard API Test 1 {tag}",
        latitude=19.0760,
        longitude=72.8777,
        geom="SRID=4326;POINT(72.8777 19.0760)",
        occurred_at=now - timedelta(hours=2),
        verification_status="VERIFIED",
        processing_status="COMPLETED",
    )
    db_session.add(r1)
    await db_session.commit()

    # 1. Default request
    res = await api_client.get("/api/v1/dashboard/summary")
    assert res.status_code == 200
    body = res.json()
    assert body["success"] is True
    assert "data" in body
    assert "meta" in body
    data = body["data"]
    assert "total_count" in data
    assert "period_count" in data
    assert "count_24h" in data
    assert "last_24h_pct" in data
    assert "verification" in data
    assert "severity" in data
    assert "category_distribution" in data
    assert "diurnal_distribution" in data
    assert len(data["diurnal_distribution"]) == 4

    # 2. Explicit time_range variations
    for tr in ["24h", "48h", "7d", "30d", "all"]:
        r_tr = await api_client.get(f"/api/v1/dashboard/summary?time_range={tr}")
        assert r_tr.status_code == 200

    # 3. Filters: category, severity, status, bbox
    res_filtered = await api_client.get(
        "/api/v1/dashboard/summary?time_range=all&category=FLOOD_WATERLOGGING&severity=SEVERE&status=VERIFIED&bbox=72.0,18.0,73.0,20.0"
    )
    assert res_filtered.status_code == 200
    data_filtered = res_filtered.json()["data"]
    assert data_filtered["total_count"] >= 1
    assert data_filtered["verification"]["verified_count"] >= 1
    assert data_filtered["severity"]["severe_count"] >= 1


@pytest.mark.asyncio
async def test_dashboard_summary_api_validation_errors(
    api_client: AsyncClient,
) -> None:
    """Test validation errors for invalid query parameters in /api/v1/dashboard/summary."""
    # Invalid time_range
    res_tr = await api_client.get("/api/v1/dashboard/summary?time_range=invalid_range")
    assert res_tr.status_code == 422
    assert res_tr.json()["error"]["code"] == "VALIDATION_ERROR"

    # Invalid severity
    res_sev = await api_client.get("/api/v1/dashboard/summary?severity=EXTREME_CRITICAL")
    assert res_sev.status_code == 422
    assert res_sev.json()["error"]["code"] == "VALIDATION_ERROR"

    # Malformed bbox (not 4 parts)
    res_bbox1 = await api_client.get("/api/v1/dashboard/summary?bbox=72.0,18.0")
    assert res_bbox1.status_code == 422

    # Malformed bbox (non-numeric)
    res_bbox2 = await api_client.get("/api/v1/dashboard/summary?bbox=a,b,c,d")
    assert res_bbox2.status_code == 422

    # Malformed bbox (min > max)
    res_bbox3 = await api_client.get("/api/v1/dashboard/summary?bbox=73.0,19.0,72.0,18.0")
    assert res_bbox3.status_code == 422


@pytest.mark.asyncio
async def test_analytics_trends_api_success_and_filters(
    api_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Test GET /api/v1/analytics/trends default and interval variations."""
    # 1. Default request (7d daily)
    res = await api_client.get("/api/v1/analytics/trends")
    assert res.status_code == 200
    body = res.json()
    assert body["success"] is True
    assert "data" in body
    assert "meta" in body
    data = body["data"]
    assert data["time_range"] == "7d"
    assert data["interval"] == "day"
    assert len(data["buckets"]) == 7
    for b in data["buckets"]:
        assert "bucket" in b
        assert "label" in b
        assert "total" in b
        assert "verified" in b

    # 2. 24h hourly trends (6 buckets)
    res_24h = await api_client.get("/api/v1/analytics/trends?time_range=24h&interval=hour")
    assert res_24h.status_code == 200
    data_24h = res_24h.json()["data"]
    assert data_24h["time_range"] == "24h"
    assert data_24h["interval"] == "hour"
    assert len(data_24h["buckets"]) == 6

    # 3. 30d daily trends (14 buckets)
    res_30d = await api_client.get("/api/v1/analytics/trends?time_range=30d&interval=day")
    assert res_30d.status_code == 200
    data_30d = res_30d.json()["data"]
    assert data_30d["time_range"] == "30d"
    assert len(data_30d["buckets"]) == 14

    # 4. Filters with bbox
    res_filt = await api_client.get(
        "/api/v1/analytics/trends?time_range=7d&bbox=72.0,18.0,73.0,20.0&severity=HIGH"
    )
    assert res_filt.status_code == 200


@pytest.mark.asyncio
async def test_analytics_trends_api_validation_errors(
    api_client: AsyncClient,
) -> None:
    """Test validation errors for invalid query parameters in /api/v1/analytics/trends."""
    # Invalid time_range (e.g. 48h is not in analytics UI time ranges)
    res_tr = await api_client.get("/api/v1/analytics/trends?time_range=48h")
    assert res_tr.status_code == 422
    assert res_tr.json()["error"]["code"] == "VALIDATION_ERROR"

    # Invalid interval
    res_int = await api_client.get("/api/v1/analytics/trends?interval=minute")
    assert res_int.status_code == 422
    assert res_int.json()["error"]["code"] == "VALIDATION_ERROR"

    # Malformed bbox
    res_bbox = await api_client.get("/api/v1/analytics/trends?bbox=bad_bbox")
    assert res_bbox.status_code == 422


@pytest.mark.asyncio
async def test_backward_compatibility_existing_routes(
    api_client: AsyncClient,
) -> None:
    """Verify that existing critical endpoints remain intact and functional."""
    # 1. Health check
    res_health = await api_client.get("/api/v1/health")
    assert res_health.status_code == 200
    assert res_health.json()["success"] is True

    # 2. Incidents listing
    res_incidents = await api_client.get("/api/v1/incidents?page=1&page_size=5")
    assert res_incidents.status_code == 200
    assert res_incidents.json()["success"] is True

    # 3. Geo incidents
    res_geo = await api_client.get("/api/v1/geo/incidents?bbox=72.0,18.0,73.0,20.0")
    assert res_geo.status_code == 200
    assert res_geo.json()["type"] == "FeatureCollection"

    # 4. Verification queue
    res_ver = await api_client.get("/api/v1/verification/queue?page=1&page_size=5")
    assert res_ver.status_code == 200
    assert res_ver.json()["success"] is True


@pytest.mark.asyncio
async def test_analytics_regional_api_success_and_filters(
    api_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Test GET /api/v1/analytics/regional default, time_range variations, and filter parameters."""
    # 1. Default request (7d)
    res = await api_client.get("/api/v1/analytics/regional")
    assert res.status_code == 200
    body = res.json()
    assert body["success"] is True
    assert "data" in body
    assert "meta" in body
    data = body["data"]
    assert data["time_range"] == "7d"
    assert isinstance(data["total_classified"], int)
    assert isinstance(data["regions"], list)
    for reg in data["regions"]:
        assert "region_code" in reg
        assert "region_name" in reg
        assert "count" in reg
        assert "percentage" in reg
        assert reg["count"] >= 0
        assert 0 <= reg["percentage"] <= 100

    # 2. Time range variations
    for tr in ["24h", "7d", "30d", "all"]:
        r_tr = await api_client.get(f"/api/v1/analytics/regional?time_range={tr}")
        assert r_tr.status_code == 200
        assert r_tr.json()["data"]["time_range"] == tr

    # 3. Filter combinations
    res_filt = await api_client.get(
        "/api/v1/analytics/regional?time_range=7d&severity=SEVERE&status=VERIFIED&bbox=72.0,18.0,74.0,20.0"
    )
    assert res_filt.status_code == 200
    assert res_filt.json()["success"] is True


@pytest.mark.asyncio
async def test_analytics_regional_api_validation_errors(
    api_client: AsyncClient,
) -> None:
    """Test validation errors for invalid query parameters in /api/v1/analytics/regional."""
    # Invalid time_range (e.g. 48h is not in analytics UI time ranges)
    res_tr = await api_client.get("/api/v1/analytics/regional?time_range=48h")
    assert res_tr.status_code == 422
    assert res_tr.json()["error"]["code"] == "VALIDATION_ERROR"

    # Invalid severity
    res_sev = await api_client.get("/api/v1/analytics/regional?severity=SUPER_CRITICAL")
    assert res_sev.status_code == 422
    assert res_sev.json()["error"]["code"] == "VALIDATION_ERROR"

    # Malformed bbox
    res_bbox = await api_client.get("/api/v1/analytics/regional?bbox=not_a_valid_bbox")
    assert res_bbox.status_code == 422
