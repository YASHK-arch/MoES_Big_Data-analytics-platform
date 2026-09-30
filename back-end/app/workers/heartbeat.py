"""Worker heartbeat utility for health monitoring.

Each worker calls `heartbeat_loop(name, stop_event)` as a background task.
It writes /tmp/heartbeat every 10 s and sets Redis key worker:heartbeat:<name>
with a 30 s TTL. The compose HEALTHCHECK tests file age < 60 s.
"""

import asyncio
import logging
import os
import time

from app.core.redis import redis_client

logger = logging.getLogger(__name__)

HEARTBEAT_FILE = "/tmp/heartbeat"
HEARTBEAT_INTERVAL_SECONDS = 10
HEARTBEAT_TTL_SECONDS = 30


async def heartbeat_loop(worker_name: str, stop_event: asyncio.Event) -> None:
    """Touch /tmp/heartbeat and set Redis worker:heartbeat:<name> every 10 s."""
    redis_key = f"worker:heartbeat:{worker_name}"
    while not stop_event.is_set():
        try:
            # Touch the file (create/update mtime)
            with open(HEARTBEAT_FILE, "w") as f:
                f.write(f"{worker_name}:{int(time.time())}\n")
        except OSError as exc:
            logger.warning("Heartbeat file write failed: %s", exc)

        try:
            await redis_client.set(redis_key, str(int(time.time())), ex=HEARTBEAT_TTL_SECONDS)
        except Exception as exc:
            logger.warning("Heartbeat Redis write failed for %s: %s", worker_name, exc)

        try:
            await asyncio.wait_for(
                asyncio.shield(stop_event.wait()),
                timeout=float(HEARTBEAT_INTERVAL_SECONDS),
            )
        except asyncio.TimeoutError:
            pass  # Normal: interval elapsed, loop again
        except asyncio.CancelledError:
            break
