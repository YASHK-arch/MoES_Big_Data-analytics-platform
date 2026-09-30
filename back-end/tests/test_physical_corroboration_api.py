"""Tests for Physical Corroboration API serialization, P7 fields, and payload size."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token
from app.intelligence.physical_corroboration.config import default_physical_config
from app.intelligence.physical_corroboration.evaluator import evaluate
from app.intelligence.physical_corroboration.models import (
    PhysicalCorroborationVerdict,
    PhysicalObservation,
    PhysicalSourceType,
)
from app.main import app
from app.models.corroboration import IncidentPhysicalCorroboration
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
async def test_incident_detail_physical_corroboration_p7_fields(
    api_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Verify incident detail returns physical_corroboration block with all P7 explainability fields."""
    uid = uuid.uuid4().hex[:8]
    source = Source(
        source_code=f"SRC_P7_{uid}",
        name="Physical API Test Source",
        source_type="CITIZEN_REPORT",
        base_trust_score=0.70,
        is_active=True,
    )
    db_session.add(source)
    await db_session.flush()

    report = WeatherReport(
        tracking_id=f"RPT-P7-{uid}",
        source_id=source.id,
        title="Severe Rainfall in Central Ward",
        description="Streets flooded after continuous downpour",
        location_name="Connaught Place, New Delhi",
        reported_category="HEAVY_RAINFALL",
        severity="HIGH",
        latitude=28.6315,
        longitude=77.2167,
        occurred_at=datetime.now(timezone.utc),
        geom="SRID=4326;POINT(77.2167 28.6315)",
        processing_status="COMPLETED",
        verification_status="PENDING",
        credibility_score=0.8200,
    )
    db_session.add(report)
    await db_session.flush()

    corrob = IncidentPhysicalCorroboration(
        incident_id=report.id,
        variable="rainfall_1h",
        observed_value=72.4,
        unit="mm/1h",
        source="OPEN_METEO",
        source_type="MODEL",
        station_or_grid_id="grid_28.63_77.22",
        distance_km=1.25,
        time_gap_h=0.5,
        verdict="SUPPORTS",
        weight=0.60,
        contribution=0.0825,
        provider_status="OK",
        observation_time=datetime.now(timezone.utc),
        explanation="Rainfall 72.4 mm/1h exceeds heavy rainfall threshold (64.5 mm)",
        is_simulated=False,
    )
    db_session.add(corrob)
    await db_session.commit()

    res = await api_client.get(f"/api/v1/reports/{report.tracking_id}")
    assert res.status_code == 200
    data = res.json()["data"]

    # Top-level compact verdict
    assert data["physical_verdict"] == "SUPPORTS"

    # Full P7 explainable block
    block = data["physical_corroboration"]
    assert block is not None
    assert block["overall_verdict"] == "SUPPORTS"
    assert block["overall_provider_status"] == "OK"
    assert block["total_contribution"] == 0.0825
    assert block["is_simulated"] is False
    assert len(block["items"]) == 1

    item = block["items"][0]
    # Product Rule P7 field assertions
    assert item["variable"] == "rainfall_1h"
    assert item["observed_value"] == 72.4
    assert item["unit"] == "mm/1h"
    assert item["source"] == "OPEN_METEO"
    assert item["source_type"] == "MODEL"
    assert item["station_or_grid_id"] == "grid_28.63_77.22"
    assert item["distance_km"] == 1.25
    assert item["time_gap_hours"] == 0.5
    assert item["verdict"] == "SUPPORTS"
    assert item["weight"] == 0.60
    assert item["contribution"] == 0.0825
    assert item["provider_status"] == "OK"
    assert item["observation_time"] is not None
    assert "exceeds heavy rainfall threshold" in item["explanation"]
    assert item["is_simulated"] is False


@pytest.mark.asyncio
async def test_incident_detail_neutral_with_reason_on_provider_outage(
    api_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Verify provider timeout/failure results in NEUTRAL with plain-language explanation (P2)."""
    uid = uuid.uuid4().hex[:8]
    source = Source(
        source_code=f"SRC_NEUT_{uid}",
        name="Outage Test Source",
        source_type="CITIZEN_REPORT",
        base_trust_score=0.60,
        is_active=True,
    )
    db_session.add(source)
    await db_session.flush()

    report = WeatherReport(
        tracking_id=f"RPT-NEUT-{uid}",
        source_id=source.id,
        title="High Wind in Coastal Sector",
        description="Roof damaged by gale",
        location_name="Puri, Odisha",
        reported_category="GALE_WIND",
        severity="HIGH",
        latitude=19.8135,
        longitude=85.8312,
        occurred_at=datetime.now(timezone.utc),
        geom="SRID=4326;POINT(85.8312 19.8135)",
        processing_status="COMPLETED",
        verification_status="PENDING",
        credibility_score=0.6000,
    )
    db_session.add(report)
    await db_session.flush()

    corrob = IncidentPhysicalCorroboration(
        incident_id=report.id,
        variable="wind_speed",
        observed_value=None,
        unit="km/h",
        source="OPEN_METEO",
        source_type="MODEL",
        station_or_grid_id=None,
        distance_km=None,
        time_gap_h=None,
        verdict="NEUTRAL",
        weight=0.60,
        contribution=0.0,
        provider_status="TIMEOUT",
        observation_time=datetime.now(timezone.utc),
        explanation="Provider timeout after 5.0s; fell back to NEUTRAL without score penalty",
        is_simulated=False,
    )
    db_session.add(corrob)
    await db_session.commit()

    res = await api_client.get(f"/api/v1/reports/{report.tracking_id}")
    assert res.status_code == 200
    data = res.json()["data"]

    assert data["physical_verdict"] == "NEUTRAL"
    block = data["physical_corroboration"]
    assert block["overall_verdict"] == "NEUTRAL"
    assert block["overall_provider_status"] == "TIMEOUT"
    assert block["total_contribution"] == 0.0

    item = block["items"][0]
    assert item["verdict"] == "NEUTRAL"
    assert item["provider_status"] == "TIMEOUT"
    assert item["observed_value"] is None
    assert "fell back to NEUTRAL" in item["explanation"]


@pytest.mark.asyncio
async def test_flood_category_never_contradicts_in_api(
    api_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Verify Product Rule P3: Flood category never returns CONTRADICTS even when rainfall is 0.0."""
    # 1. Pure evaluator verification
    obs = PhysicalObservation(
        source_name="OPEN_METEO",
        source_type=PhysicalSourceType.MODEL,
        station_or_grid_id="grid_13.08_80.27",
        latitude=12.9815,
        longitude=80.2180,
        observed_at=datetime.now(timezone.utc),
        rainfall_1h_mm=0.0,
    )
    now = datetime.now(timezone.utc)
    result = evaluate(
        category="FLOOD_WATERLOGGING",
        observation=obs,
        incident_time=now,
        incident_coords=(12.9815, 80.2180),
        config=default_physical_config,
    )
    assert result.verdict == PhysicalCorroborationVerdict.NEUTRAL
    assert result.verdict != PhysicalCorroborationVerdict.CONTRADICTS
    assert "does not contradict flood" in result.explanation.lower()

    # 2. API response verification
    uid = uuid.uuid4().hex[:8]
    source = Source(
        source_code=f"SRC_FLD_{uid}",
        name="Flood Test Source",
        source_type="CITIZEN_REPORT",
        base_trust_score=0.60,
        is_active=True,
    )
    db_session.add(source)
    await db_session.flush()

    report = WeatherReport(
        tracking_id=f"RPT-FLD-{uid}",
        source_id=source.id,
        title="Severe Waterlogging in Low-Lying Area",
        description="2 feet of water on residential roads",
        location_name="Velachery, Chennai",
        reported_category="FLOOD_WATERLOGGING",
        severity="HIGH",
        latitude=12.9815,
        longitude=80.2180,
        occurred_at=datetime.now(timezone.utc),
        geom="SRID=4326;POINT(80.2180 12.9815)",
        processing_status="COMPLETED",
        verification_status="PENDING",
        credibility_score=0.6500,
    )
    db_session.add(report)
    await db_session.flush()

    corrob = IncidentPhysicalCorroboration(
        incident_id=report.id,
        variable="rainfall_1h",
        observed_value=0.0,
        unit="mm/1h",
        source="OPEN_METEO",
        source_type="MODEL",
        station_or_grid_id="grid_13.08_80.27",
        distance_km=2.0,
        time_gap_h=0.5,
        verdict="NEUTRAL",
        weight=0.60,
        contribution=0.0,
        provider_status="OK",
        observation_time=datetime.now(timezone.utc),
        explanation=result.explanation,
        is_simulated=False,
    )
    db_session.add(corrob)
    await db_session.commit()

    res = await api_client.get(f"/api/v1/reports/{report.tracking_id}")
    assert res.status_code == 200
    data = res.json()["data"]

    assert data["physical_verdict"] == "NEUTRAL"
    assert data["physical_verdict"] != "CONTRADICTS"
    assert data["physical_corroboration"]["overall_verdict"] == "NEUTRAL"


@pytest.mark.asyncio
async def test_measure_payload_byte_size_change(
    api_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Measure API payload byte size before vs after adding physical corroboration fields."""
    res = await api_client.get("/api/v1/reports?page=1&page_size=20")
    assert res.status_code == 200
    body = res.json()
    total_bytes = len(res.content)
    item_count = len(body["data"])

    # Simulate legacy payload by stripping physical corroboration fields from each item
    legacy_items = []
    for item in body["data"]:
        legacy_item = dict(item)
        legacy_item.pop("physical_corroboration", None)
        legacy_item.pop("physical_verdict", None)
        legacy_items.append(legacy_item)

    legacy_payload = {
        "success": body["success"],
        "data": legacy_items,
        "pagination": body["pagination"],
        "meta": body["meta"],
    }
    legacy_bytes = len(json.dumps(legacy_payload).encode("utf-8"))
    diff_bytes = total_bytes - legacy_bytes
    per_item_bytes = diff_bytes / max(item_count, 1)

    print(
        f"\n[Payload Measurement] Total bytes: {total_bytes}, "
        f"Legacy bytes: {legacy_bytes}, Diff: {diff_bytes} bytes, "
        f"Per item overhead: {per_item_bytes:.1f} bytes across {item_count} items."
    )

    # Overhead for adding physical_verdict and physical_corroboration block should be reasonable
    # (less than 600 bytes per item even when full corroboration block and explanation are present)
    assert per_item_bytes < 600
