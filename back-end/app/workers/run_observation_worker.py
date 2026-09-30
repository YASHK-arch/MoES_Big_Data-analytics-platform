"""Executable standalone worker entry point for Observation Stream Consumer.

Continuously polls and persists normalized sensor observations from stream:weather:observations.

Usage:
    python -m app.workers.run_observation_worker
"""

import asyncio
import logging
import signal
import sys

from app.core.redis import redis_client
from app.db.session import engine
from app.workers.observation_worker import observation_worker
from app.workers.heartbeat import heartbeat_loop


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("app.workers.run_observation_worker")


def _handle_signal(sig: int, stop_event: asyncio.Event) -> None:
    sig_name = signal.Signals(sig).name
    logger.info(
        "Received shutdown signal %s (%d); initiating graceful worker shutdown...",
        sig_name,
        sig,
    )
    stop_event.set()


async def main() -> int:
    """Run the ObservationWorker standalone process with graceful signal handling."""
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

    logger.info("Initializing standalone ObservationWorker process...")

    try:
        await asyncio.gather(
            heartbeat_loop("observation", stop_event),
            observation_worker.run_loop(stop_event=stop_event),
        )
        return 0
    except asyncio.CancelledError:
        logger.info("Worker process task cancelled")
        return 0
    except Exception as e:
        logger.critical("Fatal error in ObservationWorker process: %s", e, exc_info=True)
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
        logger.info("ObservationWorker process shutdown complete")


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
