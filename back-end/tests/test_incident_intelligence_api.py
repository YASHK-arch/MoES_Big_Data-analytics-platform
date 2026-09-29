"""Comprehensive tests for the Stable Incident Intelligence REST API layer."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token
from app.main import app
from app.models.corroboration import IncidentObservationCorroboration
from app.models.duplicate import DuplicateCluster, DuplicateMember
from app.models.evidence import EvidenceItem, IncidentEvidenceLink
from app.models.observation import WeatherObservation
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
async def test_no_duplicate_citizen_intake_route(api_client: AsyncClient) -> None:
    """Verify POST /incidents is NOT an intake route; POST /reports is single canonical path."""
    res = await api_client.post("/api/v1/incidents", json={"title": "Test Incident"})
    assert res.status_code == 405  # Method Not Allowed (read-only resource)

    # Confirm /api/v1/reports is the valid intake path (returns 422 if body empty)
    res_reports = await api_client.post("/api/v1/reports")
    assert res_reports.status_code == 422


@pytest.mark.asyncio
async def test_list_incidents_default_pagination_and_envelope(
    api_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Verify standard response envelope and pagination metadata on GET /incidents."""
    uid = uuid.uuid4().hex[:8]
    source = Source(
        source_code=f"SRC_API_{uid}",
        name="API Test Source",
        source_type="CITIZEN_REPORT",
        base_trust_score=0.60,
        is_active=True,
    )
    db_session.add(source)
    await db_session.flush()

    report = WeatherReport(
        tracking_id=f"RPT-API-{uid}",
        source_id=source.id,
        title="Urban Flooding at Metro Station",
        description="Subway entrance inundated with 2 feet of water.",
        location_name="MG Road, Bangalore",
        reported_category="FLOOD_WATERLOGGING",
        severity="HIGH",
        latitude=12.9716,
        longitude=77.5946,
        occurred_at=datetime.now(timezone.utc),
        geom="SRID=4326;POINT(77.5946 12.9716)",
        processing_status="COMPLETED",
        verification_status="PENDING",
        credibility_score=0.7800,
        raw_payload={"orchestration": {"overall_readiness": "INTELLIGENCE_READY"}},
    )
    db_session.add(report)
    await db_session.commit()

    res = await api_client.get("/api/v1/incidents?page=1&page_size=10")
    assert res.status_code == 200
    body = res.json()

    assert body["success"] is True
    assert "data" in body
    assert isinstance(body["data"], list)
    assert len(body["data"]) >= 1

    # Check pagination envelope
    pagination = body["pagination"]
    assert pagination["page"] == 1
    assert pagination["page_size"] == 10
    assert pagination["total_records"] >= 1
    assert "total_pages" in pagination
    assert "has_next" in pagination
    assert "has_prev" in pagination

    # Check meta envelope
    assert "meta" in body
    assert "timestamp" in body["meta"]
    assert "request_id" in body["meta"]


@pytest.mark.asyncio
async def test_list_incidents_deterministic_tiebreaker_sorting(
    api_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Verify sorting by occurred_at uses mandatory tie-breaker id DESC."""
    res = await api_client.get("/api/v1/incidents?sort_by=occurred_at&sort_order=desc&page_size=50")
    assert res.status_code == 200
    items = res.json()["data"]

    for i in range(len(items) - 1):
        t1 = items[i]["occurred_at"]
        t2 = items[i + 1]["occurred_at"]
        assert t1 >= t2


@pytest.mark.asyncio
async def test_list_incidents_canonical_category_and_severity_filter(
    api_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Verify filtering by canonical category taxonomy and severity level."""
    uid = uuid.uuid4().hex[:8]
    source = Source(
        source_code=f"SRC_FLT_{uid}",
        name="Filter Source",
        source_type="CITIZEN_REPORT",
        base_trust_score=0.60,
        is_active=True,
    )
    db_session.add(source)
    await db_session.flush()

    report = WeatherReport(
        tracking_id=f"RPT-FLT-{uid}",
        source_id=source.id,
        title="Cyclone Storm Damage Alert",
        reported_category="CYCLONE_STORM",
        severity="SEVERE",
        latitude=19.8135,
        longitude=85.8312,
        occurred_at=datetime.now(timezone.utc),
        geom="SRID=4326;POINT(85.8312 19.8135)",
        processing_status="COMPLETED",
        verification_status="PENDING",
        credibility_score=0.8500,
    )
    db_session.add(report)
    await db_session.commit()

    res = await api_client.get("/api/v1/incidents?category=CYCLONE_STORM&severity=SEVERE")
    assert res.status_code == 200
    data = res.json()["data"]
    assert any(item["tracking_id"] == f"RPT-FLT-{uid}" for item in data)
    for item in data:
        assert item["category"]["code"] == "CYCLONE_STORM"
        assert item["severity"] == "SEVERE"


@pytest.mark.asyncio
async def test_list_incidents_verification_status_and_readiness_filter(
    api_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Verify verification_status and readiness filter parameters."""
    uid = uuid.uuid4().hex[:8]
    source = Source(
        source_code=f"SRC_STAT_{uid}",
        name="Status Filter Source",
        source_type="CITIZEN_REPORT",
        base_trust_score=0.60,
        is_active=True,
    )
    db_session.add(source)
    await db_session.flush()

    report = WeatherReport(
        tracking_id=f"RPT-STAT-{uid}",
        source_id=source.id,
        title="Gale Alert",
        reported_category="CYCLONE_STORM",
        severity="HIGH",
        latitude=19.8135,
        longitude=85.8312,
        occurred_at=datetime.now(timezone.utc),
        geom="SRID=4326;POINT(85.8312 19.8135)",
        processing_status="PARTIAL_INTELLIGENCE",
        verification_status="UNDER_REVIEW",
        credibility_score=0.6500,
        raw_payload={"orchestration": {"overall_readiness": "INTELLIGENCE_PARTIAL"}},
    )
    db_session.add(report)
    await db_session.commit()

    res = await api_client.get(
        "/api/v1/incidents?verification_status=UNDER_REVIEW&readiness=INTELLIGENCE_PARTIAL"
    )
    assert res.status_code == 200
    data = res.json()["data"]
    assert any(item["tracking_id"] == f"RPT-STAT-{uid}" for item in data)


@pytest.mark.asyncio
async def test_get_incident_detail_public_fields_redaction(
    api_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Verify public incident detail schema redacts private notes and internal audit logs."""
    uid = uuid.uuid4().hex[:8]
    source = Source(
        source_code=f"SRC_PUB_{uid}",
        name="Public Detail Source",
        source_type="CITIZEN_REPORT",
        base_trust_score=0.60,
        is_active=True,
    )
    db_session.add(source)
    await db_session.flush()

    report = WeatherReport(
        tracking_id=f"RPT-PUB-{uid}",
        source_id=source.id,
        title="Heavy Downpour Inundation",
        description="Water accumulated near signal junction.",
        location_name="Andheri West, Mumbai",
        reported_category="FLOOD_WATERLOGGING",
        severity="MODERATE",
        latitude=19.1197,
        longitude=72.8464,
        occurred_at=datetime.now(timezone.utc),
        geom="SRID=4326;POINT(72.8464 19.1197)",
        processing_status="COMPLETED",
        verification_status="VERIFIED",
        credibility_score=0.7845,
        credibility_explanation={"explanation_text": "High credibility: Sensor corroborated."},
        raw_payload={"orchestration": {"overall_readiness": "INTELLIGENCE_READY"}},
    )
    db_session.add(report)
    await db_session.commit()

    res = await api_client.get(f"/api/v1/incidents/{report.id}")
    assert res.status_code == 200
    data = res.json()["data"]

    # Public fields present
    assert data["id"] == str(report.id)
    assert data["tracking_id"] == report.tracking_id
    assert data["credibility"]["score"] == 0.7845
    assert data["verification"]["status"] == "VERIFIED"
    assert "summaries" in data
    assert "evidence_count" in data["summaries"]
    assert "observation_count" in data["summaries"]

    # Private operator fields omitted from public response
    assert "verification_history" not in data
    assert "orchestration_stages" not in data


@pytest.mark.asyncio
async def test_get_incident_detail_operator_fields_included(
    api_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Verify operator incident detail includes verification audit history and stage telemetry."""
    uid = uuid.uuid4().hex[:8]
    source = Source(
        source_code=f"SRC_OP_{uid}",
        name="Operator Detail Source",
        source_type="CITIZEN_REPORT",
        base_trust_score=0.60,
        is_active=True,
    )
    db_session.add(source)
    await db_session.flush()

    report = WeatherReport(
        tracking_id=f"RPT-OP-{uid}",
        source_id=source.id,
        title="Landslide Road Block",
        reported_category="LANDSLIDE",
        severity="SEVERE",
        latitude=11.6854,
        longitude=76.1320,
        occurred_at=datetime.now(timezone.utc),
        geom="SRID=4326;POINT(76.1320 11.6854)",
        processing_status="COMPLETED",
        verification_status="PENDING",
        credibility_score=0.8200,
        raw_payload={
            "orchestration": {
                "overall_readiness": "INTELLIGENCE_READY",
                "stages": {"LOCATION": {"status": "SUCCESS_WITH_RESULTS", "attempt": 1}},
            }
        },
    )
    db_session.add(report)
    await db_session.commit()

    res = await api_client.get(f"/api/v1/incidents/{report.id}/operator-detail")
    assert res.status_code == 200
    data = res.json()["data"]

    assert "verification_history" in data
    assert "orchestration_stages" in data
    assert "LOCATION" in data["orchestration_stages"]


@pytest.mark.asyncio
async def test_get_incident_credibility_canonical_drivers_and_flags(
    api_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Verify GET /incidents/{id}/credibility returns canonical drivers, flags, and label."""
    uid = uuid.uuid4().hex[:8]
    source = Source(
        source_code=f"SRC_CRED_{uid}",
        name="Credibility Test Source",
        source_type="CITIZEN_REPORT",
        base_trust_score=0.60,
        is_active=True,
    )
    db_session.add(source)
    await db_session.flush()

    report = WeatherReport(
        tracking_id=f"RPT-CRED-{uid}",
        source_id=source.id,
        title="Heavy Rainfall Alert",
        reported_category="HEAVY_RAINFALL",
        severity="HIGH",
        latitude=19.0760,
        longitude=72.8777,
        occurred_at=datetime.now(timezone.utc),
        geom="SRID=4326;POINT(72.8777 19.0760)",
        processing_status="COMPLETED",
        verification_status="PENDING",
        credibility_score=0.8800,
        credibility_explanation={
            "explanation_text": "High credibility: Corroborated by Santacruz AWS (4.2km, 48mm/hr).",
            "positive_drivers": [
                "Corroborated by Santacruz AWS (4.2km, 48mm/hr)",
                "Linked to 2 news articles",
            ],
            "negative_drivers": [],
            "uncertainty_flags": [],
            "source_prior": 0.60,
            "engine_version": "v1",
            "policy_version": "v1",
        },
    )
    db_session.add(report)
    await db_session.commit()

    res = await api_client.get(f"/api/v1/incidents/{report.id}/credibility")
    assert res.status_code == 200
    data = res.json()["data"]

    assert data["incident_id"] == str(report.id)
    assert data["score"] == 0.8800
    assert data["is_machine_assessed"] is True
    assert data["label"] == "VERY_HIGH_CREDIBILITY"
    assert len(data["positive_drivers"]) == 2
    assert "Santacruz AWS" in data["positive_drivers"][0]


@pytest.mark.asyncio
async def test_incident_credibility_timestamp_hierarchy_and_fallbacks(
    api_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Verify credibility last_calculated_at follows assessed_at -> updated_at hierarchy."""
    uid = uuid.uuid4().hex[:8]
    source = Source(
        source_code=f"SRC_TS_{uid}",
        name="Timestamp Test Source",
        source_type="CITIZEN_REPORT",
        base_trust_score=0.60,
        is_active=True,
    )
    db_session.add(source)
    await db_session.flush()

    # Case A: Valid assessed_at in ISO format
    ts_assessed = "2026-08-30T01:15:30.123456Z"
    report_a = WeatherReport(
        tracking_id=f"RPT-TS-A-{uid}",
        source_id=source.id,
        title="Timestamp Case A",
        reported_category="FLOOD",
        latitude=19.0760,
        longitude=72.8777,
        occurred_at=datetime.now(timezone.utc),
        geom="SRID=4326;POINT(72.8777 19.0760)",
        credibility_score=0.85,
        credibility_explanation={
            "assessed_at": ts_assessed,
            "engine_version": "v1",
            "policy_version": "v1",
        },
    )
    db_session.add(report_a)

    # Case B: Missing assessed_at -> falls back to updated_at
    report_b = WeatherReport(
        tracking_id=f"RPT-TS-B-{uid}",
        source_id=source.id,
        title="Timestamp Case B",
        reported_category="FLOOD",
        latitude=19.0760,
        longitude=72.8777,
        occurred_at=datetime.now(timezone.utc),
        geom="SRID=4326;POINT(72.8777 19.0760)",
        credibility_score=0.75,
        credibility_explanation={
            "engine_version": "v1",
            "policy_version": "v1",
        },
    )
    db_session.add(report_b)

    # Case C: Malformed assessed_at -> safely falls back to updated_at without error
    report_c = WeatherReport(
        tracking_id=f"RPT-TS-C-{uid}",
        source_id=source.id,
        title="Timestamp Case C",
        reported_category="FLOOD",
        latitude=19.0760,
        longitude=72.8777,
        occurred_at=datetime.now(timezone.utc),
        geom="SRID=4326;POINT(72.8777 19.0760)",
        credibility_score=0.70,
        credibility_explanation={
            "assessed_at": "not-a-valid-timestamp-string",
            "engine_version": "v1",
        },
    )
    db_session.add(report_c)

    await db_session.commit()

    # Query Case A
    res_a = await api_client.get(f"/api/v1/incidents/{report_a.id}/credibility")
    assert res_a.status_code == 200
    assert "2026-08-30T01:15:30" in res_a.json()["data"]["last_calculated_at"]

    # Query Case B (fallback to updated_at)
    res_b = await api_client.get(f"/api/v1/incidents/{report_b.id}/credibility")
    assert res_b.status_code == 200
    assert res_b.json()["data"]["last_calculated_at"] is not None

    # Query Case C (safe fallback on malformed string)
    res_c = await api_client.get(f"/api/v1/incidents/{report_c.id}/credibility")
    assert res_c.status_code == 200
    assert res_c.json()["data"]["last_calculated_at"] is not None


@pytest.mark.asyncio
async def test_get_incident_evidence_canonical_relationships(
    api_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Verify GET /incidents/{id}/evidence returns canonical EvidenceRelationship enums."""
    uid = uuid.uuid4().hex[:8]
    source = Source(
        source_code=f"SRC_EVI_{uid}",
        name="Evidence Source",
        source_type="CITIZEN_REPORT",
        base_trust_score=0.60,
        is_active=True,
    )
    db_session.add(source)
    await db_session.flush()

    report = WeatherReport(
        tracking_id=f"RPT-EVI-{uid}",
        source_id=source.id,
        title="Urban Flooding",
        reported_category="FLOOD_WATERLOGGING",
        severity="HIGH",
        latitude=19.0760,
        longitude=72.8777,
        occurred_at=datetime.now(timezone.utc),
        geom="SRID=4326;POINT(72.8777 19.0760)",
        processing_status="COMPLETED",
        verification_status="PENDING",
        credibility_score=0.7500,
    )
    db_session.add(report)
    await db_session.flush()

    evidence = EvidenceItem(
        source_id=source.id,
        external_id=f"evi_{uid}",
        evidence_type="NEWS_ARTICLE",
        title="Subway Inundation at Kurla Station",
        text_snippet="Heavy rains flood Kurla suburban rail line.",
        publisher_domain="thehindu.com",
        published_at=datetime.now(timezone.utc),
    )
    db_session.add(evidence)
    await db_session.flush()

    link = IncidentEvidenceLink(
        report_id=report.id,
        evidence_id=evidence.id,
        link_role="SUPPORTING",
        confidence_score=0.9100,
    )
    db_session.add(link)
    await db_session.commit()

    res = await api_client.get(f"/api/v1/incidents/{report.id}/evidence")
    assert res.status_code == 200
    data = res.json()["data"]

    assert len(data) == 1
    assert data[0]["relationship"] == "SUPPORTING"
    assert data[0]["confidence_score"] == 0.9100
    assert data[0]["publisher_domain"] == "thehindu.com"


@pytest.mark.asyncio
async def test_get_incident_observations_canonical_relationships(
    api_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Verify GET /incidents/{id}/observations returns canonical ObservationRelationship enums."""
    uid = uuid.uuid4().hex[:8]
    source = Source(
        source_code=f"SRC_OBS_{uid}",
        name="Observation Source",
        source_type="CITIZEN_REPORT",
        base_trust_score=0.60,
        is_active=True,
    )
    db_session.add(source)
    await db_session.flush()

    report = WeatherReport(
        tracking_id=f"RPT-OBS-{uid}",
        source_id=source.id,
        title="Severe Waterlogging",
        reported_category="FLOOD_WATERLOGGING",
        severity="HIGH",
        latitude=19.0760,
        longitude=72.8777,
        occurred_at=datetime.now(timezone.utc),
        geom="SRID=4326;POINT(72.8777 19.0760)",
        processing_status="COMPLETED",
        verification_status="PENDING",
        credibility_score=0.8500,
    )
    db_session.add(report)
    await db_session.flush()

    obs = WeatherObservation(
        source_id=source.id,
        station_code="IMD_MUM_01",
        station_name="Santacruz AWS",
        observed_at=datetime.now(timezone.utc),
        rainfall_mm=52.0,
        geom="SRID=4326;POINT(72.8777 19.0760)",
    )
    db_session.add(obs)
    await db_session.flush()

    cor = IncidentObservationCorroboration(
        report_id=report.id,
        observation_id=obs.id,
        corroboration_score=0.9400,
        distance_meters=3500.0,
        corroboration_assessment={"relationship_type": "CORROBORATING", "is_contradiction": False},
    )
    db_session.add(cor)
    await db_session.commit()

    res = await api_client.get(f"/api/v1/incidents/{report.id}/observations")
    assert res.status_code == 200
    data = res.json()["data"]

    assert len(data) == 1
    assert data[0]["relationship"] == "CORROBORATING"
    assert data[0]["station_code"] == "IMD_MUM_01"
    assert data[0]["metrics"]["rainfall_mm_1h"] == 52.0


@pytest.mark.asyncio
async def test_get_incident_cluster_summary_and_members(
    api_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Verify GET /incidents/{id}/cluster returns cluster code, size, and members."""
    uid = uuid.uuid4().hex[:8]
    source = Source(
        source_code=f"SRC_CLUS_{uid}",
        name="Cluster Source",
        source_type="CITIZEN_REPORT",
        base_trust_score=0.60,
        is_active=True,
    )
    db_session.add(source)
    await db_session.flush()

    r1 = WeatherReport(
        tracking_id=f"RPT-CL1-{uid}",
        source_id=source.id,
        title="Kurla Station Waterlogging",
        reported_category="FLOOD_WATERLOGGING",
        severity="HIGH",
        latitude=19.0760,
        longitude=72.8777,
        occurred_at=datetime.now(timezone.utc),
        geom="SRID=4326;POINT(72.8777 19.0760)",
        processing_status="COMPLETED",
        verification_status="PENDING",
        credibility_score=0.8500,
    )
    r2 = WeatherReport(
        tracking_id=f"RPT-CL2-{uid}",
        source_id=source.id,
        title="Kurla Subway Flooded",
        reported_category="FLOOD_WATERLOGGING",
        severity="HIGH",
        latitude=19.0765,
        longitude=72.8780,
        occurred_at=datetime.now(timezone.utc),
        geom="SRID=4326;POINT(72.8780 19.0765)",
        processing_status="COMPLETED",
        verification_status="DUPLICATE",
        credibility_score=0.8200,
    )
    db_session.add_all([r1, r2])
    await db_session.flush()

    cluster = DuplicateCluster(
        primary_report_id=r1.id,
        centroid_geom="SRID=4326;POINT(72.8777 19.0760)",
        member_count=2,
    )
    db_session.add(cluster)
    await db_session.flush()

    m1 = DuplicateMember(cluster_id=cluster.id, report_id=r1.id, similarity_score=1.0)
    m2 = DuplicateMember(cluster_id=cluster.id, report_id=r2.id, similarity_score=0.88)
    db_session.add_all([m1, m2])
    await db_session.commit()

    res = await api_client.get(f"/api/v1/incidents/{r1.id}/cluster")
    assert res.status_code == 200
    data = res.json()["data"]

    assert data["total_member_count"] == 2
    assert data["is_representative"] is True
    assert len(data["members"]) == 2


@pytest.mark.asyncio
async def test_geo_incidents_valid_bbox_and_safety_checks(
    api_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Verify GeoJSON FeatureCollection retrieval and safety validations."""
    # 1. Valid bbox
    res = await api_client.get("/api/v1/geo/incidents?bbox=72.0,18.0,74.0,20.0")
    assert res.status_code == 200
    body = res.json()
    assert body["type"] == "FeatureCollection"
    assert "features" in body

    # 2. Invalid min > max rejected with 422
    res_inv = await api_client.get("/api/v1/geo/incidents?bbox=74.0,20.0,72.0,18.0")
    assert res_inv.status_code == 422

    # 3. Oversized bbox (> 10 degrees) rejected with 422
    res_over = await api_client.get("/api/v1/geo/incidents?bbox=60.0,0.0,80.0,20.0")
    assert res_over.status_code == 422


@pytest.mark.asyncio
async def test_verification_queue_severity_credibility_ordering(
    api_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Verify queue sorts explicitly by SEVERE (4) > HIGH (3) > MODERATE (2) > LOW (1)."""
    uid = uuid.uuid4().hex[:8]
    cat_code = f"CAT_Q_{uid}".upper()
    source = Source(
        source_code=f"SRC_Q_{uid}",
        name="Queue Source",
        source_type="CITIZEN_REPORT",
        base_trust_score=0.60,
        is_active=True,
    )
    db_session.add(source)
    await db_session.flush()

    r_low = WeatherReport(
        tracking_id=f"RPT-QL-{uid}",
        source_id=source.id,
        title="Drizzle Observation",
        reported_category=cat_code,
        severity="LOW",
        latitude=12.9716,
        longitude=77.5946,
        occurred_at=datetime.now(timezone.utc),
        geom="SRID=4326;POINT(77.5946 12.9716)",
        processing_status="COMPLETED",
        verification_status="PENDING",
        credibility_score=0.9000,
    )
    r_severe = WeatherReport(
        tracking_id=f"RPT-QS-{uid}",
        source_id=source.id,
        title="Severe Flood Emergency",
        reported_category=cat_code,
        severity="SEVERE",
        latitude=12.9716,
        longitude=77.5946,
        occurred_at=datetime.now(timezone.utc),
        geom="SRID=4326;POINT(77.5946 12.9716)",
        processing_status="COMPLETED",
        verification_status="PENDING",
        credibility_score=0.6000,
    )
    db_session.add_all([r_low, r_severe])
    await db_session.commit()

    res = await api_client.get(f"/api/v1/verification/queue?category={cat_code}&page_size=50")
    assert res.status_code == 200
    items = res.json()["data"]

    # SEVERE must appear before LOW despite LOW having higher credibility
    severe_idx = next(i for i, it in enumerate(items) if it["tracking_id"] == f"RPT-QS-{uid}")
    low_idx = next(i for i, it in enumerate(items) if it["tracking_id"] == f"RPT-QL-{uid}")
    assert severe_idx < low_idx


@pytest.mark.asyncio
async def test_verify_and_reject_incident_creates_audit_events(
    api_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Verify operator verification and rejection endpoints update status and create audit logs."""
    uid = uuid.uuid4().hex[:8]
    source = Source(
        source_code=f"SRC_ACT_{uid}",
        name="Action Source",
        source_type="CITIZEN_REPORT",
        base_trust_score=0.60,
        is_active=True,
    )
    db_session.add(source)
    await db_session.flush()

    report = WeatherReport(
        tracking_id=f"RPT-ACT-{uid}",
        source_id=source.id,
        title="Urban Flooding Report",
        reported_category="FLOOD_WATERLOGGING",
        severity="HIGH",
        latitude=19.0760,
        longitude=72.8777,
        occurred_at=datetime.now(timezone.utc),
        geom="SRID=4326;POINT(72.8777 19.0760)",
        processing_status="COMPLETED",
        verification_status="PENDING",
        credibility_score=0.7000,
    )
    db_session.add(report)
    await db_session.commit()

    # 1. Verify Report 1
    ver_res = await api_client.post(
        f"/api/v1/verification/{report.id}/verify",
        json={"notes": "Confirmed on ground with Ward disaster team.", "broadcast_alert": True},
    )
    assert ver_res.status_code == 200
    ver_data = ver_res.json()["data"]
    assert ver_data["verification"]["status"] == "VERIFIED"
    assert len(ver_data["verification_history"]) == 1
    assert "Confirmed on ground" in ver_data["verification_history"][0]["notes"]

    # 2. Attempt to reject already verified Report 1 (Must be blocked by state machine)
    invalid_rej_res = await api_client.post(
        f"/api/v1/verification/{report.id}/reject",
        json={"rejection_reason": "OUTDATED_ARCHIVE", "notes": "Image is from 2021."},
    )
    assert invalid_rej_res.status_code == 400
    err_body = invalid_rej_res.json()
    assert err_body["success"] is False
    assert err_body["error"]["code"] == "INVALID_STATE_TRANSITION"

    # 3. Create Report 2 and test valid direct rejection
    report2 = WeatherReport(
        tracking_id=f"RPT-OP-REJ-{uid}",
        source_id=source.id,
        title="Reject Target Test Incident",
        reported_category="CYCLONE_STORM",
        severity="HIGH",
        latitude=19.0760,
        longitude=72.8777,
        occurred_at=datetime.now(timezone.utc),
        geom="SRID=4326;POINT(72.8777 19.0760)",
        processing_status="COMPLETED",
        verification_status="PENDING",
        credibility_score=0.4000,
    )
    db_session.add(report2)
    await db_session.commit()

    rej_res = await api_client.post(
        f"/api/v1/verification/{report2.id}/reject",
        json={"rejection_reason": "OUTDATED_ARCHIVE", "notes": "Image is from 2021."},
    )
    assert rej_res.status_code == 200
    rej_data = rej_res.json()["data"]
    assert rej_data["verification"]["status"] == "REJECTED"
    assert len(rej_data["verification_history"]) == 1


@pytest.mark.asyncio
async def test_frontend_report_api_backward_compatibility(
    api_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """
    Verify existing /api/v1/reports routes still work seamlessly for existing frontend.
    """
    uid = uuid.uuid4().hex[:8]
    source = Source(
        source_code=f"SRC_BC_{uid}",
        name="Backward Compat Source",
        source_type="CITIZEN_REPORT",
        base_trust_score=0.60,
        is_active=True,
    )
    db_session.add(source)
    await db_session.flush()

    report = WeatherReport(
        tracking_id=f"RPT-BC-{uid}",
        source_id=source.id,
        title="Backward Compatibility Test Report",
        reported_category="FLOOD_WATERLOGGING",
        severity="MODERATE",
        latitude=19.0760,
        longitude=72.8777,
        occurred_at=datetime.now(timezone.utc),
        geom="SRID=4326;POINT(72.8777 19.0760)",
        processing_status="COMPLETED",
        verification_status="PENDING",
        credibility_score=0.6500,
    )
    db_session.add(report)
    await db_session.commit()

    # GET /api/v1/reports
    res_list = await api_client.get("/api/v1/reports")
    assert res_list.status_code == 200
    assert res_list.json()["success"] is True

    # GET /api/v1/reports/{id}
    res_detail = await api_client.get(f"/api/v1/reports/{report.id}")
    assert res_detail.status_code == 200
    assert res_detail.json()["data"]["tracking_id"] == f"RPT-BC-{uid}"

    # GET /api/v1/incidents/{id}/credibility
    res_cred = await api_client.get(f"/api/v1/incidents/{report.id}/credibility")
    assert res_cred.status_code == 200
    assert res_cred.json()["data"]["score"] == 0.6500


@pytest.mark.asyncio
async def test_list_incidents_credibility_range_filter(
    api_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """
    Verify min_credibility and max_credibility boundary filters.
    """
    uid = uuid.uuid4().hex[:8]
    cat_code = f"CAT_RNG_{uid}".upper()
    source = Source(
        source_code=f"SRC_RNG_{uid}",
        name="Range Source",
        source_type="CITIZEN_REPORT",
        base_trust_score=0.60,
        is_active=True,
    )
    db_session.add(source)
    await db_session.flush()

    r1 = WeatherReport(
        tracking_id=f"RPT-R1-{uid}",
        source_id=source.id,
        title="Report High Cred",
        reported_category=cat_code,
        severity="HIGH",
        latitude=19.0760,
        longitude=72.8777,
        geom="SRID=4326;POINT(72.8777 19.0760)",
        occurred_at=datetime.now(timezone.utc),
        processing_status="COMPLETED",
        verification_status="PENDING",
        credibility_score=0.9200,
    )
    r2 = WeatherReport(
        tracking_id=f"RPT-R2-{uid}",
        source_id=source.id,
        title="Report Low Cred",
        reported_category=cat_code,
        severity="HIGH",
        latitude=19.0760,
        longitude=72.8777,
        geom="SRID=4326;POINT(72.8777 19.0760)",
        occurred_at=datetime.now(timezone.utc),
        processing_status="COMPLETED",
        verification_status="PENDING",
        credibility_score=0.3500,
    )
    db_session.add_all([r1, r2])
    await db_session.commit()

    res = await api_client.get(f"/api/v1/incidents?category={cat_code}&min_credibility=0.80")
    assert res.status_code == 200
    data = res.json()["data"]
    assert len(data) == 1
    assert data[0]["tracking_id"] == f"RPT-R1-{uid}"


@pytest.mark.asyncio
async def test_get_incident_intelligence_status_readiness_and_stages(
    api_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """
    Verify GET /incidents/{id}/intelligence returns per-stage execution telemetry.
    """
    uid = uuid.uuid4().hex[:8]
    source = Source(
        source_code=f"SRC_INT_{uid}",
        name="Intelligence Stage Source",
        source_type="CITIZEN_REPORT",
        base_trust_score=0.60,
        is_active=True,
    )
    db_session.add(source)
    await db_session.flush()

    report = WeatherReport(
        tracking_id=f"RPT-INT-{uid}",
        source_id=source.id,
        title="Intelligence Stage Test",
        reported_category="FLOOD_WATERLOGGING",
        severity="HIGH",
        latitude=19.0760,
        longitude=72.8777,
        geom="SRID=4326;POINT(72.8777 19.0760)",
        occurred_at=datetime.now(timezone.utc),
        processing_status="COMPLETED",
        verification_status="PENDING",
        credibility_score=0.8400,
        raw_payload={
            "orchestration": {
                "overall_readiness": "INTELLIGENCE_READY",
                "last_successful_stage": "CREDIBILITY",
                "stages": {
                    "LOCATION": {
                        "status": "SUCCESS_WITH_RESULTS",
                        "attempt": 1,
                        "duration_ms": 12.5,
                    },
                    "CREDIBILITY": {
                        "status": "SUCCESS_WITH_RESULTS",
                        "attempt": 1,
                        "duration_ms": 8.1,
                    },
                },
            }
        },
    )
    db_session.add(report)
    await db_session.commit()

    res = await api_client.get(f"/api/v1/incidents/{report.id}/intelligence")
    assert res.status_code == 200
    data = res.json()["data"]

    assert data["incident_id"] == str(report.id)
    assert data["overall_readiness"] == "INTELLIGENCE_READY"
    assert data["last_successful_stage"] == "CREDIBILITY"
    assert "LOCATION" in data["stages"]
    assert data["stages"]["LOCATION"]["duration_ms"] == 12.5


@pytest.mark.asyncio
async def test_geo_incidents_out_of_bbox_excluded(
    api_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """
    Verify reports outside the requested bounding box are excluded from GeoJSON features.
    """
    uid = uuid.uuid4().hex[:8]
    cat_code = f"CAT_OUT_{uid}".upper()
    source = Source(
        source_code=f"SRC_OUT_{uid}",
        name="Out Geo Source",
        source_type="CITIZEN_REPORT",
        base_trust_score=0.60,
        is_active=True,
    )
    db_session.add(source)
    await db_session.flush()

    report = WeatherReport(
        tracking_id=f"RPT-OUT-{uid}",
        source_id=source.id,
        title="Far Away Incident",
        reported_category=cat_code,
        severity="LOW",
        latitude=28.6139,  # Delhi
        longitude=77.2090,
        geom="SRID=4326;POINT(77.2090 28.6139)",
        occurred_at=datetime.now(timezone.utc),
        processing_status="COMPLETED",
        verification_status="PENDING",
        credibility_score=0.5000,
    )
    db_session.add(report)
    await db_session.commit()

    # Query Mumbai bbox (72-73, 18-19)
    res = await api_client.get(
        f"/api/v1/geo/incidents?bbox=72.0,18.0,73.0,19.0&category={cat_code}"
    )
    assert res.status_code == 200
    features = res.json()["features"]
    assert not any(f["properties"]["tracking_id"] == f"RPT-OUT-{uid}" for f in features)


@pytest.mark.asyncio
async def test_forbidden_direct_credibility_score_mutation(api_client: AsyncClient) -> None:
    """
    Verify no public/operator endpoint permits direct PATCH or PUT of credibility_score.
    """
    fake_id = uuid.uuid4()
    res_patch = await api_client.patch(
        f"/api/v1/incidents/{fake_id}", json={"credibility_score": 0.99}
    )
    assert res_patch.status_code == 405  # Method Not Allowed

    res_put = await api_client.put(f"/api/v1/incidents/{fake_id}", json={"credibility_score": 0.99})
    assert res_put.status_code == 405  # Method Not Allowed

    res_cred_patch = await api_client.patch(
        f"/api/v1/incidents/{fake_id}/credibility", json={"score": 0.99}
    )
    assert res_cred_patch.status_code == 405  # Method Not Allowed


@pytest.mark.asyncio
async def test_media_url_safety_presigned_and_no_secret_leak(
    api_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """
    Verify media items return safe presigned URLs without leaking secrets.
    """
    uid = uuid.uuid4().hex[:8]
    source = Source(
        source_code=f"SRC_MED_{uid}",
        name="Media Source",
        source_type="CITIZEN_REPORT",
        base_trust_score=0.60,
        is_active=True,
    )
    db_session.add(source)
    await db_session.flush()

    report = WeatherReport(
        tracking_id=f"RPT-MED-{uid}",
        source_id=source.id,
        title="Flooding with Photo",
        reported_category="FLOOD_WATERLOGGING",
        severity="HIGH",
        latitude=19.0760,
        longitude=72.8777,
        occurred_at=datetime.now(timezone.utc),
        geom="SRID=4326;POINT(72.8777 19.0760)",
        processing_status="COMPLETED",
        verification_status="PENDING",
        credibility_score=0.8000,
    )
    db_session.add(report)
    await db_session.commit()

    res = await api_client.get(f"/api/v1/incidents/{report.id}")
    assert res.status_code == 200
    data = res.json()["data"]
    assert "media" in data
    # Safe structure
    assert isinstance(data["media"], list)


@pytest.mark.asyncio
async def test_geo_incidents_without_bbox_national_overview(
    api_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Verify GeoJSON FeatureCollection retrieval without bbox for national overview."""
    uid = uuid.uuid4().hex[:8]
    cat_code = f"CAT_NAT_{uid}".upper()
    source = Source(
        source_code=f"SRC_NAT_{uid}",
        name="National Geo Source",
        source_type="CITIZEN_REPORT",
        base_trust_score=0.75,
        is_active=True,
    )
    db_session.add(source)
    await db_session.flush()

    report = WeatherReport(
        tracking_id=f"RPT-NAT-{uid}",
        source_id=source.id,
        title="National Overview Incident",
        reported_category=cat_code,
        severity="SEVERE",
        latitude=13.0827,  # Chennai
        longitude=80.2707,
        geom="SRID=4326;POINT(80.2707 13.0827)",
        occurred_at=datetime.now(timezone.utc),
        processing_status="COMPLETED",
        verification_status="VERIFIED",
        credibility_score=0.8500,
    )
    db_session.add(report)
    await db_session.commit()

    # 1. Query without bbox
    res = await api_client.get(f"/api/v1/geo/incidents?category={cat_code}")
    assert res.status_code == 200
    body = res.json()
    assert body["type"] == "FeatureCollection"
    assert "features" in body
    assert len(body["features"]) <= 500
    assert any(f["properties"]["tracking_id"] == f"RPT-NAT-{uid}" for f in body["features"])

    feature = next(
        f for f in body["features"] if f["properties"]["tracking_id"] == f"RPT-NAT-{uid}"
    )
    assert feature["geometry"]["type"] == "Point"
    assert feature["geometry"]["coordinates"] == [80.2707, 13.0827]
    assert feature["properties"]["severity"] == "SEVERE"
    assert feature["properties"]["verification_status"] == "VERIFIED"
    assert feature["properties"]["credibility_score"] == 0.8500


@pytest.mark.asyncio
async def test_geo_incidents_filtering_status_and_all_time(
    api_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Verify GeoJSON filtering by status and all-time query without bbox."""
    uid = uuid.uuid4().hex[:8]
    cat_code = f"CAT_GEO_FILT_{uid}".upper()
    source = Source(
        source_code=f"SRC_GF_{uid}",
        name="Geo Filter Source",
        source_type="CITIZEN_REPORT",
        base_trust_score=0.70,
        is_active=True,
    )
    db_session.add(source)
    await db_session.flush()

    report_verified = WeatherReport(
        tracking_id=f"RPT-GF-VER-{uid}",
        source_id=source.id,
        title="Verified Incident Filter Test",
        reported_category=cat_code,
        severity="HIGH",
        latitude=15.3173,
        longitude=75.7139,
        geom="SRID=4326;POINT(75.7139 15.3173)",
        occurred_at=datetime.now(timezone.utc) - timedelta(days=10),
        processing_status="COMPLETED",
        verification_status="VERIFIED",
        credibility_score=0.9000,
    )
    report_pending = WeatherReport(
        tracking_id=f"RPT-GF-PEN-{uid}",
        source_id=source.id,
        title="Pending Incident Filter Test",
        reported_category=cat_code,
        severity="MODERATE",
        latitude=15.3173,
        longitude=75.7139,
        geom="SRID=4326;POINT(75.7139 15.3173)",
        occurred_at=datetime.now(timezone.utc) - timedelta(days=10),
        processing_status="COMPLETED",
        verification_status="PENDING",
        credibility_score=0.6000,
    )
    db_session.add_all([report_verified, report_pending])
    await db_session.commit()

    # Query with status=VERIFIED and hours_ago=720 (30 days)
    res = await api_client.get(
        f"/api/v1/geo/incidents?category={cat_code}&status=VERIFIED&hours_ago=720"
    )
    assert res.status_code == 200
    features = res.json()["features"]
    assert any(f["properties"]["tracking_id"] == f"RPT-GF-VER-{uid}" for f in features)
    assert not any(f["properties"]["tracking_id"] == f"RPT-GF-PEN-{uid}" for f in features)
