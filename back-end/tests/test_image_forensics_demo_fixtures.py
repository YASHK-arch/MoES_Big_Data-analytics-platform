"""Tests for S2 Image Forensics demo fixtures and SIMULATED labeling (Item 10).

Verifies:
1. Reused photo across different incidents produces CONTRADICTS with is_simulated=True.
2. EXIF time mismatch produces CONTRADICTS with is_simulated=True.
3. Missing EXIF produces NEUTRAL with 0.0 adjustment and is_simulated=True (P1).
4. Demo fixtures are gated under feature flags (disabled by default).
5. Incident detail API serializes is_simulated=True for simulated findings.
"""

from __future__ import annotations

import datetime
import uuid

import pytest
from geoalchemy2.elements import WKTElement
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.intelligence.image_forensics_demo_fixtures import (
    SCENARIO_EXIF_TIME_MISMATCH,
    SCENARIO_NO_EXIF,
    SCENARIO_REUSED_IMAGE,
    create_demo_image_forensics_scenario,
)
from app.main import app
from app.models.report import WeatherReport
from app.models.source import Source


async def _create_test_report(session: AsyncSession, name: str) -> WeatherReport:
    source = Source(
        id=uuid.uuid4(),
        source_code=f"SRC_{uuid.uuid4().hex[:8].upper()}",
        source_type="CITIZEN_REPORT",
        name="Citizen Web App",
        base_trust_score=0.60,
    )
    session.add(source)
    await session.flush()

    rep_id = uuid.uuid4()
    report = WeatherReport(
        id=rep_id,
        tracking_id=f"TRK-{uuid.uuid4().hex[:6].upper()}",
        source_id=source.id,
        title=f"Demo Disaster Event - {name}",
        description="Demo test incident description for simulation checks.",
        latitude=19.0760,
        longitude=72.8777,
        geom=WKTElement("POINT(72.8777 19.0760)", srid=4326),
        location_name="Mumbai, Maharashtra",
        occurred_at=datetime.datetime(2026, 8, 15, 12, 0, 0, tzinfo=datetime.timezone.utc),
        reported_category="FLOODING",
        verification_status="PENDING",
        credibility_score=0.55,
    )
    session.add(report)
    await session.flush()
    return report


@pytest.mark.asyncio
async def test_demo_fixture_reused_image_scenario(db_session: AsyncSession):
    """Scenario 1: Reused photo across incidents produces CONTRADICTS with is_simulated=True."""
    report = await _create_test_report(db_session, "Reused Photo")
    other_id = str(uuid.uuid4())

    finding = await create_demo_image_forensics_scenario(
        db=db_session,
        report=report,
        scenario=SCENARIO_REUSED_IMAGE,
        other_incident_id=other_id,
        force=True,
    )

    assert finding is not None
    assert finding.is_simulated is True
    assert finding.overall_verdict == "CONTRADICTS"
    assert finding.reuse_verdict == "CONTRADICTS"
    assert finding.credibility_adjustment == -0.05
    assert finding.matched_incident_ids == [other_id]
    assert finding.checks is not None and len(finding.checks) == 3


@pytest.mark.asyncio
async def test_demo_fixture_exif_time_mismatch_scenario(db_session: AsyncSession):
    """Scenario 2: EXIF capture time mismatch produces CONTRADICTS with is_simulated=True."""
    report = await _create_test_report(db_session, "Time Mismatch")

    finding = await create_demo_image_forensics_scenario(
        db=db_session,
        report=report,
        scenario=SCENARIO_EXIF_TIME_MISMATCH,
        force=True,
    )

    assert finding is not None
    assert finding.is_simulated is True
    assert finding.overall_verdict == "CONTRADICTS"
    assert finding.time_verdict == "CONTRADICTS"
    assert finding.time_difference == "120.00 hours"
    assert finding.credibility_adjustment == -0.05


@pytest.mark.asyncio
async def test_demo_fixture_no_exif_neutral_scenario(db_session: AsyncSession):
    """Scenario 3: Missing EXIF produces NEUTRAL with 0.0 adjustment and is_simulated=True (P1)."""
    report = await _create_test_report(db_session, "Missing EXIF")

    finding = await create_demo_image_forensics_scenario(
        db=db_session,
        report=report,
        scenario=SCENARIO_NO_EXIF,
        force=True,
    )

    assert finding is not None
    assert finding.is_simulated is True
    assert finding.overall_verdict == "NEUTRAL"
    assert finding.time_verdict == "NEUTRAL"
    assert finding.location_verdict == "NEUTRAL"
    assert finding.reuse_verdict == "SUPPORTS"
    assert finding.credibility_adjustment == 0.0


@pytest.mark.asyncio
async def test_demo_fixture_feature_flag_gating(db_session: AsyncSession, monkeypatch):
    """Verify demo fixtures are skipped when feature flags are false (default state)."""
    report = await _create_test_report(db_session, "Flag Gating")

    monkeypatch.setattr(settings, "IMAGE_FORENSICS_ENABLED", False)
    monkeypatch.setattr(settings, "IMAGE_FORENSICS_DEMO_FIXTURE_ENABLED", False)

    finding = await create_demo_image_forensics_scenario(
        db=db_session,
        report=report,
        scenario=SCENARIO_REUSED_IMAGE,
        force=False,
    )
    assert finding is None

    # Enable flag -> creates finding
    monkeypatch.setattr(settings, "IMAGE_FORENSICS_DEMO_FIXTURE_ENABLED", True)
    finding_enabled = await create_demo_image_forensics_scenario(
        db=db_session,
        report=report,
        scenario=SCENARIO_REUSED_IMAGE,
        force=False,
    )
    assert finding_enabled is not None
    assert finding_enabled.is_simulated is True


@pytest.mark.asyncio
async def test_demo_fixture_api_serialization(db_session: AsyncSession):
    """Verify API returns is_simulated=True in image_forensics block for demo fixture incidents."""
    report = await _create_test_report(db_session, "API Serialization")
    other_id = str(uuid.uuid4())

    finding = await create_demo_image_forensics_scenario(
        db=db_session,
        report=report,
        scenario=SCENARIO_REUSED_IMAGE,
        other_incident_id=other_id,
        force=True,
    )
    assert finding is not None
    await db_session.commit()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.get(f"/api/v1/incidents/{report.id}")
        assert resp.status_code == 200
        data = resp.json()["data"]

        forensics = data.get("image_forensics")
        assert forensics is not None
        assert forensics["is_simulated"] is True
        assert forensics["overall_verdict"] == "CONTRADICTS"
        assert forensics["images"][0]["is_simulated"] is True
        assert forensics["images"][0]["matched_incident_ids"] == [other_id]
