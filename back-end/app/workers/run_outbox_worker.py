"""Executable standalone worker entry point for Realtime Outbox publisher.

Continuously polls and delivers pending transactional outbox events to Redis Streams.

Usage:
    python -m app.workers.run_outbox_worker
"""

import asyncio
import logging
import signal
import sys

from app.core.config import settings
from app.core.redis import redis_client
from app.db.session import engine
from app.workers.heartbeat import heartbeat_loop
from app.workers.outbox_worker import RealtimeOutboxWorker

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("app.workers.run_outbox_worker")


def _handle_signal(sig: int, stop_event: asyncio.Event) -> None:
    sig_name = signal.Signals(sig).name
    logger.info(
        "Received shutdown signal %s (%d); initiating graceful worker shutdown...",
        sig_name,
        sig,
    )
    stop_event.set()


async def main() -> int:
    """Run the RealtimeOutboxWorker standalone process with graceful signal handling."""
    if not settings.OUTBOX_WORKER_ENABLED:
        logger.warning(
            "Standalone RealtimeOutboxWorker invoked but OUTBOX_WORKER_ENABLED is false; exiting."
        )
        return 0

    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()

    def _make_signal_callback(s: int):
        return lambda: _handle_signal(s, stop_event)

    def _fallback_signal_handler(signum: int, frame: object) -> None:
        _handle_signal(signum, stop_event)

    # Register signal handlers for graceful termination
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, _make_signal_callback(sig))
        except NotImplementedError:
            # Fallback for environments where add_signal_handler is not available
            signal.signal(sig, _fallback_signal_handler)

    logger.info("Initializing standalone RealtimeOutboxWorker process...")
    worker = RealtimeOutboxWorker()

    try:
        await asyncio.gather(
            heartbeat_loop("outbox", stop_event),
            worker.run_loop(stop_event=stop_event),
        )
        return 0
    except asyncio.CancelledError:
        logger.info("Worker process task cancelled")
        return 0
    except Exception as e:
        logger.critical("Fatal error in RealtimeOutboxWorker process: %s", e, exc_info=True)
        return 1
    finally:
        logger.info("Closing database engine and Redis connection pools...")
        try:
            await redis_client.close()
        except Exception as e:
            logger.warning("Error closing Redis client: %s", e)
        try:
            await engine.dispose()
        except Exception as e:
            logger.warning("Error disposing database engine: %s", e)
        logger.info("RealtimeOutboxWorker process shutdown complete")


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
