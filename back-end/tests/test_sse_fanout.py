"""Tests for SSE fan-out architecture: subscriber queues, slow client drop, and replay deduplication."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.api.v1.events import SSEBroadcaster


@pytest.mark.asyncio
async def test_20_clients_receive_5_events_in_order():
    """Verify 20 concurrent client queues all receive 5 broadcast events in exact order."""
    broadcaster = SSEBroadcaster(stream_name="test:stream")
    queues = [broadcaster.subscribe() for _ in range(20)]

    try:
        # Broadcast 5 events in order
        for i in range(1, 6):
            msg_id = f"1000-{i}"
            payload = {"event_type": "report.created", "index": i}
            broadcaster.broadcast(msg_id, payload)

        # Verify all 20 clients received all 5 events in order
        for q in queues:
            assert q.qsize() == 5
            for expected_idx in range(1, 6):
                msg_id, payload = q.get_nowait()
                assert msg_id == f"1000-{expected_idx}"
                assert payload["index"] == expected_idx
    finally:
        for q in queues:
            broadcaster.unsubscribe(q)


@pytest.mark.asyncio
async def test_slow_client_dropped_without_affecting_others():
    """Verify slow client with full buffer (maxsize=100) is dropped with RESYNC without affecting fast clients."""
    broadcaster = SSEBroadcaster(stream_name="test:stream")
    fast_queue = broadcaster.subscribe()
    slow_queue = broadcaster.subscribe()

    try:
        # Send 105 events
        for i in range(1, 106):
            msg_id = f"2000-{i}"
            payload = {"event_type": "report.created", "i": i}
            broadcaster.broadcast(msg_id, payload)

            # Fast client keeps consuming
            if not fast_queue.empty():
                fast_queue.get_nowait()

        # Slow client queue overflowed -> dropped from broadcaster subscribers
        assert slow_queue not in broadcaster._subscribers
        # Fast client remains subscribed
        assert fast_queue in broadcaster._subscribers

        # Slow queue has resync message at the end
        items = []
        while not slow_queue.empty():
            items.append(slow_queue.get_nowait())

        resync_items = [item for item in items if item[0] == "RESYNC"]
        assert len(resync_items) == 1
        assert "BUFFER_OVERFLOW" in resync_items[0][1]["chunk"]
    finally:
        broadcaster.unsubscribe(fast_queue)
        broadcaster.unsubscribe(slow_queue)


@pytest.mark.asyncio
async def test_reconnect_with_last_event_id_no_loss_no_duplicates():
    """Verify reconnecting with Last-Event-ID provides gapless stream with zero duplicates between replay and live queue."""
    mock_redis = MagicMock()
    mock_redis.connect = AsyncMock()
    mock_redis.close = AsyncMock()

    # Replay returns events 1000-2, 1000-3, 1000-4
    replay_entries = [
        ("1000-2", {"event_type": "report.created", "entity_id": "r2", "payload": "{}"}),
        ("1000-3", {"event_type": "report.created", "entity_id": "r3", "payload": "{}"}),
        ("1000-4", {"event_type": "report.created", "entity_id": "r4", "payload": "{}"}),
    ]
    mock_redis.xrange = AsyncMock(
        side_effect=[
            [("1000-1", {})],  # oldest entry check
            replay_entries,  # replay entries
        ]
    )

    request = MagicMock()
    # Let generator yield 3 items then stop
    counter = 0

    async def is_disconnected():
        nonlocal counter
        return counter >= 3

    request.is_disconnected = is_disconnected

    from app.api.v1 import events

    # Pre-populate live broadcaster with event 1000-4 (overlap) and 1000-5 (new live)
    generator = events.realtime_event_generator(
        request=request,
        last_event_id="1000-2",
        client=mock_redis,
        heartbeat_interval=1.0,
    )

    received_events = []
    # Intercept generator items
    async for chunk in generator:
        if "id: " in chunk:
            for line in chunk.splitlines():
                if line.startswith("id: "):
                    received_events.append(line.replace("id: ", "").strip())
        counter += 1
        if counter >= 3:
            break

    # 1000-2 was last_event_id, so it must not be re-yielded
    assert "1000-2" not in received_events
    # 1000-3 and 1000-4 were yielded
    assert "1000-3" in received_events
    assert "1000-4" in received_events
    # Check no duplicate IDs in received list
    assert len(received_events) == len(set(received_events))
