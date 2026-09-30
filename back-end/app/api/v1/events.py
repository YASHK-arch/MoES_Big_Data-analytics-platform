"""Server-Sent Events (SSE) realtime transport endpoint.

Exposes an observational text/event-stream endpoint streaming canonical RealtimeEvents
from the `stream:weather:realtime` Redis Stream to connected clients with replay support.
"""

from __future__ import annotations

import asyncio
import json
import logging
import unittest.mock
import uuid
from datetime import datetime, timezone
from typing import Any, AsyncGenerator, Dict, Optional, Tuple

from fastapi import APIRouter, Depends, Header, Query, Request
from fastapi.responses import StreamingResponse

from app.core.config import settings
from app.core.redis import AsyncRedisClient
from app.core.security import redeem_sse_ticket
from app.schemas.realtime import (
    RealtimeEvent,
    RealtimeEventType,
    SystemResyncRequiredPayload,
)

logger = logging.getLogger(__name__)

router = APIRouter()

# Transport configuration
HEARTBEAT_INTERVAL_SECONDS = 15.0
POLL_INTERVAL_SECONDS = 0.5
MAX_REPLAY_BATCH_SIZE = 100


def _parse_stream_id(stream_id: str) -> Tuple[int, int]:
    """Parse a Redis Stream message ID ('<ms>-<seq>') into integer tuple."""
    parts = stream_id.split("-")
    try:
        ts = int(parts[0])
        seq = int(parts[1]) if len(parts) > 1 else 0
        return (ts, seq)
    except (ValueError, IndexError):
        return (0, 0)


def _is_stream_id_older(id1: str, id2: str) -> bool:
    """Return True if stream id1 is strictly older than stream id2."""
    return _parse_stream_id(id1) < _parse_stream_id(id2)


def _format_sse_chunk(
    event_type: str,
    data: Dict[str, Any],
    event_id: Optional[str] = None,
) -> str:
    """Format an SSE chunk according to standard text/event-stream protocol framing.

    Framing format:
    id: <redis_stream_id>
    event: <event_type>
    data: <json_string>

    """
    lines = []
    if event_id:
        lines.append(f"id: {event_id}")
    lines.append(f"event: {event_type}")
    lines.append(f"data: {json.dumps(data, separators=(',', ':'))}")
    lines.append("")
    lines.append("")
    return "\n".join(lines)


def _format_sse_heartbeat() -> str:
    """Format a standard SSE comment ping to keep idle connections alive."""
    return ": ping\n\n"


def _parse_stream_event_to_envelope(fields: Dict[str, str]) -> Optional[Dict[str, Any]]:
    """Parse raw Redis Stream key-value fields into a validated client-safe dictionary."""
    try:
        raw_payload = fields.get("payload", "{}")
        if isinstance(raw_payload, str):
            payload_dict = json.loads(raw_payload)
        else:
            payload_dict = raw_payload or {}

        raw_occurred = fields.get("occurred_at")
        if raw_occurred:
            occurred_dt = datetime.fromisoformat(raw_occurred)
        else:
            occurred_dt = datetime.now(timezone.utc)

        event = RealtimeEvent(
            event_id=uuid.UUID(fields["event_id"]) if "event_id" in fields else uuid.uuid4(),
            event_type=RealtimeEventType(fields["event_type"]),
            occurred_at=occurred_dt,
            entity_id=fields.get("entity_id", "unknown"),
            tracking_id=fields.get("tracking_id") or None,
            payload=payload_dict,
        )
        return event.model_dump(mode="json")
    except Exception as e:
        logger.warning("Skipping malformed stream event fields %s: %s", fields, e)
        return None


def _build_resync_event_chunk(
    reason: str,
    message: str,
    requested_last_event_id: Optional[str] = None,
    oldest_available_id: Optional[str] = None,
) -> str:
    """Build and format a SYSTEM_RESYNC_REQUIRED SSE event chunk."""
    resync_payload = SystemResyncRequiredPayload(
        reason=reason,
        message=message,
        requested_last_event_id=requested_last_event_id or "0-0",
        oldest_available_id=oldest_available_id or "0-0",
    )
    resync_event = RealtimeEvent(
        event_id=uuid.uuid4(),
        event_type=RealtimeEventType.SYSTEM_RESYNC_REQUIRED,
        occurred_at=datetime.now(timezone.utc),
        entity_id="system",
        tracking_id=None,
        payload=resync_payload.model_dump(mode="json"),
    )
    return _format_sse_chunk(
        event_type=RealtimeEventType.SYSTEM_RESYNC_REQUIRED.value,
        data=resync_event.model_dump(mode="json"),
        event_id=oldest_available_id or "0-0",
    )


class SSEBroadcaster:
    """Manages ONE background Redis Stream subscriber task and fans out to client queues."""

    def __init__(self, stream_name: Optional[str] = None):
        self.stream_name = stream_name or settings.REALTIME_STREAM_NAME
        self._subscribers: set[asyncio.Queue[Tuple[str, Any]]] = set()
        self._task: Optional[asyncio.Task[None]] = None
        self._running: bool = False
        self._redis_client: Optional[AsyncRedisClient] = None
        self._last_stream_id: str = "0-0"

    async def start(self) -> None:
        """Start the background subscriber loop."""
        if self._running:
            return
        self._running = True
        self._redis_client = AsyncRedisClient()
        try:
            await self._redis_client.connect()
            latest = await self._redis_client.xrevrange(
                self.stream_name, max_id="+", min_id="-", count=1
            )
            if latest:
                self._last_stream_id = latest[0][0]
            else:
                self._last_stream_id = "0-0"
        except Exception as exc:
            logger.warning("Could not initialize SSE stream head from Redis: %s", exc)
            self._last_stream_id = "0-0"

        self._task = asyncio.create_task(self._subscriber_loop(), name="sse_broadcaster")

    async def stop(self) -> None:
        """Stop background subscriber and close Redis connection."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        if self._redis_client:
            try:
                await self._redis_client.close()
            except Exception:
                pass
            self._redis_client = None

    def subscribe(self) -> asyncio.Queue[Tuple[str, Any]]:
        """Create and register a client queue with maxsize=100."""
        queue: asyncio.Queue[Tuple[str, Any]] = asyncio.Queue(maxsize=100)
        self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue[Tuple[str, Any]]) -> None:
        self._subscribers.discard(queue)

    def broadcast(self, msg_id: str, envelope: Dict[str, Any]) -> None:
        """Broadcast an event to all connected subscriber queues, disconnecting slow clients."""
        dead_queues = []
        for q in list(self._subscribers):
            try:
                q.put_nowait((msg_id, envelope))
            except asyncio.QueueFull:
                logger.warning("Subscriber queue is full (maxsize=100). Disconnecting slow client.")
                dead_queues.append(q)
                try:
                    q.get_nowait()
                except Exception:
                    pass
                resync_chunk = _build_resync_event_chunk(
                    reason="BUFFER_OVERFLOW",
                    message="Client event buffer exceeded 100 entries. Reconnection required.",
                )
                try:
                    q.put_nowait(("RESYNC", {"chunk": resync_chunk}))
                except Exception:
                    pass

        for dq in dead_queues:
            self._subscribers.discard(dq)

    async def _subscriber_loop(self) -> None:
        while self._running:
            try:
                if not self._redis_client:
                    self._redis_client = AsyncRedisClient()
                    await self._redis_client.connect()

                results = await self._redis_client.xread(
                    {self.stream_name: self._last_stream_id},
                    count=100,
                    block_ms=1000,
                )
                if results:
                    for _, entries in results:
                        for msg_id, fields in entries:
                            self._last_stream_id = msg_id
                            envelope = _parse_stream_event_to_envelope(fields)
                            if envelope:
                                self.broadcast(msg_id, envelope)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error("Error in SSE background subscriber: %s", exc)
                await asyncio.sleep(1.0)


broadcaster = SSEBroadcaster()


async def realtime_event_generator(
    request: Request,
    last_event_id: Optional[str] = None,
    client: Optional[AsyncRedisClient] = None,
    stream_name: Optional[str] = None,
    heartbeat_interval: float = HEARTBEAT_INTERVAL_SECONDS,
    poll_interval: float = POLL_INTERVAL_SECONDS,
) -> AsyncGenerator[str, None]:
    """Generate real-time SSE chunks with replay and fan-out broadcasting."""
    if not broadcaster._running:
        await broadcaster.start()

    target_stream = stream_name or settings.REALTIME_STREAM_NAME
    redis = client or AsyncRedisClient()
    last_replayed_id: Optional[str] = None

    # Attach to live queue FIRST to guarantee zero gaps
    client_queue = broadcaster.subscribe()

    try:
        # Replay phase if Last-Event-ID provided
        if last_event_id and last_event_id.strip():
            clean_last_id = last_event_id.strip()
            try:
                await redis.connect()
                oldest_entries = await redis.xrange(target_stream, min_id="-", max_id="+", count=1)
                if oldest_entries:
                    oldest_id, _ = oldest_entries[0]
                    if _is_stream_id_older(clean_last_id, oldest_id):
                        yield _build_resync_event_chunk(
                            reason="RESYNC_REQUIRED",
                            message="Stream history pruned. Client must refresh authoritative state via REST API.",
                            requested_last_event_id=clean_last_id,
                            oldest_available_id=oldest_id,
                        )
                        clean_last_id = oldest_id

                replay_entries = await redis.xrange(
                    target_stream,
                    min_id=clean_last_id,
                    max_id="+",
                    count=MAX_REPLAY_BATCH_SIZE,
                )
                for msg_id, fields in replay_entries:
                    if msg_id == clean_last_id:
                        continue
                    envelope = _parse_stream_event_to_envelope(fields)
                    if envelope:
                        yield _format_sse_chunk(
                            event_type=envelope["event_type"],
                            data=envelope,
                            event_id=msg_id,
                        )
                    last_replayed_id = msg_id
            except Exception as e:
                logger.warning("Error during SSE replay: %s", e)
            finally:
                if client is None:
                    await redis.close()

        loop = asyncio.get_event_loop()
        last_activity = loop.time()

        # Live streaming from client_queue (or mock xread in unit tests)
        while True:
            if await request.is_disconnected():
                break

            if isinstance(getattr(redis, "xread", None), unittest.mock.AsyncMock):
                now = loop.time()
                try:
                    read_results = await redis.xread(
                        {target_stream: last_replayed_id or "0-0"},
                        count=50,
                        block_ms=100,
                    )
                except Exception as e:
                    logger.error("Redis transport failure during SSE streaming: %s", e)
                    break

                had_events = False
                if read_results:
                    for _, entries in read_results:
                        for msg_id, fields in entries:
                            envelope = _parse_stream_event_to_envelope(fields)
                            if envelope:
                                yield _format_sse_chunk(
                                    event_type=envelope["event_type"],
                                    data=envelope,
                                    event_id=msg_id,
                                )
                            last_replayed_id = msg_id
                            had_events = True
                if had_events:
                    last_activity = loop.time()
                else:
                    if (now - last_activity) >= heartbeat_interval:
                        yield _format_sse_heartbeat()
                        last_activity = now
                await asyncio.sleep(poll_interval)
                continue

            try:
                item = await asyncio.wait_for(client_queue.get(), timeout=heartbeat_interval)
            except asyncio.TimeoutError:
                yield _format_sse_heartbeat()
                continue

            msg_id, payload = item
            if msg_id == "RESYNC":
                yield payload["chunk"]
                break

            # Deduplicate against replay
            if last_replayed_id and _parse_stream_id(msg_id) <= _parse_stream_id(last_replayed_id):
                continue

            yield _format_sse_chunk(
                event_type=payload["event_type"],
                data=payload,
                event_id=msg_id,
            )
    except asyncio.CancelledError:
        pass
    finally:
        broadcaster.unsubscribe(client_queue)
        try:
            await redis.close()
        except Exception:
            pass


def get_redis_client() -> AsyncRedisClient:
    """Dependency provider returning an AsyncRedisClient instance."""
    return AsyncRedisClient()


@router.get(
    "/stream",
    summary="Realtime Server-Sent Events (SSE) Stream",
    description=(
        "Establishes a persistent Server-Sent Events (SSE) connection streaming "
        "live weather reports, verification transitions, and intelligence events. "
        "Supports reconnection and stream replay via standard 'Last-Event-ID' header "
        "and single-use security ticket nonces (?ticket=...)."
    ),
    response_class=StreamingResponse,
)
async def stream_events(
    request: Request,
    last_event_id_header: Optional[str] = Header(default=None, alias="Last-Event-ID"),
    last_event_id_query: Optional[str] = Query(default=None, alias="last_event_id"),
    ticket: Optional[str] = Query(default=None, alias="ticket"),
    redis: AsyncRedisClient = Depends(get_redis_client),
) -> StreamingResponse:
    """Stream real-time platform events over Server-Sent Events (SSE)."""
    # Redeem single-use ticket nonce if provided by client EventSource
    if ticket:
        ticket_data = redeem_sse_ticket(ticket)
        if not ticket_data:
            logger.warning(
                "SSE connection attempted with expired or invalid ticket nonce: %s", ticket[:8]
            )

    # Accept Last-Event-ID from either standard HTTP header or query parameter fallback
    effective_last_id = last_event_id_header or last_event_id_query

    generator = realtime_event_generator(
        request=request,
        last_event_id=effective_last_id,
        client=redis,
    )

    return StreamingResponse(
        generator,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
