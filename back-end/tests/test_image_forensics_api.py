"""API tests for image forensics block on incident detail endpoints (S2 Item 8).

Verifies:
- GET /api/v1/incidents/{id} includes image_forensics block
- GET /api/v1/incidents/{id}/operator-detail includes image_forensics block
- Derived checks, verdicts, and explanations are present
- Reuse matches expose other incident IDs only (P5)
- No raw GPS coordinates exposed in public/operator endpoints (P5)
- OpenAPI schema contains image_forensics block definition
"""

import datetime
import uuid

import pytest
from geoalchemy2.elements import WKTElement
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.main import app
from app.models.image_forensics import IncidentImageFinding
from app.models.media import ReportMedia
from app.models.report import WeatherReport
from app.models.source import Source


@pytest.mark.asyncio
async def test_api_incident_detail_includes_image_forensics(db_session: AsyncSession):
    """Test public and operator incident detail endpoints return structured image forensics."""
    # 1. Setup source & report
    source = Source(
        id=uuid.uuid4(),
        source_code="CITIZEN_WEB_S2",
        source_type="CITIZEN_REPORT",
        name="Citizen Web App",
        base_trust_score=0.60,
    )
    db_session.add(source)
    await db_session.flush()

    rep_id = uuid.uuid4()
    report = WeatherReport(
        id=rep_id,
        tracking_id=f"TRK-S2-{uuid.uuid4().hex[:6].upper()}",
        source_id=source.id,
        title="Cyclone Winds in Paradip",
        description="Strong coastal winds causing tree falls and power disruptions.",
        latitude=20.3165,
        longitude=86.6114,
        geom=WKTElement("POINT(86.6114 20.3165)", srid=4326),
        location_name="Paradip, Odisha",
        occurred_at=datetime.datetime(2026, 8, 15, 10, 0, 0, tzinfo=datetime.timezone.utc),
        reported_category="CYCLONE_STORM",
        verification_status="PENDING",
        credibility_score=0.65,
    )
    db_session.add(report)

    media = ReportMedia(
        id=uuid.uuid4(),
        report_id=rep_id,
        media_type="IMAGE",
        storage_bucket="weather-evidence",
        storage_key=f"reports/{rep_id}/img1.jpg",
        mime_type="image/jpeg",
        file_size_bytes=45000,
        sha256_hash="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    )
    db_session.add(media)

    # 2. Add an image finding with cross-incident reuse match
    reused_incident_id = str(uuid.uuid4())
    finding = IncidentImageFinding(
        id=uuid.uuid4(),
        incident_id=rep_id,
        media_id=media.id,
        sha256=media.sha256_hash,
        phash="c629293939f68629",
        dhash="0000000000000000",
        has_exif=True,
        exif_timestamp_utc=datetime.datetime(2026, 8, 15, 9, 30, 0, tzinfo=datetime.timezone.utc),
        timezone_assumed_ist=False,
        time_verdict="SUPPORTS",
        time_difference="0.50 hours",
        location_verdict="SUPPORTS",
        location_difference="2.40 km",
        reuse_verdict="CONTRADICTS",
        matched_incident_ids=[reused_incident_id],
        overall_verdict="CONTRADICTS",
        credibility_adjustment=-0.05,
        checks=[
            {
                "check_type": "EXIF_TIME",
                "verdict": "SUPPORTS",
                "observed_value": "2026-08-15T09:30:00+00:00",
                "expected_value": "2026-08-15T10:00:00+00:00",
                "difference": "0.50 hours",
                "reason": "Photo capture time is within 3.0h of declared incident time",
                "matched_incident_ids": [],
            },
            {
                "check_type": "EXIF_LOCATION",
                "verdict": "SUPPORTS",
                "observed_value": "COORDINATES_PRESENT",
                "expected_value": "DECLARED_INCIDENT_LOCATION",
                "difference": "2.40 km",
                "reason": "Photo GPS coordinates match declared location within 2.40 km",
                "matched_incident_ids": [],
            },
            {
                "check_type": "IMAGE_REUSE",
                "verdict": "CONTRADICTS",
                "observed_value": "1 distant matches",
                "expected_value": "0 cross-incident matches",
                "difference": "1 distant incident(s)",
                "reason": "Identical photo previously appeared in separate distant incident",
                "matched_incident_ids": [reused_incident_id],
            },
        ],
        is_simulated=False,
    )
    db_session.add(finding)
    await db_session.commit()

    # 3. Call Public Endpoint
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.get(f"/api/v1/incidents/{rep_id}")
        assert resp.status_code == 200
        data = resp.json()["data"]

        # Check image_forensics block exists
        assert "image_forensics" in data
        forensics = data["image_forensics"]
        assert forensics is not None
        assert forensics["overall_verdict"] == "CONTRADICTS"
        assert forensics["total_credibility_adjustment"] == -0.05
        assert forensics["image_count"] == 1
        assert not forensics["is_simulated"]

        # Check image item details
        assert len(forensics["images"]) == 1
        img_item = forensics["images"][0]
        assert img_item["phash"] == "c629293939f68629"
        assert img_item["has_exif"] is True
        assert img_item["time_verdict"] == "SUPPORTS"
        assert img_item["location_verdict"] == "SUPPORTS"
        assert img_item["reuse_verdict"] == "CONTRADICTS"

        # Product Rule P5: matched_incident_ids must be incident IDs only
        assert img_item["matched_incident_ids"] == [reused_incident_id]

        # Product Rule P5: Privacy — no raw GPS coordinates in observed_value
        loc_check = next(c for c in img_item["checks"] if c["check_type"] == "EXIF_LOCATION")
        assert loc_check["observed_value"] == "COORDINATES_PRESENT"
        assert "86.6114" not in str(loc_check["observed_value"])

        # 4. Call Operator Detail Endpoint
        op_resp = await client.get(f"/api/v1/incidents/{rep_id}/operator-detail")
        assert op_resp.status_code == 200
        op_data = op_resp.json()["data"]
        assert "image_forensics" in op_data
        assert op_data["image_forensics"]["overall_verdict"] == "CONTRADICTS"


@pytest.mark.asyncio
async def test_openapi_schema_contains_image_forensics():
    """Verify OpenAPI documentation includes the image_forensics schemas."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.get("/api/v1/openapi.json")
        assert resp.status_code == 200
        spec = resp.json()

        schemas = spec.get("components", {}).get("schemas", {})
        assert "IncidentImageForensicsDetail" in schemas
        assert "ImageForensicItemDetail" in schemas
        assert "ImageForensicCheckDetail" in schemas

        # Verify IncidentDetailPublic schema contains image_forensics property
        detail_schema = schemas.get("IncidentDetailPublic", {})
        props = detail_schema.get("properties", {})
        assert "image_forensics" in props


@pytest.mark.asyncio
async def test_api_incident_detail_without_images_has_null_forensics(db_session: AsyncSession):
    """Verify incident without images returns null image_forensics."""
    source = Source(
        id=uuid.uuid4(),
        source_code="CITIZEN_NO_IMG",
        source_type="CITIZEN_REPORT",
        name="Citizen Web App",
        base_trust_score=0.60,
    )
    db_session.add(source)
    await db_session.flush()

    rep_id = uuid.uuid4()
    report = WeatherReport(
        id=rep_id,
        tracking_id=f"TRK-NOIMG-{uuid.uuid4().hex[:6].upper()}",
        source_id=source.id,
        title="Urban Waterlogging",
        description="Waterlogging on main road.",
        latitude=12.9716,
        longitude=77.5946,
        geom=WKTElement("POINT(77.5946 12.9716)", srid=4326),
        location_name="Bengaluru, Karnataka",
        occurred_at=datetime.datetime(2026, 8, 15, 10, 0, 0, tzinfo=datetime.timezone.utc),
        reported_category="FLOODING",
        verification_status="PENDING",
        credibility_score=0.50,
    )
    db_session.add(report)
    await db_session.commit()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.get(f"/api/v1/incidents/{rep_id}")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["image_forensics"] is None


@pytest.mark.asyncio
async def test_api_incident_detail_missing_exif_neutral(db_session: AsyncSession):
    """Verify missing EXIF yields NEUTRAL verdict with 0.0 credibility adjustment."""
    source = Source(
        id=uuid.uuid4(),
        source_code="CITIZEN_NO_EXIF",
        source_type="CITIZEN_REPORT",
        name="Citizen Web App",
        base_trust_score=0.60,
    )
    db_session.add(source)
    await db_session.flush()

    rep_id = uuid.uuid4()
    report = WeatherReport(
        id=rep_id,
        tracking_id=f"TRK-NOEXIF-{uuid.uuid4().hex[:6].upper()}",
        source_id=source.id,
        title="Hailstorm",
        description="Hailstorm observed.",
        latitude=28.6139,
        longitude=77.2090,
        geom=WKTElement("POINT(77.2090 28.6139)", srid=4326),
        location_name="New Delhi",
        occurred_at=datetime.datetime(2026, 8, 15, 12, 0, 0, tzinfo=datetime.timezone.utc),
        reported_category="CYCLONE_STORM",
        verification_status="PENDING",
        credibility_score=0.55,
    )
    db_session.add(report)

    media = ReportMedia(
        id=uuid.uuid4(),
        report_id=rep_id,
        media_type="IMAGE",
        storage_bucket="weather-evidence",
        storage_key=f"reports/{rep_id}/no_exif.jpg",
        mime_type="image/jpeg",
        file_size_bytes=32000,
        sha256_hash="f" * 64,
    )
    db_session.add(media)

    finding = IncidentImageFinding(
        id=uuid.uuid4(),
        incident_id=rep_id,
        media_id=media.id,
        sha256=media.sha256_hash,
        phash="1111222233334444",
        dhash="0000000000000000",
        has_exif=False,
        time_verdict="NEUTRAL",
        time_difference=None,
        location_verdict="NEUTRAL",
        location_difference=None,
        reuse_verdict="SUPPORTS",
        matched_incident_ids=[],
        overall_verdict="NEUTRAL",
        credibility_adjustment=0.0,
        checks=[
            {
                "check_type": "EXIF_TIME",
                "verdict": "NEUTRAL",
                "reason": "Missing or stripped EXIF metadata is treated as neutral (P1)",
            },
            {
                "check_type": "EXIF_LOCATION",
                "verdict": "NEUTRAL",
                "reason": "Missing or stripped EXIF metadata is treated as neutral (P1)",
            },
            {
                "check_type": "IMAGE_REUSE",
                "verdict": "SUPPORTS",
                "reason": "No previous occurrences detected",
            },
        ],
        is_simulated=False,
    )
    db_session.add(finding)
    await db_session.commit()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.get(f"/api/v1/incidents/{rep_id}")
        assert resp.status_code == 200
        data = resp.json()["data"]
        forensics = data["image_forensics"]
        assert forensics is not None
        assert forensics["overall_verdict"] == "NEUTRAL"
        assert forensics["total_credibility_adjustment"] == 0.0
        assert forensics["images"][0]["has_exif"] is False

