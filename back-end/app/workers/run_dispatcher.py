"""Executable standalone worker entry point for Intelligence Orchestration.

Continuously polls and executes intelligence pipeline stages for queued reports.

Usage:
    python -m app.workers.run_dispatcher
"""

import asyncio
import logging
import os
import signal
import sys

from app.core.redis import redis_client
from app.db.session import engine
from app.orchestration.dispatcher import orchestration_dispatcher
from app.workers.heartbeat import heartbeat_loop

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("app.workers.run_dispatcher")


def _handle_signal(sig: int, stop_event: asyncio.Event) -> None:
    sig_name = signal.Signals(sig).name
    logger.info(
        "Received shutdown signal %s (%d); initiating graceful worker shutdown...",
        sig_name,
        sig,
    )
    stop_event.set()


async def main() -> int:
    """Run the OrchestrationDispatcher standalone process with graceful signal handling."""
    stop_event = asyncio.Event()
    _hb_task = asyncio.ensure_future(heartbeat_loop("dispatcher", stop_event))
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

    consumer_name = os.environ.get("ORCHESTRATOR_CONSUMER_NAME")
    if consumer_name:
        orchestration_dispatcher.consumer_name = consumer_name
    logger.info("Initializing standalone OrchestrationDispatcher process (%s)...", orchestration_dispatcher.consumer_name)

    try:
        # Loop until stop event is set
        while not stop_event.is_set():
            try:
                # The process_batch handles exceptions for individual events
                await orchestration_dispatcher.process_batch(count=10, block_ms=2000)
            except Exception as loop_err:
                logger.error(
                    "Unexpected error in dispatcher polling loop: %s", loop_err, exc_info=True
                )
                await asyncio.sleep(5)  # Backoff on catastrophic loop failure

        return 0
    except asyncio.CancelledError:
        logger.info("Worker process task cancelled")
        return 0
    except Exception as e:
        logger.critical("Fatal error in OrchestrationDispatcher process: %s", e, exc_info=True)
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
        logger.info("OrchestrationDispatcher process shutdown complete")


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
