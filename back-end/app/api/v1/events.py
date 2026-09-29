"""Server-Sent Events (SSE) realtime transport endpoint.

Exposes an observational text/event-stream endpoint streaming canonical RealtimeEvents
from the `stream:weather:realtime` Redis Stream to connected clients with replay support.
"""

from __future__ import annotations

import asyncio
import json
import logging
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


async def realtime_event_generator(
    request: Request,
    last_event_id: Optional[str] = None,
    client: Optional[AsyncRedisClient] = None,
    stream_name: Optional[str] = None,
    heartbeat_interval: float = HEARTBEAT_INTERVAL_SECONDS,
    poll_interval: float = POLL_INTERVAL_SECONDS,
) -> AsyncGenerator[str, None]:
    """Generate real-time SSE chunks with replay and live streaming."""
    target_stream = stream_name or settings.REALTIME_STREAM_NAME
    redis = client or AsyncRedisClient()
    current_last_id: Optional[str] = None

    try:
        await redis.connect()

        # -------------------------------------------------------------
        # 1. Replay Phase (if Last-Event-ID provided)
        # -------------------------------------------------------------
        if last_event_id and last_event_id.strip():
            clean_last_id = last_event_id.strip()

            # Check oldest available entry in the stream
            oldest_entries = await redis.xrange(target_stream, min_id="-", max_id="+", count=1)

            if oldest_entries:
                oldest_id, _ = oldest_entries[0]
                if _is_stream_id_older(clean_last_id, oldest_id):
                    # Client requested stream position older than retained history
                    resync_payload = SystemResyncRequiredPayload(
                        reason="RESYNC_REQUIRED",
                        message=(
                            "Stream history pruned. Client must refresh authoritative "
                            "state via REST API."
                        ),
                        requested_last_event_id=clean_last_id,
                        oldest_available_id=oldest_id,
                    )
                    resync_event = RealtimeEvent(
                        event_id=uuid.uuid4(),
                        event_type=RealtimeEventType.SYSTEM_RESYNC_REQUIRED,
                        occurred_at=datetime.now(timezone.utc),
                        entity_id="system",
                        tracking_id=None,
                        payload=resync_payload.model_dump(mode="json"),
                    )
                    yield _format_sse_chunk(
                        event_type=RealtimeEventType.SYSTEM_RESYNC_REQUIRED.value,
                        data=resync_event.model_dump(mode="json"),
                        event_id=oldest_id,
                    )
                    clean_last_id = oldest_id

            # Replay entries starting from clean_last_id up to current head
            replay_entries = await redis.xrange(
                target_stream,
                min_id=clean_last_id,
                max_id="+",
                count=MAX_REPLAY_BATCH_SIZE,
            )
            for msg_id, fields in replay_entries:
                if msg_id == clean_last_id:
                    # Exclude the exact last event already received by client
                    continue
                envelope = _parse_stream_event_to_envelope(fields)
                if envelope is not None:
                    yield _format_sse_chunk(
                        event_type=envelope["event_type"],
                        data=envelope,
                        event_id=msg_id,
                    )
                current_last_id = msg_id

        # -------------------------------------------------------------
        # Determine starting stream position for live streaming
        # -------------------------------------------------------------
        if current_last_id is None:
            latest_entries = await redis.xrevrange(
                target_stream,
                max_id="+",
                min_id="-",
                count=1,
            )
            if latest_entries:
                current_last_id = latest_entries[0][0]
            else:
                current_last_id = "0-0"

        # -------------------------------------------------------------
        # 2. Live Streaming Phase
        # -------------------------------------------------------------
        loop = asyncio.get_event_loop()
        last_activity = loop.time()

        while True:
            # Check client disconnect
            if await request.is_disconnected():
                logger.info("SSE client disconnected cleanly.")
                break

            now = loop.time()

            try:
                read_results = await redis.xread(
                    {target_stream: current_last_id},
                    count=50,
                    block_ms=1000,
                )
            except Exception as e:
                logger.error("Redis transport failure during SSE streaming: %s", e)
                # Terminate generator cleanly to trigger client EventSource reconnection
                break

            had_events = False
            if read_results:
                for _, entries in read_results:
                    for msg_id, fields in entries:
                        envelope = _parse_stream_event_to_envelope(fields)
                        if envelope is not None:
                            yield _format_sse_chunk(
                                event_type=envelope["event_type"],
                                data=envelope,
                                event_id=msg_id,
                            )
                        current_last_id = msg_id
                        had_events = True

            if had_events:
                last_activity = loop.time()
            else:
                if (now - last_activity) >= heartbeat_interval:
                    yield _format_sse_heartbeat()
                    last_activity = now

            await asyncio.sleep(poll_interval)

    except asyncio.CancelledError:
        logger.info("SSE request stream cancelled (client disconnected).")
    except Exception as e:
        logger.warning("Unhandled error in SSE generator: %s", e)
    finally:
        await redis.close()


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
            logger.warning("SSE connection attempted with expired or invalid ticket nonce: %s", ticket[:8])

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
