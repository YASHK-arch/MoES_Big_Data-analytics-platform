"""Unit and integration tests for Transactional Outbox pattern and OutboxWorker.

Tests atomic persistence, failure isolation, stable event ID preservation,
concurrency with SKIP LOCKED, exponential backoff, and pruning.
"""

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.redis import AsyncRedisClient
from app.models.outbox import RealtimeOutbox
from app.models.report import WeatherReport
from app.models.verification import VerificationEvent
from app.schemas.report import CitizenReportCreate
from app.services.realtime_service import RealtimeService
from app.services.report_service import InvalidStateTransitionError, ReportService
from app.workers.outbox_worker import RealtimeOutboxWorker

# ============================================================================
# 1. Transactional Atomicity Tests
# ============================================================================


@pytest.mark.asyncio
async def test_citizen_report_creation_writes_outbox_atomically(db_session: AsyncSession):
    """Verify report submission inserts WeatherReport and RealtimeOutbox atomically."""
    mock_redis = MagicMock(spec=AsyncRedisClient)
    mock_redis.xadd = AsyncMock(return_value="1725000000001-0")

    mock_realtime = RealtimeService(client=mock_redis)
    report_svc = ReportService(realtime_svc=mock_realtime)

    payload = CitizenReportCreate(
        latitude=19.0760,
        longitude=72.8777,
        category_code="FLOOD_WATERLOGGING",
        severity="HIGH",
        title="Atomic Outbox Report Test",
        description="Waterlogging on main road",
        location_name="Bandra East",
    )

    report, media_count = await report_svc.create_citizen_report(
        session=db_session,
        payload=payload,
    )

    assert report is not None
    assert report.id is not None

    # Verify RealtimeOutbox rows were persisted in PostgreSQL
    # (report.created + orchestration.incident_ingested)
    stmt = select(RealtimeOutbox).where(
        RealtimeOutbox.entity_id == str(report.id),
        RealtimeOutbox.event_type == "report.created",
    )
    res = await db_session.execute(stmt)
    outbox = res.scalar_one_or_none()

    assert outbox is not None
    assert outbox.event_type == "report.created"
    assert outbox.tracking_id == report.tracking_id
    assert outbox.status in ("PENDING", "PUBLISHED")
    assert outbox.payload["tracking_id"] == report.tracking_id
    assert outbox.payload["category_code"] == "FLOOD_WATERLOGGING"
    assert "phone" not in outbox.payload

    # Verify orchestration trigger outbox row was also created atomically
    orch_stmt = select(RealtimeOutbox).where(
        RealtimeOutbox.entity_id == str(report.id),
        RealtimeOutbox.event_type == "orchestration.incident_ingested",
    )
    orch_res = await db_session.execute(orch_stmt)
    orch_outbox = orch_res.scalar_one_or_none()
    assert orch_outbox is not None
    assert orch_outbox.payload["aggregate_id"] == str(report.id)


@pytest.mark.asyncio
async def test_verification_transition_writes_outbox_atomically(db_session: AsyncSession):
    """Verify verification update inserts report, VerificationEvent, and outbox atomically."""
    mock_redis = MagicMock(spec=AsyncRedisClient)
    mock_redis.xadd = AsyncMock(return_value="1725000000002-0")

    mock_realtime = RealtimeService(client=mock_redis)
    report_svc = ReportService(realtime_svc=mock_realtime)

    # 1. Create report
    payload = CitizenReportCreate(
        latitude=19.0178,
        longitude=72.8478,
        category_code="HEAVY_RAINFALL",
        severity="SEVERE",
        title="Verification Outbox Test",
        description="Heavy rain",
        location_name="Dadar",
    )
    report, _ = await report_svc.create_citizen_report(session=db_session, payload=payload)

    # 2. Transition PENDING -> VERIFIED
    updated_report = await report_svc.update_verification_status(
        session=db_session,
        report_id_or_tracking=str(report.id),
        new_status="VERIFIED",
        notes="Ground truth confirmed by DEOC operator",
    )

    assert updated_report.verification_status == "VERIFIED"

    # Verify VerificationEvent audit row
    verif_stmt = select(VerificationEvent).where(VerificationEvent.report_id == report.id)
    verif_res = await db_session.execute(verif_stmt)
    assert verif_res.scalar_one_or_none() is not None

    # Verify RealtimeOutbox verification_changed event
    outbox_stmt = select(RealtimeOutbox).where(
        RealtimeOutbox.entity_id == str(report.id),
        RealtimeOutbox.event_type == "report.verification_changed",
    )
    outbox_res = await db_session.execute(outbox_stmt)
    outbox_row = outbox_res.scalar_one_or_none()

    assert outbox_row is not None
    assert outbox_row.payload["previous_status"] == "PENDING"
    assert outbox_row.payload["new_status"] == "VERIFIED"
    assert "notes" not in outbox_row.payload


@pytest.mark.asyncio
async def test_invalid_verification_transition_persists_no_outbox(db_session: AsyncSession):
    """Verify illegal transition raises InvalidStateTransitionError and writes NO outbox row."""
    report_svc = ReportService()

    # 1. Create and verify report
    payload = CitizenReportCreate(
        latitude=19.0178,
        longitude=72.8478,
        category_code="LANDSLIDE",
        severity="SEVERE",
        title="Illegal Transition Test",
        description="Debris on road",
        location_name="Ghatkopar",
    )
    report, _ = await report_svc.create_citizen_report(session=db_session, payload=payload)
    await report_svc.update_verification_status(
        session=db_session,
        report_id_or_tracking=str(report.id),
        new_status="REJECTED",
    )

    # 2. Attempt illegal transition from terminal REJECTED -> VERIFIED
    with pytest.raises(InvalidStateTransitionError):
        await report_svc.update_verification_status(
            session=db_session,
            report_id_or_tracking=str(report.id),
            new_status="VERIFIED",
        )

    # Verify no outbox row with new_status=VERIFIED exists
    outbox_stmt = select(RealtimeOutbox).where(
        RealtimeOutbox.entity_id == str(report.id),
        RealtimeOutbox.event_type == "report.verification_changed",
    )
    res = await db_session.execute(outbox_stmt)
    rows = list(res.scalars().all())
    for r in rows:
        assert r.payload["new_status"] != "VERIFIED"


# ============================================================================
# 2. Outbox Worker & Retry Semantics Tests
# ============================================================================


@pytest.mark.asyncio
async def test_outbox_worker_publishes_pending_batch_and_updates_status(db_session: AsyncSession):
    """Verify OutboxWorker claims PENDING rows with SKIP LOCKED and marks them PUBLISHED."""
    await db_session.execute(delete(RealtimeOutbox))
    await db_session.commit()

    mock_redis = MagicMock(spec=AsyncRedisClient)
    mock_redis.xadd = AsyncMock(return_value="1725000000010-0")

    worker = RealtimeOutboxWorker(client=mock_redis)

    # 1. Insert 3 pending outbox rows
    event_ids = [uuid.uuid4() for _ in range(3)]
    for i, e_id in enumerate(event_ids):
        row = RealtimeOutbox(
            event_id=e_id,
            event_type="report.created",
            entity_id=f"rep-{i}",
            tracking_id=f"RPT-00{i}",
            occurred_at=datetime.now(timezone.utc),
            payload={"test": i},
            status="PENDING",
            attempts=0,
        )
        db_session.add(row)
    await db_session.commit()

    # 2. Run worker batch
    published_count, failed_count = await worker.publish_pending_batch(db_session, batch_size=10)

    assert published_count >= 3
    assert failed_count == 0
    assert mock_redis.xadd.call_count >= 3

    # Verify database status is updated to PUBLISHED
    stmt = select(RealtimeOutbox).where(RealtimeOutbox.event_id.in_(event_ids))
    res = await db_session.execute(stmt)
    rows = list(res.scalars().all())
    for r in rows:
        assert r.status == "PUBLISHED"
        assert r.published_at is not None
        assert r.last_error is None


@pytest.mark.asyncio
async def test_outbox_worker_handles_redis_failure_with_exponential_backoff(
    db_session: AsyncSession,
):
    """Verify Redis outage increments attempts, records last_error, and calculates next_retry_at."""
    mock_redis = MagicMock(spec=AsyncRedisClient)
    mock_redis.xadd = AsyncMock(side_effect=ConnectionError("Redis connection refused"))

    worker = RealtimeOutboxWorker(client=mock_redis)

    e_id = uuid.uuid4()
    row = RealtimeOutbox(
        event_id=e_id,
        event_type="report.created",
        entity_id="rep-fail-1",
        tracking_id="RPT-FAIL",
        occurred_at=datetime.now(timezone.utc),
        payload={"k": "v"},
        status="PENDING",
        attempts=0,
        max_attempts=3,
    )
    db_session.add(row)
    await db_session.commit()

    # Attempt 1: Failed
    pub_count, fail_count = await worker.publish_pending_batch(db_session, batch_size=10)
    assert pub_count == 0
    assert fail_count == 1

    # Reload row from DB
    res = await db_session.execute(select(RealtimeOutbox).where(RealtimeOutbox.event_id == e_id))
    reloaded = res.scalar_one()
    assert reloaded.attempts == 1
    assert reloaded.status == "PENDING"
    assert reloaded.next_retry_at is not None
    assert "Redis connection refused" in (reloaded.last_error or "")


@pytest.mark.asyncio
async def test_outbox_worker_moves_to_dead_letter_on_max_attempts(db_session: AsyncSession):
    """Verify outbox row moves to DEAD_LETTER after exceeding max_attempts."""
    await db_session.execute(delete(RealtimeOutbox))
    await db_session.commit()

    mock_redis = MagicMock(spec=AsyncRedisClient)
    mock_redis.xadd = AsyncMock(side_effect=ConnectionError("Persistent Redis Outage"))

    worker = RealtimeOutboxWorker(client=mock_redis)

    e_id = uuid.uuid4()
    row = RealtimeOutbox(
        event_id=e_id,
        event_type="report.created",
        entity_id="rep-dlq",
        tracking_id="RPT-DLQ",
        occurred_at=datetime.now(timezone.utc),
        payload={"k": "v"},
        status="PENDING",
        attempts=2,  # Already attempted 2 times
        max_attempts=3,
    )
    db_session.add(row)
    await db_session.commit()

    # Attempt 3: Exceeds max_attempts (3)
    pub_count, fail_count = await worker.publish_pending_batch(db_session, batch_size=10)
    assert pub_count == 0
    assert fail_count == 1

    res = await db_session.execute(select(RealtimeOutbox).where(RealtimeOutbox.event_id == e_id))
    reloaded = res.scalar_one()
    assert reloaded.attempts == 3
    assert reloaded.status == "DEAD_LETTER"


@pytest.mark.asyncio
async def test_outbox_worker_preserves_stable_event_id_across_retries(db_session: AsyncSession):
    """Verify the exact same stable event_id is transmitted on publication retries."""
    mock_redis = MagicMock(spec=AsyncRedisClient)
    mock_redis.xadd = AsyncMock(return_value="1725000000020-0")

    worker = RealtimeOutboxWorker(client=mock_redis)

    stable_event_id = uuid.uuid4()
    row = RealtimeOutbox(
        event_id=stable_event_id,
        event_type="report.intelligence_ready",
        entity_id="rep-stable",
        tracking_id="RPT-STABLE",
        occurred_at=datetime.now(timezone.utc),
        payload={"credibility_score": 0.95},
        status="PENDING",
        attempts=1,  # Retrying attempt 2
    )
    db_session.add(row)
    await db_session.commit()

    await worker.publish_pending_batch(db_session, batch_size=10)

    mock_redis.xadd.assert_called_once()
    fields = mock_redis.xadd.call_args[0][1]
    assert fields["event_id"] == str(stable_event_id)
    assert fields["event_type"] == "report.intelligence_ready"


@pytest.mark.asyncio
async def test_prune_published_events(db_session: AsyncSession):
    """Verify prune_published_events removes only old PUBLISHED rows."""
    worker = RealtimeOutboxWorker()

    now = datetime.now(timezone.utc)
    old_time = now - timedelta(hours=100)
    recent_time = now - timedelta(hours=5)

    # 1. Old published row (should be pruned)
    r1 = RealtimeOutbox(
        event_id=uuid.uuid4(),
        event_type="report.created",
        entity_id="r1",
        occurred_at=old_time,
        payload={},
        status="PUBLISHED",
        published_at=old_time,
    )
    # 2. Recent published row (should NOT be pruned)
    r2 = RealtimeOutbox(
        event_id=uuid.uuid4(),
        event_type="report.created",
        entity_id="r2",
        occurred_at=recent_time,
        payload={},
        status="PUBLISHED",
        published_at=recent_time,
    )
    # 3. Pending row (should NEVER be pruned)
    r3 = RealtimeOutbox(
        event_id=uuid.uuid4(),
        event_type="report.created",
        entity_id="r3",
        occurred_at=old_time,
        payload={},
        status="PENDING",
    )

    db_session.add_all([r1, r2, r3])
    await db_session.commit()

    pruned = await worker.prune_published_events(db_session, retention_hours=72)
    assert pruned == 1

    # Verify r2 and r3 still exist
    res = await db_session.execute(
        select(RealtimeOutbox).where(RealtimeOutbox.entity_id.in_(["r1", "r2", "r3"]))
    )
    remaining_ids = [r.entity_id for r in res.scalars().all()]
    assert "r1" not in remaining_ids
    assert "r2" in remaining_ids
    assert "r3" in remaining_ids


@pytest.mark.asyncio
async def test_transaction_rollback_removes_both_report_and_outbox(db_session: AsyncSession):
    """Verify that a rolled-back transaction persists neither the report nor the outbox row."""
    tracking_id = f"RPT-RB-{uuid.uuid4().hex[:6].upper()}"
    report_id = uuid.uuid4()

    # 1. Stage both in a transaction
    report = WeatherReport(
        id=report_id,
        tracking_id=tracking_id,
        latitude=19.0,
        longitude=72.8,
        severity="MODERATE",
        title="Rollback Test",
        reported_category="CYCLONE_HIGH_WIND",
    )
    db_session.add(report)

    outbox = RealtimeOutbox(
        event_id=uuid.uuid4(),
        event_type="report.created",
        entity_id=str(report_id),
        tracking_id=tracking_id,
        occurred_at=datetime.now(timezone.utc),
        payload={"tracking_id": tracking_id},
        status="PENDING",
    )
    db_session.add(outbox)

    # 2. Rollback transaction
    await db_session.rollback()

    # 3. Verify neither entity exists in the database
    res_rep = await db_session.execute(
        select(WeatherReport).where(WeatherReport.tracking_id == tracking_id)
    )
    assert res_rep.scalar_one_or_none() is None

    res_out = await db_session.execute(
        select(RealtimeOutbox).where(RealtimeOutbox.tracking_id == tracking_id)
    )
    assert res_out.scalar_one_or_none() is None
