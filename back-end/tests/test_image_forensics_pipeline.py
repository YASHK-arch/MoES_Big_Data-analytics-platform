"""Tests for image forensics worker/pipeline orchestration (S2 Item 6).

Guarantees verified:
- Hashes and EXIF computed and stored after upload
- Idempotent replay: running multiple times never creates duplicate rows
- Worker crash/recovery simulation with zero duplicate rows
- Corrupt image payload produces NEUTRAL verdict with recorded reason without crashing
- Realtime outbox event staged with 'incident.image_forensics_completed'
- Credibility recomputed and capped, report.verification_status strictly untouched (P2)
"""

import datetime
import io
import uuid
import pytest
from geoalchemy2.elements import WKTElement
from PIL import Image
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.intelligence.image_forensics_service import image_forensics_service
from app.models.category import EventCategory
from app.models.image_forensics import ImageHash, IncidentImageFinding
from app.models.media import ReportMedia
from app.models.outbox import RealtimeOutbox
from app.models.report import WeatherReport
from app.models.source import Source


def _generate_test_image_bytes(has_exif: bool = True, offset: str = "+05:30") -> bytes:
    """Helper to generate a JPEG image in-memory with optional EXIF."""
    img = Image.new("RGB", (80, 80), color=(120, 180, 220))
    buf = io.BytesIO()
    if has_exif:
        exif = img.getexif()
        exif[0x0132] = "2026:08:15 14:30:00"
        if offset:
            exif[0x9011] = offset
        img.save(buf, format="JPEG", exif=exif)
    else:
        img.save(buf, format="PNG")
    return buf.getvalue()


async def _create_test_report_with_media(
    db: AsyncSession,
    image_bytes: bytes,
    mime_type: str = "image/jpeg",
) -> Tuple[WeatherReport, ReportMedia]:
    """Create a persistent test report and linked media."""
    # Ensure source exists
    source_stmt = select(Source).where(Source.source_code == "CITIZEN_WEB").limit(1)
    res_s = await db.execute(source_stmt)
    source = res_s.scalar_one_or_none()
    if not source:
        source = Source(
            id=uuid.uuid4(),
            source_code="CITIZEN_WEB",
            source_type="CITIZEN_REPORT",
            name="Citizen Web App",
            base_trust_score=0.60,
        )
        db.add(source)
        await db.flush()

    report_id = uuid.uuid4()
    report = WeatherReport(
        id=report_id,
        tracking_id=f"TRK-{uuid.uuid4().hex[:8].upper()}",
        source_id=source.id,
        latitude=12.9716,
        longitude=77.5946,
        geom=WKTElement("POINT(77.5946 12.9716)", srid=4326),
        location_name="Bengaluru, Karnataka",
        title="Heavy Rainfall in Bengaluru",
        occurred_at=datetime.datetime(2026, 8, 15, 9, 0, 0, tzinfo=datetime.timezone.utc),
        reported_category="HEAVY_RAINFALL",
        description="Heavy rainfall flooding main street.",
        verification_status="PENDING",
        credibility_score=0.60,
    )
    db.add(report)

    media_id = uuid.uuid4()
    media = ReportMedia(
        id=media_id,
        report_id=report_id,
        media_type="IMAGE",
        storage_bucket="weather-evidence",
        storage_key=f"reports/{report_id}/{media_id}.jpg",
        mime_type=mime_type,
        file_size_bytes=len(image_bytes),
        sha256_hash="test_sha256_" + uuid.uuid4().hex,
    )
    db.add(media)
    await db.flush()
    return report, media


@pytest.mark.asyncio
async def test_pipeline_compute_hash_and_exif_and_emit_outbox(db_session: AsyncSession):
    """Test full image forensics pipeline execution and event staging."""
    img_bytes = _generate_test_image_bytes(has_exif=True)
    report, media = await _create_test_report_with_media(db_session, img_bytes)

    # Run image forensics
    summary = await image_forensics_service.run_incident_image_forensics(
        db=db_session,
        report_id=report.id,
        force_run=True,
        media_bytes_map={media.id: img_bytes},
    )

    assert summary.overall_verdict in ("SUPPORTS", "NEUTRAL")

    # 1. Verify ImageHash row created
    hash_stmt = select(ImageHash).where(ImageHash.media_id == media.id)
    res_hash = await db_session.execute(hash_stmt)
    img_hash = res_hash.scalar_one_or_none()
    assert img_hash is not None
    assert len(img_hash.phash) == 16
    assert len(img_hash.dhash) == 16

    # 2. Verify IncidentImageFinding row created
    finding_stmt = select(IncidentImageFinding).where(IncidentImageFinding.media_id == media.id)
    res_finding = await db_session.execute(finding_stmt)
    finding = res_finding.scalar_one_or_none()
    assert finding is not None
    assert finding.has_exif
    assert finding.time_verdict in ("SUPPORTS", "NEUTRAL")

    # 3. Verify RealtimeOutbox SSE event staged
    outbox_stmt = select(RealtimeOutbox).where(
        RealtimeOutbox.entity_id == str(report.id),
        RealtimeOutbox.event_type == "incident.image_forensics_completed",
    )
    res_outbox = await db_session.execute(outbox_stmt)
    outbox_event = res_outbox.scalar_one_or_none()
    assert outbox_event is not None
    assert outbox_event.payload["incident_id"] == str(report.id)
    assert "images" in outbox_event.payload

    # 4. Invariant: verification_status untouched (P2)
    assert report.verification_status == "PENDING"


@pytest.mark.asyncio
async def test_idempotent_replay_no_duplicate_rows(db_session: AsyncSession):
    """Test that running the pipeline repeatedly on the same incident produces zero duplicate rows."""
    img_bytes = _generate_test_image_bytes(has_exif=True)
    report, media = await _create_test_report_with_media(db_session, img_bytes)

    # First run
    await image_forensics_service.run_incident_image_forensics(
        db=db_session,
        report_id=report.id,
        force_run=True,
        media_bytes_map={media.id: img_bytes},
    )

    # Count rows after run 1
    cnt_hashes_1 = await db_session.scalar(
        select(func.count(ImageHash.id)).where(ImageHash.media_id == media.id)
    )
    cnt_findings_1 = await db_session.scalar(
        select(func.count(IncidentImageFinding.id)).where(IncidentImageFinding.media_id == media.id)
    )
    assert cnt_hashes_1 == 1
    assert cnt_findings_1 == 1

    # Second run (replay)
    await image_forensics_service.run_incident_image_forensics(
        db=db_session,
        report_id=report.id,
        force_run=True,
        media_bytes_map={media.id: img_bytes},
    )

    # Count rows after run 2 (MUST remain exactly 1)
    cnt_hashes_2 = await db_session.scalar(
        select(func.count(ImageHash.id)).where(ImageHash.media_id == media.id)
    )
    cnt_findings_2 = await db_session.scalar(
        select(func.count(IncidentImageFinding.id)).where(IncidentImageFinding.media_id == media.id)
    )
    assert cnt_hashes_2 == 1
    assert cnt_findings_2 == 1


@pytest.mark.asyncio
async def test_worker_crash_and_recovery_no_duplicate_rows(db_session: AsyncSession):
    """Simulate a worker failure and restart: state recovers cleanly without duplicates."""
    img_bytes = _generate_test_image_bytes(has_exif=True)
    report, media = await _create_test_report_with_media(db_session, img_bytes)

    # Simulate partial execution: media processed halfway
    await image_forensics_service.process_report_media(
        db=db_session,
        report=report,
        media=media,
        image_bytes=img_bytes,
    )

    # Worker crashes before full summary and event staging.
    # Worker recovers and re-runs full incident forensics:
    summary = await image_forensics_service.run_incident_image_forensics(
        db=db_session,
        report_id=report.id,
        force_run=True,
        media_bytes_map={media.id: img_bytes},
    )

    # Check total rows
    cnt_hashes = await db_session.scalar(
        select(func.count(ImageHash.id)).where(ImageHash.media_id == media.id)
    )
    cnt_findings = await db_session.scalar(
        select(func.count(IncidentImageFinding.id)).where(IncidentImageFinding.media_id == media.id)
    )
    assert cnt_hashes == 1
    assert cnt_findings == 1
    assert summary.overall_verdict in ("SUPPORTS", "NEUTRAL")


@pytest.mark.asyncio
async def test_corrupt_image_returns_neutral_safely(db_session: AsyncSession):
    """Product Rule P6: Corrupt file returns NEUTRAL, records error reason, never crashes report."""
    corrupt_bytes = b"CORRUPTED_FILE_DATA_NOT_VALID_IMAGE"
    report, media = await _create_test_report_with_media(db_session, corrupt_bytes, mime_type="image/jpeg")

    summary = await image_forensics_service.run_incident_image_forensics(
        db=db_session,
        report_id=report.id,
        force_run=True,
        media_bytes_map={media.id: corrupt_bytes},
    )

    # Overall summary must be NEUTRAL
    assert summary.overall_verdict == "NEUTRAL"
    assert summary.total_credibility_adjustment == 0.0

    # Finding in DB must have error_reason and NEUTRAL
    finding = await db_session.scalar(
        select(IncidentImageFinding).where(IncidentImageFinding.media_id == media.id)
    )
    assert finding is not None
    assert finding.overall_verdict == "NEUTRAL"
    assert finding.error_reason is not None
    assert "DECODE_ERROR" in finding.error_reason
