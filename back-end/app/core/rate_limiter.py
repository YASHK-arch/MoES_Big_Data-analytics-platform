"""Sliding window rate limiter for security endpoints with Redis backing and fail-open support."""

from __future__ import annotations

import logging
import time
from collections import defaultdict
from typing import Any, Dict, List, Optional

from app.core.config import settings

logger = logging.getLogger(__name__)


def get_client_ip(request: Any) -> str:
    """Extract client IP address from request.

    Defaults to request.client.host.
    Only inspects X-Forwarded-For if settings.TRUSTED_PROXY_COUNT > 0,
    taking the Nth address from the right.
    """
    if not request:
        return "127.0.0.1"

    trusted_proxies = getattr(settings, "TRUSTED_PROXY_COUNT", 0)
    if trusted_proxies > 0 and hasattr(request, "headers"):
        forwarded = request.headers.get("x-forwarded-for") or request.headers.get("X-Forwarded-For")
        if forwarded:
            ips = [ip.strip() for ip in forwarded.split(",") if ip.strip()]
            if ips:
                # Nth address from the right
                idx = min(trusted_proxies, len(ips))
                return ips[-idx]

    if hasattr(request, "client") and request.client and getattr(request.client, "host", None):
        return request.client.host

    return "127.0.0.1"


class SlidingWindowRateLimiter:
    """Sliding-window rate limiter tracking request timestamps per client key."""

    def __init__(self, max_requests: int = 10, window_seconds: float = 60.0) -> None:
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._history: Dict[str, List[float]] = defaultdict(list)
        self._active_keys: set[str] = set()

    def is_allowed(self, key: str, max_requests: Optional[int] = None) -> bool:
        """Check if request for key is allowed synchronously; prune expired timestamps."""
        now = time.monotonic()
        cutoff = now - self.window_seconds
        limit = max_requests if max_requests is not None else self.max_requests

        # Prune older entries
        timestamps = [ts for ts in self._history[key] if ts > cutoff]
        self._history[key] = timestamps

        if len(timestamps) >= limit:
            return False

        self._history[key].append(now)
        return True

    async def is_allowed_async(self, key: str, max_requests: Optional[int] = None) -> bool:
        """Check rate limit backed by Redis.

        If Redis is unavailable, logs a warning and fails OPEN (returns True).
        """
        limit = max_requests if max_requests is not None else self.max_requests
        from app.core.redis import redis_client

        try:
            if hasattr(self, "_active_keys"):
                self._active_keys.add(key)
            bucket = int(time.time() // self.window_seconds)
            redis_key = f"ratelimit:{key}:{bucket}"
            val = await redis_client.incr(redis_key)
            if val == 1:
                await redis_client.expire(redis_key, int(self.window_seconds) + 5)
            if val > limit:
                return False
            return True
        except Exception as exc:
            logger.warning("Redis unavailable for rate limiter; failing OPEN: %s", exc)
            return True

    def get_retry_after(self, key: str) -> int:
        """Return recommended retry-after seconds until oldest entry expires."""
        now = time.monotonic()
        cutoff = now - self.window_seconds
        timestamps = [ts for ts in self._history.get(key, []) if ts > cutoff]
        if not timestamps:
            return 1
        oldest = min(timestamps)
        remaining = int(oldest + self.window_seconds - now + 0.999)
        return max(1, remaining)

    async def get_retry_after_async(self, key: str) -> int:
        """Calculate retry-after seconds for Redis window."""
        now = time.time()
        remaining = int(self.window_seconds - (now % self.window_seconds))
        return max(1, remaining)

    def reset(self, key: str) -> None:
        """Reset history for a given key (e.g. on successful authentication)."""
        if key in self._history:
            del self._history[key]
        try:
            import asyncio

            loop = asyncio.get_running_loop()
            bucket = int(time.time() // self.window_seconds)
            redis_key = f"ratelimit:{key}:{bucket}"
            from app.core.redis import redis_client

            loop.create_task(redis_client.delete(redis_key))
        except (RuntimeError, Exception):
            pass

    async def reset_async(self, key: str) -> None:
        """Reset rate limit in Redis and memory."""
        self.reset(key)
        from app.core.redis import redis_client

        try:
            bucket = int(time.time() // self.window_seconds)
            redis_key = f"ratelimit:{key}:{bucket}"
            await redis_client.delete(redis_key)
        except Exception:
            pass

    def clear(self) -> None:
        """Clear all in-memory rate limit history and Redis keys."""
        try:
            import asyncio

            loop = asyncio.get_running_loop()
            bucket = int(time.time() // self.window_seconds)
            from app.core.redis import redis_client

            for k in set(self._history.keys()) | getattr(self, "_active_keys", set()):
                loop.create_task(redis_client.delete(f"ratelimit:{k}:{bucket}"))
        except (RuntimeError, Exception):
            pass
        self._history.clear()
        if hasattr(self, "_active_keys"):
            self._active_keys.clear()


# Global rate limiter instance for authentication endpoints
login_rate_limiter = SlidingWindowRateLimiter(max_requests=15, window_seconds=60.0)

# Global rate limiter instance for citizen report submissions
report_rate_limiter = SlidingWindowRateLimiter(max_requests=10, window_seconds=60.0)
