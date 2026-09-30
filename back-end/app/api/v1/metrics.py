"""O3 Prometheus metrics endpoint.

GET /metrics — Prometheus text format metrics:
  - HTTP request count and latency histogram by route and status
  - Per-stream lag and pending (XINFO GROUPS)
  - Outbox pending count and oldest age in seconds
  - DB pool checked-out connections
  - Worker heartbeat age (seconds since last heartbeat)

Gauges are recomputed at scrape time with a 5s server-side cache.
No Prometheus server or Grafana container required.
"""

import asyncio
import logging
import time
from typing import Any

from fastapi import APIRouter, Request, Response
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)
from sqlalchemy import text

from app.core.config import settings
from app.core.redis import redis_client
from app.db.session import async_session_factory, engine

logger = logging.getLogger(__name__)
router = APIRouter()

# ── Metric definitions ────────────────────────────────────────────────────────

http_requests_total = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["method", "route", "status_code"],
)

http_request_duration_seconds = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency",
    ["method", "route"],
    buckets=[0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
)

# Stream metrics
stream_lag = Gauge(
    "stream_lag_messages",
    "Number of unacknowledged (pending) messages per consumer group",
    ["stream", "group"],
)
stream_pending = Gauge(
    "stream_pending_messages",
    "Total pending messages in stream group",
    ["stream", "group"],
)

# Outbox metrics
outbox_pending_count = Gauge(
    "outbox_pending_count",
    "Number of PENDING outbox events not yet published",
)
outbox_oldest_age_seconds = Gauge(
    "outbox_oldest_age_seconds",
    "Age in seconds of the oldest PENDING outbox event",
)

# DB pool
db_pool_checked_out = Gauge(
    "db_pool_checked_out",
    "Number of DB connections currently checked out from the pool",
)

# Worker heartbeats
worker_heartbeat_age_seconds = Gauge(
    "worker_heartbeat_age_seconds",
    "Seconds since worker last wrote its heartbeat",
    ["worker"],
)

# ── Scrape-time refresh cache ─────────────────────────────────────────────────

_cache_lock = asyncio.Lock()
_last_refresh: float = 0.0
_CACHE_TTL = 5.0  # seconds

EXPECTED_WORKERS = ["outbox", "dispatcher", "ingestion", "observation", "evidence", "scheduler"]


async def _refresh_gauges() -> None:
    """Recompute all async gauges. Called at most once per _CACHE_TTL seconds."""
    global _last_refresh
    now = time.monotonic()

    async with _cache_lock:
        if now - _last_refresh < _CACHE_TTL:
            return  # Another coroutine already refreshed recently
        _last_refresh = now

    # 1. Stream metrics
    for stream_name in [settings.REALTIME_STREAM_NAME, settings.STREAM_DEAD_LETTER_NAME]:
        try:
            groups = await redis_client.xinfo_groups(stream_name)
            for group in groups:
                gname = str(group.get("name", "unknown"))
                lag = int(group.get("lag", 0) or 0)
                pending = int(group.get("pending", 0) or 0)
                stream_lag.labels(stream=stream_name, group=gname).set(lag)
                stream_pending.labels(stream=stream_name, group=gname).set(pending)
        except Exception as exc:
            logger.debug("Stream metric refresh failed for %s: %s", stream_name, exc)

    # 2. Outbox metrics (query DB)
    try:
        async with async_session_factory() as session:
            result = await session.execute(
                text(
                    "SELECT count(*), extract(epoch from (now() - min(created_at))) "
                    "FROM outbox_events WHERE status = 'PENDING'"
                )
            )
            row = result.one_or_none()
            if row:
                outbox_pending_count.set(int(row[0] or 0))
                outbox_oldest_age_seconds.set(float(row[1] or 0))
    except Exception as exc:
        logger.debug("Outbox metric refresh failed: %s", exc)

    # 3. DB pool checked-out
    try:
        pool = engine.sync_engine.pool  # type: ignore[attr-defined]
        checked_out = getattr(pool, "checkedout", lambda: 0)()
        db_pool_checked_out.set(checked_out)
    except Exception:
        pass

    # 4. Worker heartbeat ages
    ts_now = time.time()
    for name in EXPECTED_WORKERS:
        key = f"worker:heartbeat:{name}"
        try:
            val = await redis_client.get(key)
            if val:
                last_ts = float(val)
                worker_heartbeat_age_seconds.labels(worker=name).set(ts_now - last_ts)
            else:
                # Key missing or expired → set to a large age value
                worker_heartbeat_age_seconds.labels(worker=name).set(9999)
        except Exception:
            worker_heartbeat_age_seconds.labels(worker=name).set(9999)


# ── Middleware hook for request metrics ───────────────────────────────────────


async def record_request_metric(request: Request, call_next: Any) -> Any:
    """ASGI middleware for request count and latency metrics.

    Attach to the FastAPI app with:
        app.middleware("http")(record_request_metric)
    """
    route = request.url.path
    # Normalize to route template if available
    if request.scope.get("route"):
        route = getattr(request.scope["route"], "path", route)

    method = request.method
    start = time.monotonic()

    response = await call_next(request)

    elapsed = time.monotonic() - start
    status = str(response.status_code)

    http_requests_total.labels(method=method, route=route, status_code=status).inc()
    http_request_duration_seconds.labels(method=method, route=route).observe(elapsed)

    return response


# ── /metrics endpoint ─────────────────────────────────────────────────────────


@router.get(
    "/metrics",
    summary="Prometheus Metrics",
    description="Prometheus text-format metrics. Blocked by nginx from :8080; internal only.",
    include_in_schema=False,
)
async def metrics_endpoint() -> Response:
    """Serve Prometheus metrics. Refresh async gauges at most every 5 s."""
    await _refresh_gauges()
    data = generate_latest()
    return Response(content=data, media_type=CONTENT_TYPE_LATEST)
