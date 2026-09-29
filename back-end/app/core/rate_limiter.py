"""In-memory sliding window rate limiter for security endpoints."""

from __future__ import annotations

import time
from collections import defaultdict
from typing import Dict, List


class SlidingWindowRateLimiter:
    """Sliding-window rate limiter tracking request timestamps per client key."""

    def __init__(self, max_requests: int = 10, window_seconds: float = 60.0) -> None:
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._history: Dict[str, List[float]] = defaultdict(list)

    def is_allowed(self, key: str) -> bool:
        """Check if request for key is allowed; prune expired timestamps."""
        now = time.monotonic()
        cutoff = now - self.window_seconds

        # Prune older entries
        timestamps = [ts for ts in self._history[key] if ts > cutoff]
        self._history[key] = timestamps

        if len(timestamps) >= self.max_requests:
            return False

        self._history[key].append(now)
        return True

    def reset(self, key: str) -> None:
        """Reset history for a given key (e.g. on successful authentication)."""
        if key in self._history:
            del self._history[key]


# Global rate limiter instance for authentication endpoints
login_rate_limiter = SlidingWindowRateLimiter(max_requests=15, window_seconds=60.0)
