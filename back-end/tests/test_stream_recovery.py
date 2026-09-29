import asyncio
import uuid
from datetime import datetime, timezone

import pytest

from app.core.config import settings
from app.core.redis import AsyncRedisClient
from app.ingestion.schemas import NormalizedIngestionEvent
from app.services.stream_service import StreamService


@pytest.mark.asyncio
async def test_stream_autoclaim_unacked_message_recovery():
    """Verify consumer B reclaims and processes an unacked message from consumer A after idle threshold."""
    client = AsyncRedisClient()
    try:
        await client.connect()
    except Exception:
        pytest.skip("Local Redis server not accessible")

    service = StreamService(client=client)
    unique_id = uuid.uuid4().hex[:8]
    stream_name = f"stream:test:recovery:{unique_id}"
    group_name = f"group:test:recovery:{unique_id}"

    try:
        # Publish event
        event = NormalizedIngestionEvent(
            event_id=uuid.uuid4(),
            source_code="TEST_SRC",
            category_code="FLOOD",
            severity="MEDIUM",
            title="Recovery Test Event",
            occurred_at=datetime.now(timezone.utc),
            latitude=19.076,
            longitude=72.877,
        )
        await service.publish_event(event, stream_name=stream_name)

        # Consumer A reads event and does NOT ack
        events_a = await service.read_events(
            group_name=group_name,
            consumer_name="consumer-A",
            stream_name=stream_name,
            count=1,
            block_ms=1000,
            claim_idle_ms=100000,
        )
        assert len(events_a) == 1
        msg_id, rec_event = events_a[0]
        assert str(rec_event.event_id) == str(event.event_id)

        # Consumer B immediately tries to read - idle threshold 100ms not met yet
        events_b_early = await service.read_events(
            group_name=group_name,
            consumer_name="consumer-B",
            stream_name=stream_name,
            count=1,
            block_ms=100,
            claim_idle_ms=200,
        )
        assert len(events_b_early) == 0

        # Wait past idle threshold (250ms)
        await asyncio.sleep(0.3)

        # Consumer B reclaims idle message via XAUTOCLAIM
        events_b_reclaimed = await service.read_events(
            group_name=group_name,
            consumer_name="consumer-B",
            stream_name=stream_name,
            count=1,
            block_ms=100,
            claim_idle_ms=200,
        )
        assert len(events_b_reclaimed) == 1
        reclaimed_id, reclaimed_ev = events_b_reclaimed[0]
        assert reclaimed_id == msg_id
        assert str(reclaimed_ev.event_id) == str(event.event_id)

        # Consumer B acknowledges the message
        ack_res = await service.ack_event(reclaimed_id, stream_name=stream_name, group_name=group_name)
        assert ack_res is True

        # Confirm PEL is empty
        pending = await service.get_pending_summary(stream_name, group_name)
        assert pending["count"] == 0

    finally:
        await client.delete(stream_name)
        await client.close()


@pytest.mark.asyncio
async def test_stream_max_delivery_attempts_dlq(monkeypatch):
    """Verify messages exceeding STREAM_MAX_DELIVERY_ATTEMPTS are moved to dead-letter stream."""
    client = AsyncRedisClient()
    try:
        await client.connect()
    except Exception:
        pytest.skip("Local Redis server not accessible")

    monkeypatch.setattr(settings, "STREAM_MAX_DELIVERY_ATTEMPTS", 2)
    service = StreamService(client=client)
    unique_id = uuid.uuid4().hex[:8]
    stream_name = f"stream:test:dlq:{unique_id}"
    group_name = f"group:test:dlq:{unique_id}"

    try:
        event = NormalizedIngestionEvent(
            event_id=uuid.uuid4(),
            source_code="TEST_SRC",
            category_code="FLOOD",
            severity="HIGH",
            title="DLQ Poison Test",
            occurred_at=datetime.now(timezone.utc),
            latitude=19.076,
            longitude=72.877,
        )
        await service.publish_event(event, stream_name=stream_name)

        # First read by worker-1 (delivery 1)
        res1 = await service.read_events(
            group_name=group_name,
            consumer_name="worker-1",
            stream_name=stream_name,
            count=1,
            block_ms=500,
            claim_idle_ms=100000,
        )
        assert len(res1) == 1

        # Wait 150ms
        await asyncio.sleep(0.2)

        # Reclaim 1 by worker-2 (delivery 2)
        res2 = await service.read_events(
            group_name=group_name,
            consumer_name="worker-2",
            stream_name=stream_name,
            count=1,
            block_ms=500,
            claim_idle_ms=100,
        )
        assert len(res2) == 1

        # Wait 150ms
        await asyncio.sleep(0.2)

        # Reclaim 2 by worker-3 (delivery 3 -> exceeds max_attempts=2)
        # Should route to DLQ and not return to caller
        res3 = await service.read_events(
            group_name=group_name,
            consumer_name="worker-3",
            stream_name=stream_name,
            count=1,
            block_ms=500,
            claim_idle_ms=100,
        )
        assert len(res3) == 0

        # Check that original group PEL is cleared (ACKed on DLQ transfer)
        pending = await service.get_pending_summary(stream_name, group_name)
        assert pending["count"] == 0

    finally:
        await client.delete(stream_name)
        await client.close()
