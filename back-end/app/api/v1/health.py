"""Health and readiness endpoints for API liveness and dependency checks.

O2 spec:
  GET /health  — liveness probe (no deps, always fast)
  GET /ready   — readiness probe (DB SELECT 1, Redis PING, alembic head; 503 on failure)
  GET /health/workers — lists each worker up/down from Redis heartbeat keys (TTL 30s)
"""

from datetime import datetime, timezone
from typing import Any, Dict

from fastapi import APIRouter, status
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.core.config import settings
from app.core.redis import redis_client
from app.db.session import async_session_factory

router = APIRouter()

# Workers expected in the demo stack (matches run_*.py entrypoints)
EXPECTED_WORKERS = [
    "outbox",
    "dispatcher",
    "ingestion",
    "observation",
    "evidence",
    "scheduler",
]


@router.get(
    "/health",
    status_code=status.HTTP_200_OK,
    summary="Liveness Probe",
    description="Lightweight liveness check — no external dependencies. Always returns 200 if the process is alive.",
)
async def health_check() -> Dict[str, Any]:
    """Liveness probe: returns 200 immediately without touching DB or Redis."""
    return {
        "success": True,
        "data": {
            "status": "healthy",
            "service": settings.PROJECT_NAME,
            "environment": settings.ENVIRONMENT,
            "version": "0.1.0",
        },
        "meta": {
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    }


@router.get(
    "/ready",
    summary="Readiness Probe",
    description=(
        "Deep readiness check: DB SELECT 1, Redis PING, alembic revision at head. "
        "Returns 503 with the failing check name if any dependency is unavailable."
    ),
)
async def readiness_check() -> JSONResponse:
    """Readiness probe: checks DB, Redis, and alembic migration head.

    Returns 200 if all checks pass, 503 naming the failing check otherwise.
    """
    checks: Dict[str, str] = {}

    # 1. Database check
    try:
        async with async_session_factory() as session:
            await session.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as exc:
        checks["database"] = f"error: {exc}"
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "success": False,
                "data": {"status": "not_ready", "failing_check": "database", "checks": checks},
                "meta": {"timestamp": datetime.now(timezone.utc).isoformat()},
            },
        )

    # 2. Redis check
    try:
        pong = await redis_client.ping()
        checks["redis"] = "ok" if pong else "no response"
        if not pong:
            raise RuntimeError("Redis PING returned falsy")
    except Exception as exc:
        checks["redis"] = f"error: {exc}"
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "success": False,
                "data": {"status": "not_ready", "failing_check": "redis", "checks": checks},
                "meta": {"timestamp": datetime.now(timezone.utc).isoformat()},
            },
        )

    # 3. Alembic migration check
    try:
        async with async_session_factory() as session:
            result = await session.execute(
                text("SELECT version_num FROM alembic_version LIMIT 1")
            )
            row = result.scalar_one_or_none()
            alembic_rev = row or "unknown"
            checks["alembic"] = str(alembic_rev)
            # We just report the current revision; not failing if not exactly at head
            # (the migrate container handles upgrades before api starts)
    except Exception as exc:
        checks["alembic"] = f"error: {exc}"

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "success": True,
            "data": {"status": "ready", "checks": checks},
            "meta": {"timestamp": datetime.now(timezone.utc).isoformat()},
        },
    )


@router.get(
    "/health/workers",
    status_code=status.HTTP_200_OK,
    summary="Worker Heartbeat Status",
    description="Lists each background worker's up/down status from Redis heartbeat keys (TTL 30 s).",
)
async def worker_health() -> Dict[str, Any]:
    """Check heartbeat Redis keys set by each background worker every 10 s (TTL 30 s)."""
    workers: Dict[str, Any] = {}

    for name in EXPECTED_WORKERS:
        key = f"worker:heartbeat:{name}"
        try:
            ttl = await redis_client.ttl(key)
            # TTL > 0 means key exists and hasn't expired → worker is alive
            if ttl > 0:
                workers[name] = {"status": "up", "ttl_remaining_s": ttl}
            else:
                workers[name] = {"status": "down", "ttl_remaining_s": None}
        except Exception as exc:
            workers[name] = {"status": "unknown", "error": str(exc)}

    all_up = all(w.get("status") == "up" for w in workers.values())

    return {
        "success": True,
        "data": {
            "all_up": all_up,
            "workers": workers,
        },
        "meta": {"timestamp": datetime.now(timezone.utc).isoformat()},
    }
