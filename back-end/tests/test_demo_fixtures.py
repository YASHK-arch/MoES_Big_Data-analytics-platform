"""Tests for deterministic demo fixture provider and simulated observation labeling."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import create_access_token
from app.intelligence.physical_corroboration.config import default_physical_config
from app.intelligence.physical_corroboration.evaluator import evaluate
from app.intelligence.physical_corroboration.models import (
    PhysicalCorroborationVerdict,
    PhysicalSourceType,
    ProviderStatus,
)
from app.intelligence.physical_corroboration.providers.fixture_provider import (
    FixtureWeatherProvider,
)
from app.intelligence.physical_corroboration.service import (
    PhysicalCorroborationService,
)
from app.main import app
from app.models.report import WeatherReport
from app.models.source import Source


@pytest.fixture
async def api_client():
    token = create_access_token(subject="operator@weather-platform.gov.in", role="OPERATOR")
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport,
        base_url="http://testserver",
        headers={"Authorization": f"Bearer {token}"},
    ) as client:
        yield client


@pytest.mark.asyncio
async def test_demo_fixture_provider_deterministic_scenarios() -> None:
    """Verify FixtureWeatherProvider returns deterministic SUPPORTS, CONTRADICTS, and NEUTRAL scenarios."""
    provider = FixtureWeatherProvider()
    target_time = datetime.now(timezone.utc)

    # 1. SUPPORTS scenario (Heavy rainfall)
    obs_sup, status_sup, err_sup = await provider.fetch_observation(
        lat=28.6139,
        lon=77.2090,
        target_time=target_time,
        category="HEAVY_RAINFALL",
    )
    assert status_sup == ProviderStatus.OK
    assert err_sup is None
    assert obs_sup is not None
    assert obs_sup.is_simulated is True
    assert obs_sup.source_type == PhysicalSourceType.STATION
    assert obs_sup.rainfall_1h_mm == 78.5

    # 2. CONTRADICTS scenario (Strong wind reported, calm measured by station)
    obs_con, status_con, err_con = await provider.fetch_observation(
        lat=19.0760,
        lon=72.8777,
        target_time=target_time,
        category="STRONG_WIND",
    )
    assert status_con == ProviderStatus.OK
    assert err_con is None
    assert obs_con is not None
    assert obs_con.is_simulated is True
    assert obs_con.source_type == PhysicalSourceType.STATION
    assert obs_con.wind_speed_kmh == 5.0
    assert obs_con.wind_gusts_kmh == 8.0

    # 3. NEUTRAL / Provider-down scenario (Outage fallback)
    obs_neu, status_neu, err_neu = await provider.fetch_observation(
        lat=13.0827,
        lon=80.2707,
        target_time=target_time,
        category="FOG",
    )
    assert status_neu == ProviderStatus.TIMEOUT
    assert obs_neu is None
    assert "timeout" in err_neu.lower()


@pytest.mark.asyncio
async def test_demo_fixture_evaluator_simulated_labeling() -> None:
    """Verify evaluator preserves is_simulated flag through evaluation logic."""
    target_time = datetime.now(timezone.utc)
    provider = FixtureWeatherProvider(scenario="CONTRADICTS")
    obs, status, _ = await provider.fetch_observation(
        lat=12.9716,
        lon=77.5946,
        target_time=target_time,
        category="STRONG_WIND",
    )
    assert obs is not None
    assert obs.is_simulated is True

    result = evaluate(
        category="STRONG_WIND",
        observation=obs,
        incident_time=target_time,
        incident_coords=(12.9716, 77.5946),
        config=default_physical_config,
    )
    assert result.verdict == PhysicalCorroborationVerdict.CONTRADICTS
    assert result.is_simulated is True
    assert result.contribution < 0.0


@pytest.mark.asyncio
async def test_demo_fixture_pipeline_service_and_api_serialization(
    api_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Verify demo fixture creates database record with is_simulated=True and API serializes it."""
    uid = uuid.uuid4().hex[:8]
    source = Source(
        source_code=f"SRC_SIM_{uid}",
        name="Simulated Drill Source",
        source_type="CITIZEN_REPORT",
        base_trust_score=0.70,
        is_active=True,
    )
    db_session.add(source)
    await db_session.flush()

    report = WeatherReport(
        tracking_id=f"RPT-SIM-{uid}",
        source_id=source.id,
        title="Cyclone Wind Drill Event",
        description="Demo incident for live presentation",
        location_name="Bhubaneswar, Odisha",
        reported_category="CYCLONE_STORM",
        severity="SEVERE",
        latitude=20.2961,
        longitude=85.8245,
        occurred_at=datetime.now(timezone.utc),
        geom="SRID=4326;POINT(85.8245 20.2961)",
        processing_status="PENDING",
        verification_status="PENDING",
        credibility_score=0.5000,
    )
    db_session.add(report)
    await db_session.flush()

    # Run service with FixtureWeatherProvider
    fixture_provider = FixtureWeatherProvider(scenario="SUPPORTS")
    service = PhysicalCorroborationService(provider=fixture_provider)

    corrob_record = await service.corroborate_incident(
        db=db_session,
        report=report,
        force_run=True,
    )
    assert corrob_record is not None
    assert corrob_record.is_simulated is True
    assert corrob_record.verdict == "SUPPORTS"
    await db_session.commit()

    # Query public tracking API to verify is_simulated badge serialization
    res = await api_client.get(f"/api/v1/reports/{report.tracking_id}")
    assert res.status_code == 200
    data = res.json()["data"]

    assert data["physical_verdict"] == "SUPPORTS"
    corrob_block = data["physical_corroboration"]
    assert corrob_block is not None
    assert corrob_block["is_simulated"] is True
    assert len(corrob_block["items"]) == 1
    assert corrob_block["items"][0]["is_simulated"] is True
