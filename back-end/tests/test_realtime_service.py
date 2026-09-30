"""Unit & integration tests for RealtimeService, Redis Streams adapter, and domain event publishing.

Validates schema contracts, deterministic serialization, privacy guardrails,
transaction-isolated publishing, and failure resiliency.
"""

import asyncio
import json
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.redis import AsyncRedisClient
from app.models.report import WeatherReport
from app.schemas.realtime import (
    RealtimeEvent,
    RealtimeEventType,
    ReportCreatedPayload,
    ReportVerificationChangedPayload,
)
from app.schemas.report import CitizenReportCreate
from app.services.realtime_service import RealtimeService
from app.services.report_service import InvalidStateTransitionError, ReportService

# ============================================================================
# 1. Realtime Schema & Envelope Tests
# ============================================================================


def test_realtime_event_envelope_validation():
    """Verify RealtimeEvent validation, defaults, and deterministic JSON serialization."""
    event_id = uuid.uuid4()
    now_utc = datetime(2026, 8, 30, 12, 0, 0, tzinfo=timezone.utc)

    event = RealtimeEvent(
        event_id=event_id,
        event_type=RealtimeEventType.REPORT_CREATED,
        occurred_at=now_utc,
        entity_id="test-entity-123",
        tracking_id="RPT-20260830-ABCD",
        payload={"severity": "HIGH", "category_code": "FLOOD_WATERLOGGING"},
    )

    data = event.model_dump(mode="json")
    assert data["event_id"] == str(event_id)
    assert data["event_type"] == "report.created"
    assert data["occurred_at"] == "2026-08-30T12:00:00Z"
    assert data["entity_id"] == "test-entity-123"
    assert data["tracking_id"] == "RPT-20260830-ABCD"
    assert data["payload"]["severity"] == "HIGH"


def test_realtime_payload_shapes_and_privacy():
    """Verify strongly-typed payload models forbid arbitrary/sensitive fields."""
    created_payload = ReportCreatedPayload(
        tracking_id="RPT-20260830-0001",
        category_code="HEAVY_RAINFALL",
        severity="SEVERE",
        verification_status="PENDING",
        location_name="Dadar, Mumbai",
        latitude=19.0178,
        longitude=72.8478,
        occurred_at=datetime.now(timezone.utc),
        has_media=True,
    )
    dumped = created_payload.model_dump(mode="json")
    assert "tracking_id" in dumped
    assert "latitude" in dumped
    assert "phone" not in dumped
    assert "operator_notes" not in dumped
    assert "password" not in dumped


def test_verification_changed_payload_structure():
    """Verify ReportVerificationChangedPayload contains audit status transition metadata."""
    payload = ReportVerificationChangedPayload(
        tracking_id="RPT-20260830-0002",
        previous_status="PENDING",
        new_status="VERIFIED",
        category_code="FLOOD_WATERLOGGING",
        severity="HIGH",
        location_name="Kurla West",
        occurred_at=datetime.now(timezone.utc),
    )
    dumped = payload.model_dump(mode="json")
    assert dumped["previous_status"] == "PENDING"
    assert dumped["new_status"] == "VERIFIED"
    assert "notes" not in dumped


# ============================================================================
# 2. RealtimeService Publishing Unit Tests
# ============================================================================


@pytest.mark.asyncio
async def test_publish_event_calls_redis_xadd():
    """Verify RealtimeService.publish_event formats Redis fields and respects max_len."""
    mock_redis = MagicMock(spec=AsyncRedisClient)
    mock_redis.xadd = AsyncMock(return_value="1725000000000-0")

    service = RealtimeService(
        client=mock_redis,
        stream_name="stream:weather:realtime",
        maxlen=10000,
    )

    event = RealtimeEvent(
        event_type=RealtimeEventType.REPORT_CREATED,
        entity_id="entity-1",
        tracking_id="RPT-001",
        payload={"test": "val"},
    )

    msg_id = await service.publish_event(event)

    assert msg_id == "1725000000000-0"
    mock_redis.xadd.assert_called_once()
    call_args, call_kwargs = mock_redis.xadd.call_args
    assert call_args[0] == "stream:weather:realtime"
    fields = call_args[1]
    assert fields["event_id"] == str(event.event_id)
    assert fields["event_type"] == "report.created"
    assert fields["entity_id"] == "entity-1"
    assert fields["tracking_id"] == "RPT-001"
    assert json.loads(fields["payload"]) == {"test": "val"}
    assert call_kwargs.get("max_len") == 10000
    assert call_kwargs.get("approximate") is True


@pytest.mark.asyncio
async def test_publish_event_handles_redis_failure_gracefully():
    """Verify RealtimeService logs error and returns None when Redis fails, without raising."""
    mock_redis = MagicMock(spec=AsyncRedisClient)
    mock_redis.xadd = AsyncMock(side_effect=ConnectionError("Redis connection refused"))

    service = RealtimeService(client=mock_redis)

    event = RealtimeEvent(
        event_type=RealtimeEventType.REPORT_CREATED,
        entity_id="entity-fail",
        payload={"k": "v"},
    )

    # Must NOT raise exception
    msg_id = await service.publish_event(event)
    assert msg_id is None


@pytest.mark.asyncio
async def test_publish_intelligence_ready_and_cluster_updated():
    """Verify helper publication methods for intelligence ready and cluster updated."""
    mock_redis = MagicMock(spec=AsyncRedisClient)
    mock_redis.xadd = AsyncMock(return_value="1725000000001-0")
    service = RealtimeService(client=mock_redis)

    mock_report = MagicMock(spec=WeatherReport)
    mock_report.id = uuid.uuid4()
    mock_report.tracking_id = "RPT-INTEL-1"

    msg_id = await service.publish_intelligence_ready(
        report=mock_report,
        credibility_score=0.885,
        readiness="INTELLIGENCE_READY",
    )
    assert msg_id == "1725000000001-0"

    cluster_msg_id = await service.publish_cluster_updated(
        cluster_id="cluster-99",
        primary_report_id=str(mock_report.id),
        member_count=4,
    )
    assert cluster_msg_id == "1725000000001-0"


# ============================================================================
# 3. ReportService Realtime Integration Tests
# ============================================================================


@pytest.mark.asyncio
async def test_citizen_report_creation_publishes_realtime_event(db_session: AsyncSession):
    """Verify successful citizen report submission emits report.created event with safe fields."""
    mock_realtime = RealtimeService(client=MagicMock())
    mock_realtime.publish_staged_outbox = AsyncMock(return_value="1725000000002-0")  # type: ignore[method-assign]

    report_svc = ReportService(realtime_svc=mock_realtime)

    payload = CitizenReportCreate(
        latitude=19.0760,
        longitude=72.8777,
        category_code="FLOOD_WATERLOGGING",
        severity="HIGH",
        title="Live Realtime Flood Test",
        description="Waterlogging on main highway",
        location_name="Bandra East",
    )

    report, media_count = await report_svc.create_citizen_report(
        session=db_session,
        payload=payload,
    )

    assert report is not None
    assert report.id is not None
    assert media_count == 0

    assert mock_realtime.publish_staged_outbox.call_count == 2
    outbox_calls = [call[0][0] for call in mock_realtime.publish_staged_outbox.call_args_list]
    event_types = {outbox.event_type for outbox in outbox_calls}
    assert "report.created" in event_types
    assert "orchestration.incident_ingested" in event_types


@pytest.mark.asyncio
async def test_verification_transition_publishes_realtime_event(db_session: AsyncSession):
    """Verify valid verification transition emits report.verification_changed."""
    mock_realtime = RealtimeService(client=MagicMock())
    mock_realtime.publish_staged_outbox = AsyncMock(return_value="1725000000004-0")  # type: ignore[method-assign]

    report_svc = ReportService(realtime_svc=mock_realtime)

    # 1. Create report in PENDING state (calls publish_staged_outbox 2x:
    # report.created + orchestration.incident_ingested)
    payload = CitizenReportCreate(
        latitude=19.0178,
        longitude=72.8478,
        category_code="CYCLONE_HIGH_WIND",
        severity="SEVERE",
        title="Verification Realtime Test",
        description="High winds observed",
        location_name="Bandra",
    )
    report, _ = await report_svc.create_citizen_report(session=db_session, payload=payload)

    # 2. Transition PENDING -> VERIFIED (calls publish_staged_outbox 1x:
    # report.verification_changed)
    updated_report = await report_svc.update_verification_status(
        session=db_session,
        report_id_or_tracking=str(report.id),
        new_status="VERIFIED",
        notes="Confirmed by local control room",
    )

    assert updated_report.verification_status == "VERIFIED"
    assert mock_realtime.publish_staged_outbox.call_count == 3
    last_outbox_arg = mock_realtime.publish_staged_outbox.call_args[0][0]
    assert last_outbox_arg.entity_id == str(report.id)
    assert last_outbox_arg.event_type == "report.verification_changed"


@pytest.mark.asyncio
async def test_invalid_verification_transition_publishes_nothing(db_session: AsyncSession):
    """Verify invalid verification state transition raises error and publishes NOTHING."""
    mock_realtime = RealtimeService(client=MagicMock())
    mock_realtime.publish_staged_outbox = AsyncMock()  # type: ignore[method-assign]

    report_svc = ReportService(realtime_svc=mock_realtime)

    # 1. Create and transition to terminal VERIFIED state
    payload = CitizenReportCreate(
        latitude=19.0178,
        longitude=72.8478,
        category_code="HEATWAVE",
        severity="MODERATE",
        title="Terminal State Test",
        description="High heat conditions",
        location_name="Dadar",
    )
    report, _ = await report_svc.create_citizen_report(session=db_session, payload=payload)
    await report_svc.update_verification_status(
        session=db_session,
        report_id_or_tracking=str(report.id),
        new_status="VERIFIED",
    )

    mock_realtime.publish_staged_outbox.reset_mock()

    # 2. Attempt illegal transition from VERIFIED -> PENDING
    with pytest.raises(InvalidStateTransitionError):
        await report_svc.update_verification_status(
            session=db_session,
            report_id_or_tracking=str(report.id),
            new_status="PENDING",
        )

    mock_realtime.publish_staged_outbox.assert_not_called()


# ============================================================================
# 4. AsyncRedisClient Stream Operations Unit Tests
# ============================================================================


@pytest.mark.asyncio
async def test_redis_client_xread_and_xrange_parsing():
    """Verify AsyncRedisClient parses raw RESP responses for xread and xrange."""
    client = AsyncRedisClient()

    # Mock _execute_raw to return typical Redis XREAD raw response
    mock_xread_resp = [
        [
            "stream:weather:realtime",
            [
                [
                    "1725000000000-0",
                    ["event_id", "evt-123", "event_type", "report.created", "entity_id", "ent-1"],
                ]
            ],
        ]
    ]

    client._execute_raw = AsyncMock(return_value=mock_xread_resp)

    results = await client.xread({"stream:weather:realtime": "0-0"}, count=5)
    assert len(results) == 1
    stream_name, entries = results[0]
    assert stream_name == "stream:weather:realtime"
    assert len(entries) == 1
    msg_id, fields = entries[0]
    assert msg_id == "1725000000000-0"
    assert fields["event_id"] == "evt-123"
    assert fields["event_type"] == "report.created"

    # Mock _execute_raw for XRANGE
    mock_xrange_resp = [
        [
            "1725000000001-0",
            ["event_id", "evt-456", "event_type", "report.verification_changed"],
        ]
    ]
    client._execute_raw = AsyncMock(return_value=mock_xrange_resp)

    range_results = await client.xrange("stream:weather:realtime", min_id="-", max_id="+", count=10)
    assert len(range_results) == 1
    msg_id2, fields2 = range_results[0]
    assert msg_id2 == "1725000000001-0"
    assert fields2["event_type"] == "report.verification_changed"


@pytest.mark.asyncio
async def test_redis_client_db_select_connect_within_2s():
    """Verify AsyncRedisClient connects to non-zero db (e.g. 5) within 2s without deadlock."""
    client = AsyncRedisClient(redis_url="redis://localhost:6379/5")
    try:
        await asyncio.wait_for(client.connect(), timeout=2.0)
        res = await asyncio.wait_for(client.ping(), timeout=2.0)
        assert res is True
    except (ConnectionError, OSError):
        pytest.skip("Local Redis server not accessible")
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_redis_client_xautoclaim_parsing():
    """Verify AsyncRedisClient parses raw RESP response for xautoclaim."""
    client = AsyncRedisClient()
    mock_autoclaim_resp = [
        "1725000000002-0",
        [
            [
                "1725000000001-0",
                ["event_id", "evt-789", "event_type", "report.created"],
            ]
        ],
    ]
    client._execute_raw = AsyncMock(return_value=mock_autoclaim_resp)
    next_id, entries = await client.xautoclaim(
        stream="stream:weather:test",
        group="group:test",
        consumer="consumer:1",
        min_idle_time_ms=60000,
    )
    assert next_id == "1725000000002-0"
    assert len(entries) == 1
    assert entries[0][0] == "1725000000001-0"
    assert entries[0][1]["event_id"] == "evt-789"
