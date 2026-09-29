import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import select

from app.db.session import async_session_factory
from app.ingestion.demo_adapter import DemoSeedAdapter
from app.ingestion.exceptions import NormalizationError
from app.ingestion.normalizer import EventNormalizer
from app.ingestion.registry import AdapterRegistry
from app.ingestion.schemas import NormalizedIngestionEvent, RawIngestionEvent
from app.models.report import WeatherReport
from app.services.report_service import report_service
from app.services.stream_service import StreamService
from app.workers.ingestion_worker import IngestionWorker


# 1. Normalization Tests
def test_normalizer_valid_representative_record():
    """Test normalizing a standard representative weather event record."""
    raw = RawIngestionEvent(
        source_code="IMD_AWS",
        external_id="AWS-MUM-20260829-01",
        payload={
            "title": "Severe Rain and Gale Winds in Colaba",
            "description": "Rainfall exceeding 45mm in 1 hour recorded at station.",
            "latitude": "18.9067",
            "longitude": "72.8147",
            "location_name": "Colaba, Mumbai, Maharashtra",
            "severity": "severe",
            "category": "heavy_rain",
            "occurred_at": "2026-08-29T08:30:00Z",
        },
    )

    norm = EventNormalizer.normalize(raw)

    assert norm.source_code == "IMD_AWS"
    assert norm.external_id == "AWS-MUM-20260829-01"
    assert norm.title == "Severe Rain and Gale Winds in Colaba"
    assert norm.latitude == 18.9067
    assert norm.longitude == 72.8147
    assert norm.severity == "SEVERE"
    assert norm.category_code == "HEAVY_RAINFALL"
    assert norm.location_name == "Colaba, Mumbai, Maharashtra"
    assert norm.occurred_at.tzinfo == timezone.utc


def test_normalizer_severity_mapping():
    """Test mapping of source terms like 'critical', 'extreme', 'warning' to platform domain."""
    for term in ["critical", "extreme", "severe", "danger", "red"]:
        raw = RawIngestionEvent(
            source_code="TEST_FEED",
            payload={"title": "Test", "latitude": 19.0, "longitude": 73.0, "severity": term},
        )
        norm = EventNormalizer.normalize(raw)
        assert norm.severity == "SEVERE"

    for term in ["high", "orange", "warning"]:
        raw = RawIngestionEvent(
            source_code="TEST_FEED",
            payload={"title": "Test", "latitude": 19.0, "longitude": 73.0, "severity": term},
        )
        norm = EventNormalizer.normalize(raw)
        assert norm.severity == "HIGH"


def test_normalizer_invalid_coordinates():
    """Test rejection of out-of-bounds or non-numeric coordinates."""
    # Latitude > 90
    raw1 = RawIngestionEvent(
        source_code="TEST_FEED",
        payload={"title": "Test", "latitude": 95.0, "longitude": 75.0},
    )
    with pytest.raises(NormalizationError) as exc1:
        EventNormalizer.normalize(raw1)
    assert "latitude" in str(exc1.value)

    # Longitude < -180
    raw2 = RawIngestionEvent(
        source_code="TEST_FEED",
        payload={"title": "Test", "latitude": 19.0, "longitude": -195.0},
    )
    with pytest.raises(NormalizationError) as exc2:
        EventNormalizer.normalize(raw2)
    assert "longitude" in str(exc2.value)

    # Non-numeric coordinate
    raw3 = RawIngestionEvent(
        source_code="TEST_FEED",
        payload={"title": "Test", "latitude": "invalid_lat", "longitude": 75.0},
    )
    with pytest.raises(NormalizationError) as exc3:
        EventNormalizer.normalize(raw3)
    assert "latitude" in str(exc3.value)


def test_normalizer_invalid_timestamps():
    """Test rejection of future-skewed or malformed timestamps."""
    now = datetime.now(timezone.utc)

    # Date skewed > 24 hours into the future
    future_date = (now + timedelta(days=2)).isoformat()
    raw_future = RawIngestionEvent(
        source_code="TEST_FEED",
        payload={
            "title": "Future Event",
            "latitude": 19.0,
            "longitude": 73.0,
            "occurred_at": future_date,
        },
    )
    with pytest.raises(NormalizationError) as exc_fut:
        EventNormalizer.normalize(raw_future)
    assert "future" in str(exc_fut.value)

    # Unrecognized date format
    raw_malformed = RawIngestionEvent(
        source_code="TEST_FEED",
        payload={
            "title": "Bad Date",
            "latitude": 19.0,
            "longitude": 73.0,
            "occurred_at": "not-a-valid-date",
        },
    )
    with pytest.raises(NormalizationError) as exc_mal:
        EventNormalizer.normalize(raw_malformed)
    assert "occurred_at" in str(exc_mal.value)


# 2. Ingestion Adapter & Registry Tests
@pytest.mark.asyncio
async def test_demo_seed_adapter_and_registry():
    """Test BaseIngestionAdapter, DemoSeedAdapter, and AdapterRegistry discovery."""
    registry = AdapterRegistry()
    adapter = DemoSeedAdapter(source_code="DEMO_TEST")

    registry.register(adapter)
    assert registry.get("DEMO_TEST") is adapter
    assert len(registry.list_adapters()) == 1

    events = await adapter.ingest()
    assert len(events) == 2
    assert all(isinstance(ev, NormalizedIngestionEvent) for ev in events)
    assert events[0].source_code == "DEMO_TEST"
    assert events[0].severity in {"MODERATE", "HIGH", "SEVERE"}


# 3. Redis Stream Service Unit Tests
@pytest.mark.asyncio
async def test_stream_service_publish_and_ack():
    """Test publishing and acknowledging events via StreamService."""
    mock_redis = MagicMock()
    mock_redis.xadd = AsyncMock(return_value="1724920000000-0")
    mock_redis.xgroup_create = AsyncMock(return_value=True)
    mock_redis.xack = AsyncMock(return_value=1)

    service = StreamService(client=mock_redis)

    event = NormalizedIngestionEvent(
        source_code="TEST_STREAM",
        external_id="EXT-12345",
        title="Stream Test Event",
        latitude=19.0760,
        longitude=72.8777,
        occurred_at=datetime.now(timezone.utc),
    )

    # Publish
    msg_id = await service.publish_event(event, stream_name="stream:test")
    assert msg_id == "1724920000000-0"
    mock_redis.xadd.assert_called_once()

    # Ack
    acked = await service.ack_event(msg_id, stream_name="stream:test", group_name="group:test")
    assert acked is True
    mock_redis.xack.assert_called_once_with("stream:test", "group:test", "1724920000000-0")


# 4. Database Persistence & Idempotency Integration Tests
@pytest.mark.asyncio
async def test_persistence_and_idempotency_path():
    """Test persisting normalized events into PostgreSQL and verifying idempotency."""
    async with async_session_factory() as session:
        unique_ext_id = f"IDEMP-TEST-{uuid.uuid4().hex[:8]}"

        event = NormalizedIngestionEvent(
            source_code="AUTOMATED_IDEMP_TEST",
            external_id=unique_ext_id,
            category_code="FLOOD_WATERLOGGING",
            severity="HIGH",
            title="Idempotency Test Flash Flood",
            description="Testing duplicate event insertion prevention.",
            latitude=19.2183,
            longitude=72.9781,
            location_name="Thane, Maharashtra",
            occurred_at=datetime.now(timezone.utc),
            raw_payload={"original_metric": 42.5},
        )

        # First ingestion -> Creates new record
        report1 = await report_service.ingest_normalized_event(session, event)
        assert report1 is not None
        assert report1.external_id == unique_ext_id
        assert report1.tracking_id.startswith("RPT-")
        assert report1.verification_status == "PENDING"
        assert report1.processing_status == "QUEUED"

        # Verify orchestration trigger outbox row was staged with valid
        # non-null aggregate_id == report1.id
        from app.models.outbox import RealtimeOutbox

        orch_stmt = select(RealtimeOutbox).where(
            RealtimeOutbox.entity_id == str(report1.id),
            RealtimeOutbox.event_type == "orchestration.incident_ingested",
        )
        orch_res = await session.execute(orch_stmt)
        orch_row = orch_res.scalar_one_or_none()
        assert orch_row is not None
        assert orch_row.payload["aggregate_id"] == str(report1.id)
        assert orch_row.payload["event_type"] == "incident.ingested"

        first_report_id = report1.id
        first_tracking_id = report1.tracking_id

        # Second ingestion with same source and external_id updates existing record (idempotent)
        updated_event = NormalizedIngestionEvent(
            source_code="AUTOMATED_IDEMP_TEST",
            external_id=unique_ext_id,
            category_code="FLOOD_WATERLOGGING",
            severity="HIGH",
            title="Idempotency Test Flash Flood Updated",
            latitude=19.2183,
            longitude=72.9781,
            occurred_at=datetime.now(timezone.utc),
            raw_payload={"original_metric": 55.0, "updated": True},
        )

        report2 = await report_service.ingest_normalized_event(session, updated_event)
        assert report2.id == first_report_id
        assert report2.tracking_id == first_tracking_id
        assert report2.raw_payload is not None
        assert report2.raw_payload["original_metric"] == 55.0

        # Verify only 1 record exists with this external_id for this source in the database
        stmt = select(WeatherReport).where(WeatherReport.external_id == unique_ext_id)
        res = await session.execute(stmt)
        matching_reports = res.scalars().all()
        assert len(matching_reports) == 1


# 5. Ingestion Worker Unit / Flow Tests
@pytest.mark.asyncio
async def test_ingestion_worker_process_batch():
    """Test IngestionWorker consuming, persisting, and acknowledging stream events."""
    mock_stream = MagicMock()
    mock_report_svc = MagicMock()

    test_event = NormalizedIngestionEvent(
        source_code="WORKER_TEST",
        external_id="W-001",
        title="Worker Test Event",
        latitude=13.0827,
        longitude=80.2707,
        occurred_at=datetime.now(timezone.utc),
    )

    mock_stream.read_events = AsyncMock(return_value=[("1001-0", test_event)])
    mock_stream.ack_event = AsyncMock(return_value=True)

    fake_report = MagicMock()
    fake_report.tracking_id = "RPT-WORKER-001"
    mock_report_svc.ingest_normalized_event = AsyncMock(return_value=fake_report)

    worker = IngestionWorker(
        stream_svc=mock_stream,
        report_svc=mock_report_svc,
        session_factory=async_session_factory,
    )

    results = await worker.process_batch(count=10)

    assert len(results) == 1
    msg_id, res_report = results[0]
    assert msg_id == "1001-0"
    assert res_report is fake_report
    mock_report_svc.ingest_normalized_event.assert_called_once()
    mock_stream.ack_event.assert_called_once_with("1001-0")


@pytest.mark.asyncio
async def test_recoverable_persistence_failure_and_pel_retry():
    """Test unacknowledged PEL behavior during persistence failure and subsequent retry."""
    from sqlalchemy import delete

    from app.core.redis import redis_client
    from app.services.stream_service import stream_service

    is_alive = await redis_client.ping()
    if not is_alive:
        pytest.skip("Redis server not reachable")

    test_stream = f"stream:weather:events:{uuid.uuid4().hex[:6]}"
    test_group = f"group:weather:processors:{uuid.uuid4().hex[:6]}"
    consumer_name = f"test-pel-consumer-{uuid.uuid4().hex[:6]}"
    unique_ext_id = f"PEL-FAIL-TEST-{uuid.uuid4().hex[:8]}"

    event = NormalizedIngestionEvent(
        source_code="TEST_RETRY_FEED",
        external_id=unique_ext_id,
        category_code="HEAVY_RAINFALL",
        severity="HIGH",
        title="Recoverable Failure Test Incident",
        latitude=19.0760,
        longitude=72.8777,
        occurred_at=datetime.now(timezone.utc),
    )

    # 1. Publish to Redis stream
    await stream_service.ensure_consumer_group(test_stream, test_group)
    msg_id = await stream_service.publish_event(event, stream_name=test_stream)

    # 2. Simulate persistence failure in worker
    failing_report_svc = MagicMock()
    failing_report_svc.ingest_normalized_event = AsyncMock(
        side_effect=RuntimeError("Simulated database transient connection timeout")
    )

    failing_worker = IngestionWorker(
        stream_svc=stream_service,
        report_svc=failing_report_svc,
        session_factory=async_session_factory,
        consumer_name=consumer_name,
        stream_name=test_stream,
        group_name=test_group,
    )

    # Attempt 1: Process batch -> fails persistence
    results_fail = await failing_worker.process_batch(count=10, block_ms=500, from_id=">")

    # Assert result tuple has (msg_id, None) indicating unacknowledged failure
    matching_fail = [r for r in results_fail if r[0] == msg_id]
    assert len(matching_fail) == 1
    assert matching_fail[0][1] is None

    # 3. Verify PEL contains the unacknowledged message
    pel_summary = await stream_service.get_pending_summary(test_stream, test_group)
    assert pel_summary["count"] >= 1

    # 4. Verify no database record exists yet
    async with async_session_factory() as session:
        stmt = select(WeatherReport).where(WeatherReport.external_id == unique_ext_id)
        res = await session.execute(stmt)
        assert res.scalar_one_or_none() is None

    # 5. Restore real ReportService and retry processing from PEL (from_id="0")
    recovering_worker = IngestionWorker(
        stream_svc=stream_service,
        report_svc=report_service,
        session_factory=async_session_factory,
        consumer_name=consumer_name,
        stream_name=test_stream,
        group_name=test_group,
    )

    results_retry = await recovering_worker.process_batch(count=10, block_ms=500, from_id="0")
    matching_retry = [r for r in results_retry if r[0] == msg_id]
    assert len(matching_retry) == 1
    persisted_report = matching_retry[0][1]
    assert persisted_report is not None
    assert persisted_report.external_id == unique_ext_id

    # 6. Verify exactly one database record exists
    async with async_session_factory() as session:
        stmt = select(WeatherReport).where(WeatherReport.external_id == unique_ext_id)
        res = await session.execute(stmt)
        all_reps = res.scalars().all()
        assert len(all_reps) == 1

        # Clean up database record
        del_stmt = delete(WeatherReport).where(WeatherReport.external_id == unique_ext_id)
        await session.execute(del_stmt)
        await session.commit()
