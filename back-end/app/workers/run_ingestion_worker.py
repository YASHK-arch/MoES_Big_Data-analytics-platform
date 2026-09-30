"""Executable standalone worker entry point for Incident Ingestion Stream Consumer.

Continuously polls and persists normalized incident events from stream:weather:events.

Usage:
    python -m app.workers.run_ingestion_worker
"""

import asyncio
import logging
import signal
import sys

from app.core.redis import redis_client
from app.db.session import engine
from app.workers.heartbeat import heartbeat_loop
from app.workers.ingestion_worker import ingestion_worker

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("app.workers.run_ingestion_worker")


def _handle_signal(sig: int, stop_event: asyncio.Event) -> None:
    sig_name = signal.Signals(sig).name
    logger.info(
        "Received shutdown signal %s (%d); initiating graceful worker shutdown...",
        sig_name,
        sig,
    )
    stop_event.set()


async def main() -> int:
    """Run the IngestionWorker standalone process with graceful signal handling."""
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
            signal.signal(sig, _fallback_signal_handler)

    logger.info("Initializing standalone IngestionWorker process...")

    try:
        await asyncio.gather(
            heartbeat_loop("ingestion", stop_event),
            ingestion_worker.run_loop(stop_event=stop_event),
        )
        return 0
    except asyncio.CancelledError:
        logger.info("Worker process task cancelled")
        return 0
    except Exception as e:
        logger.critical("Fatal error in IngestionWorker process: %s", e, exc_info=True)
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
        logger.info("IngestionWorker process shutdown complete")


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
