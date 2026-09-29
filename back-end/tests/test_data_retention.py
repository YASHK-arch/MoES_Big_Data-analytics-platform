"""Automated unit and integration test suite for Data Retention and Archival (C2)."""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from geoalchemy2.elements import WKTElement
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.archive import WeatherReportArchive
from app.models.evidence import EvidenceItem
from app.models.media import ReportMedia
from app.models.observation import WeatherObservation
from app.models.report import WeatherReport
from app.models.source import Source
from app.models.user import User
from app.models.verification import VerificationEvent
from app.services.retention_service import retention_service


@pytest.fixture
async def sample_source(db_session: AsyncSession) -> Source:
    """Create a persistent test source for retention tests."""
    source_code = f"SRC_RET_{uuid.uuid4().hex[:8].upper()}"
    src = Source(
        id=uuid.uuid4(),
        source_code=source_code,
        name="Retention Test Source",
        source_type="CITIZEN_REPORT",
        base_trust_score=0.60,
    )
    db_session.add(src)
    await db_session.flush()
    return src


@pytest.fixture
async def sample_user(db_session: AsyncSession) -> User:
    """Create a test user for verification events."""
    user = User(
        id=uuid.uuid4(),
        email=f"reviewer_{uuid.uuid4().hex[:6]}@example.com",
        hashed_password="hashed_pw_test",
        full_name="Reviewer Test",
        role="REVIEWER",
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()
    return user


@pytest.mark.asyncio
async def test_retention_window_boundary(db_session: AsyncSession, sample_source: Source):
    """Test boundary condition: expired records are pruned, fresh records preserved."""
    now = datetime.now(timezone.utc)
    retention_days = 6

    # 1. Expired report (7 days old)
    expired_time = now - timedelta(days=7)
    expired_report = WeatherReport(
        id=uuid.uuid4(),
        tracking_id=f"RPT-EXP-{uuid.uuid4().hex[:6].upper()}",
        source_id=sample_source.id,
        title="Expired Heavy Rain Report",
        description="Expired incident description",
        geom=WKTElement("SRID=4326;POINT(77.5946 12.9716)", extended=True),
        latitude=12.9716,
        longitude=77.5946,
        occurred_at=expired_time,
        created_at=expired_time,
        processing_status="COMPLETED",
        verification_status="PENDING",
        credibility_score=0.50,
    )

    # 2. Fresh report (5 days old)
    fresh_time = now - timedelta(days=5)
    fresh_report = WeatherReport(
        id=uuid.uuid4(),
        tracking_id=f"RPT-FRESH-{uuid.uuid4().hex[:6].upper()}",
        source_id=sample_source.id,
        title="Fresh Heavy Rain Report",
        description="Fresh incident description",
        geom=WKTElement("SRID=4326;POINT(77.5946 12.9716)", extended=True),
        latitude=12.9716,
        longitude=77.5946,
        occurred_at=fresh_time,
        created_at=fresh_time,
        processing_status="COMPLETED",
        verification_status="PENDING",
        credibility_score=0.50,
    )

    db_session.add_all([expired_report, fresh_report])
    await db_session.flush()

    # Run retention cycle
    res = await retention_service.run_retention_cycle(
        session=db_session,
        retention_days=retention_days,
        dry_run=False,
    )

    assert res.reports_deleted >= 1

    # Verify expired report deleted, fresh report preserved
    check_expired = await db_session.get(WeatherReport, expired_report.id)
    check_fresh = await db_session.get(WeatherReport, fresh_report.id)

    assert check_expired is None
    assert check_fresh is not None
    assert check_fresh.id == fresh_report.id


@pytest.mark.asyncio
async def test_verified_reports_archival(
    db_session: AsyncSession, sample_source: Source, sample_user: User
):
    """Test that VERIFIED reports are archived into weather_reports_archive before deletion."""
    now = datetime.now(timezone.utc)
    retention_days = 6
    expired_time = now - timedelta(days=8)

    verified_rep = WeatherReport(
        id=uuid.uuid4(),
        tracking_id=f"RPT-VER-{uuid.uuid4().hex[:6].upper()}",
        source_id=sample_source.id,
        title="Verified Flooding Incident",
        description="Verified waterlogging on main road",
        location_name="Indiranagar 100ft Road",
        geom=WKTElement("SRID=4326;POINT(77.6408 12.9784)", extended=True),
        latitude=12.9784,
        longitude=77.6408,
        occurred_at=expired_time,
        created_at=expired_time,
        processing_status="COMPLETED",
        verification_status="VERIFIED",
        credibility_score=0.92,
        credibility_explanation={"explanation": "Verified by authority operator."},
    )
    db_session.add(verified_rep)
    await db_session.flush()

    # Add verification event and media
    v_event = VerificationEvent(
        report_id=verified_rep.id,
        user_id=sample_user.id,
        previous_status="PENDING",
        new_status="VERIFIED",
        notes="Confirmed on ground.",
    )
    media = ReportMedia(
        report_id=verified_rep.id,
        media_type="IMAGE",
        storage_bucket="weather-media",
        storage_key=f"reports/{verified_rep.id}/photo.jpg",
        mime_type="image/jpeg",
        file_size_bytes=102400,
        sha256_hash="abcdef1234567890",
    )
    db_session.add_all([v_event, media])
    await db_session.flush()

    # Run retention cycle
    res = await retention_service.run_retention_cycle(
        session=db_session,
        retention_days=retention_days,
        dry_run=False,
    )

    assert res.reports_archived >= 1
    assert res.reports_deleted >= 1

    # Verify deleted from weather_reports
    deleted_check = await db_session.get(WeatherReport, verified_rep.id)
    assert deleted_check is None

    # Verify archived into weather_reports_archive with full attributes
    archive_row = await db_session.get(WeatherReportArchive, verified_rep.id)
    assert archive_row is not None
    assert archive_row.tracking_id == verified_rep.tracking_id
    assert archive_row.title == "Verified Flooding Incident"
    assert archive_row.location_name == "Indiranagar 100ft Road"
    assert archive_row.latitude == 12.9784
    assert archive_row.longitude == 77.6408
    assert archive_row.verification_status == "VERIFIED"
    assert archive_row.credibility_score == 0.92
    assert archive_row.archived_at is not None


@pytest.mark.asyncio
async def test_unverified_reports_hard_deletion(
    db_session: AsyncSession, sample_source: Source
):
    """Test that expired unverified reports are hard-deleted without archival."""
    now = datetime.now(timezone.utc)
    retention_days = 6
    expired_time = now - timedelta(days=10)

    rejected_rep = WeatherReport(
        id=uuid.uuid4(),
        tracking_id=f"RPT-REJ-{uuid.uuid4().hex[:6].upper()}",
        source_id=sample_source.id,
        title="Spam / Rejected Report",
        description="Fake incident report",
        geom=WKTElement("SRID=4326;POINT(77.5946 12.9716)", extended=True),
        latitude=12.9716,
        longitude=77.5946,
        occurred_at=expired_time,
        created_at=expired_time,
        processing_status="COMPLETED",
        verification_status="REJECTED",
        credibility_score=0.10,
    )
    db_session.add(rejected_rep)
    await db_session.flush()

    # Run retention cycle
    await retention_service.run_retention_cycle(
        session=db_session,
        retention_days=retention_days,
        dry_run=False,
    )

    # Verify deleted from weather_reports
    assert (await db_session.get(WeatherReport, rejected_rep.id)) is None
    # Verify NOT in weather_reports_archive
    assert (await db_session.get(WeatherReportArchive, rejected_rep.id)) is None


@pytest.mark.asyncio
async def test_observations_and_evidence_deletion(
    db_session: AsyncSession, sample_source: Source
):
    """Test that expired observations and evidence items are pruned while fresh ones remain."""
    now = datetime.now(timezone.utc)
    retention_days = 6

    # 1. Expired observation (8 days old)
    expired_obs = WeatherObservation(
        id=uuid.uuid4(),
        source_id=sample_source.id,
        station_code="AWS_EXP_01",
        station_name="Old Test AWS Station",
        geom=WKTElement("SRID=4326;POINT(77.5946 12.9716)", extended=True),
        observed_at=now - timedelta(days=8),
        rainfall_mm=45.2,
    )
    # 2. Fresh observation (2 days old)
    fresh_obs = WeatherObservation(
        id=uuid.uuid4(),
        source_id=sample_source.id,
        station_code="AWS_FRESH_01",
        station_name="Fresh Test AWS Station",
        geom=WKTElement("SRID=4326;POINT(77.5946 12.9716)", extended=True),
        observed_at=now - timedelta(days=2),
        rainfall_mm=12.0,
    )

    # 3. Expired evidence (9 days old)
    expired_evi = EvidenceItem(
        id=uuid.uuid4(),
        source_id=sample_source.id,
        external_id=f"NEWS_{uuid.uuid4().hex[:8]}",
        title="Old News Article About Rains",
        publisher_domain="example.com",
        published_at=now - timedelta(days=9),
    )
    # 4. Fresh evidence (1 day old)
    fresh_evi = EvidenceItem(
        id=uuid.uuid4(),
        source_id=sample_source.id,
        external_id=f"NEWS_{uuid.uuid4().hex[:8]}",
        title="Recent Weather Bulletin",
        publisher_domain="example.com",
        published_at=now - timedelta(days=1),
    )

    db_session.add_all([expired_obs, fresh_obs, expired_evi, fresh_evi])
    await db_session.flush()

    # Run retention cycle
    res = await retention_service.run_retention_cycle(
        session=db_session,
        retention_days=retention_days,
        dry_run=False,
    )

    assert res.observations_deleted >= 1
    assert res.evidence_deleted >= 1

    # Verify expired pruned
    assert (await db_session.get(WeatherObservation, expired_obs.id)) is None
    assert (await db_session.get(EvidenceItem, expired_evi.id)) is None

    # Verify fresh preserved
    assert (await db_session.get(WeatherObservation, fresh_obs.id)) is not None
    assert (await db_session.get(EvidenceItem, fresh_evi.id)) is not None


@pytest.mark.asyncio
async def test_retention_idempotency_double_run(
    db_session: AsyncSession, sample_source: Source
):
    """Test that running the retention cycle twice consecutively is completely idempotent."""
    now = datetime.now(timezone.utc)
    retention_days = 6
    expired_time = now - timedelta(days=7)

    verified_rep = WeatherReport(
        id=uuid.uuid4(),
        tracking_id=f"RPT-IDEM-{uuid.uuid4().hex[:6].upper()}",
        source_id=sample_source.id,
        title="Idempotency Test Report",
        geom=WKTElement("SRID=4326;POINT(77.5946 12.9716)", extended=True),
        latitude=12.9716,
        longitude=77.5946,
        occurred_at=expired_time,
        created_at=expired_time,
        processing_status="COMPLETED",
        verification_status="VERIFIED",
        credibility_score=0.88,
    )
    db_session.add(verified_rep)
    await db_session.flush()

    # First run: should archive and delete
    res1 = await retention_service.run_retention_cycle(
        session=db_session,
        retention_days=retention_days,
        dry_run=False,
    )
    assert res1.reports_archived >= 1

    # Second run: should safely execute with 0 records found without error
    res2 = await retention_service.run_retention_cycle(
        session=db_session,
        retention_days=retention_days,
        dry_run=False,
    )
    assert len(res2.errors) == 0

    # Ensure exactly 1 copy exists in archive
    stmt = (
        select(func.count(WeatherReportArchive.id))
        .where(WeatherReportArchive.id == verified_rep.id)
    )
    count = (await db_session.execute(stmt)).scalar_one()
    assert count == 1


@pytest.mark.asyncio
async def test_retention_dry_run_produces_no_writes(
    db_session: AsyncSession, sample_source: Source
):
    """Test that dry_run=True computes statistics without mutating the database."""
    now = datetime.now(timezone.utc)
    retention_days = 6
    expired_time = now - timedelta(days=8)

    verified_rep = WeatherReport(
        id=uuid.uuid4(),
        tracking_id=f"RPT-DRY-{uuid.uuid4().hex[:6].upper()}",
        source_id=sample_source.id,
        title="Dry Run Test Report",
        geom=WKTElement("SRID=4326;POINT(77.5946 12.9716)", extended=True),
        latitude=12.9716,
        longitude=77.5946,
        occurred_at=expired_time,
        created_at=expired_time,
        processing_status="COMPLETED",
        verification_status="VERIFIED",
        credibility_score=0.90,
    )
    db_session.add(verified_rep)
    await db_session.flush()

    # Dry-run execution
    res = await retention_service.run_retention_cycle(
        session=db_session,
        retention_days=retention_days,
        dry_run=True,
    )

    assert res.dry_run is True
    assert res.reports_archived >= 1
    assert res.reports_deleted >= 1

    # Verify that database records were NOT touched
    check_rep = await db_session.get(WeatherReport, verified_rep.id)
    assert check_rep is not None
    assert check_rep.id == verified_rep.id

    check_arch = await db_session.get(WeatherReportArchive, verified_rep.id)
    assert check_arch is None
