"""Grid-hour observation cache with single-flight deduplication.

Ensures that concurrent or rapid successive requests for the same ~0.25° grid cell
and hour make exactly ONE provider call (single-flight locking) and serve all
subsequent queries directly from cache (TTL 3600s).
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Awaitable, Callable, Dict, Optional, Tuple

from app.intelligence.physical_corroboration.evaluator import compute_grid_hour_cache_key
from app.intelligence.physical_corroboration.models import (
    PhysicalObservation,
    ProviderStatus,
)

logger = logging.getLogger(__name__)


class SingleFlightGridHourCache:
    """Cache and single-flight coordinator for physical weather observations."""

    def __init__(self, ttl_seconds: int = 3600) -> None:
        self.ttl_seconds = ttl_seconds
        self._in_memory_cache: Dict[str, Tuple[PhysicalObservation, float]] = {}
        self._in_flight: Dict[
            str, asyncio.Future[Tuple[Optional[PhysicalObservation], ProviderStatus, Optional[str]]]
        ] = {}
        self._lock = asyncio.Lock()
        self.cache_hits: int = 0
        self.cache_misses: int = 0

    async def get_or_fetch(
        self,
        lat: float,
        lon: float,
        target_time: datetime,
        fetch_coroutine_fn: Callable[
            [], Awaitable[Tuple[Optional[PhysicalObservation], ProviderStatus, Optional[str]]]
        ],
    ) -> Tuple[Optional[PhysicalObservation], ProviderStatus, Optional[str], bool]:
        """Fetch or retrieve from cache with single-flight guarantee.

        Returns:
            (observation, provider_status, error_message, is_cache_hit)
        """
        cache_key = compute_grid_hour_cache_key(lat, lon, target_time)
        loop = asyncio.get_running_loop()
        now = loop.time()

        # 1. Check in-memory cache
        if cache_key in self._in_memory_cache:
            obs, expire_at = self._in_memory_cache[cache_key]
            if now < expire_at:
                self.cache_hits += 1
                return obs, ProviderStatus.OK, None, True
            else:
                del self._in_memory_cache[cache_key]

        # 2. Check single-flight in-flight map
        async with self._lock:
            if cache_key in self._in_flight:
                future = self._in_flight[cache_key]
                is_leader = False
            else:
                future = loop.create_future()
                self._in_flight[cache_key] = future
                is_leader = True

        if not is_leader:
            # Follower: await the leader's in-flight execution
            self.cache_hits += 1
            obs, status, err = await future
            return obs, status, err, True

        # Leader: execute the actual fetch
        self.cache_misses += 1
        try:
            obs, status, err = await fetch_coroutine_fn()
            if status == ProviderStatus.OK and obs is not None:
                self._in_memory_cache[cache_key] = (obs, now + self.ttl_seconds)

            future.set_result((obs, status, err))
            return obs, status, err, False

        except Exception as exc:
            err_msg = f"Single-flight execution failed: {exc}"
            logger.error(err_msg)
            res = (None, ProviderStatus.PROVIDER_ERROR, err_msg)
            future.set_result(res)
            return res[0], res[1], res[2], False

        finally:
            async with self._lock:
                self._in_flight.pop(cache_key, None)

    def clear(self) -> None:
        """Clear memory cache for testing."""
        self._in_memory_cache.clear()
        self._in_flight.clear()
        self.cache_hits = 0
        self.cache_misses = 0
