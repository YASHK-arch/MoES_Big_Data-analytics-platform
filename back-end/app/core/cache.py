"""Redis-backed get-or-compute cache helper with single-flight locking."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
from typing import Any, Awaitable, Callable, Dict, Optional

from app.core.config import settings
from app.core.redis import redis_client

logger = logging.getLogger(__name__)


def generate_cache_key(endpoint: str, query_params: Optional[Dict[str, Any]] = None) -> str:
    """Generate cache key: endpoint + sha256 of sorted query params."""
    if not query_params:
        serialized = ""
    else:
        # Sort items by parameter name, omitting None values
        items = sorted((str(k), str(v)) for k, v in query_params.items() if v is not None)
        serialized = json.dumps(items)
    param_hash = hashlib.sha256(serialized.encode("utf-8")).hexdigest()
    return f"{endpoint}:{param_hash}"


async def get_or_compute(
    endpoint: str,
    query_params: Optional[Dict[str, Any]],
    compute_fn: Callable[[], Awaitable[Any]],
    ttl: Optional[int] = None,
) -> Any:
    """Get value from Redis cache or compute with single-flight lock.

    Key = endpoint + sha256 of sorted query params.
    TTL default 10 s via settings.DASHBOARD_CACHE_TTL_SECONDS.
    Uses SET NX lock so only one concurrent request computes on a miss
    while others wait up to 2 seconds or serve stale value.
    Fails open (computes directly) on Redis errors.
    """
    effective_ttl = ttl if ttl is not None else getattr(settings, "DASHBOARD_CACHE_TTL_SECONDS", 10)
    if effective_ttl <= 0:
        return await compute_fn()

    cache_key = generate_cache_key(endpoint, query_params)
    lock_key = f"lock:{cache_key}"
    stale_key = f"stale:{cache_key}"

    # 1. Try reading from cache
    try:
        cached = await redis_client.get(cache_key)
        if cached is not None:
            return json.loads(cached)
    except Exception as exc:
        logger.warning("Redis cache get error; computing directly: %s", exc)
        return await compute_fn()

    # 2. Cache miss -> acquire single-flight lock
    try:
        acquired = await redis_client.set(lock_key, "locked", ex=5, nx=True)
    except Exception as exc:
        logger.warning("Redis lock error; computing directly: %s", exc)
        return await compute_fn()

    if acquired:
        # Winner executes computation
        try:
            result = await compute_fn()
            # Serialize
            if hasattr(result, "model_dump"):
                serialized = json.dumps(result.model_dump(mode="json"))
            else:
                serialized = json.dumps(result)

            try:
                await redis_client.set(cache_key, serialized, ex=effective_ttl)
                # Keep stale copy for fallback (1 hour)
                await redis_client.set(stale_key, serialized, ex=3600)
            except Exception as exc:
                logger.warning("Redis cache write failed: %s", exc)

            return result
        finally:
            try:
                await redis_client.delete(lock_key)
            except Exception:
                pass
    else:
        # Another request holds the lock; wait up to 2 seconds or serve stale value
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline:
            await asyncio.sleep(0.05)
            try:
                cached = await redis_client.get(cache_key)
                if cached is not None:
                    return json.loads(cached)
            except Exception:
                break

        # If still not populated after waiting up to 2s, check for stale value
        try:
            stale_val = await redis_client.get(stale_key)
            if stale_val is not None:
                return json.loads(stale_val)
        except Exception:
            pass

        # Fallback to computing directly
        return await compute_fn()
