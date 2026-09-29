"""Executable standalone worker entry point for Ingestion Scheduling.

Periodically triggers all registered ingestion adapters and publishes
normalized events to the ingestion Redis stream.

Usage:
    python -m app.workers.run_scheduler
"""

import asyncio
import logging
import signal
import sys
import time
from typing import Any, List

from app.core.config import settings
from app.core.redis import redis_client
from app.db.session import async_session_factory
from app.ingestion import adapter_registry
from app.ingestion.schemas import (
    NormalizedEvidenceEvent,
    NormalizedIngestionEvent,
    NormalizedObservationEvent,
)
from app.services.retention_service import retention_service
from app.services.stream_service import stream_service

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("app.workers.run_scheduler")


def _handle_signal(sig: int, stop_event: asyncio.Event) -> None:
    sig_name = signal.Signals(sig).name
    logger.info(
        "Received shutdown signal %s (%d); initiating graceful worker shutdown...",
        sig_name,
        sig,
    )
    stop_event.set()


async def trigger_ingestion_cycle() -> None:
    """Trigger all registered adapters and route events to appropriate Redis streams."""
    adapters = adapter_registry.list_adapters()
    logger.info(
        "Starting ingestion cycle across %d registered adapters...",
        len(adapters),
    )

    for adapter in adapters:
        try:
            logger.info("Running adapter: %s", adapter.source_code)
            events: List[Any] = await adapter.ingest()
            published_count = 0

            for event in events:
                try:
                    if isinstance(event, NormalizedIngestionEvent):
                        await stream_service.publish_event(event)
                        published_count += 1
                    elif isinstance(event, NormalizedObservationEvent):
                        await stream_service.publish_observation(event)
                        published_count += 1
                    elif isinstance(event, NormalizedEvidenceEvent):
                        await stream_service.publish_evidence(event)
                        published_count += 1
                    else:
                        logger.warning(
                            "Skipping unrecognized event type from adapter %s: %s",
                            adapter.source_code,
                            type(event),
                        )
                except Exception as ev_err:
                    logger.error(
                        "Failed to publish event from adapter %s: %s",
                        adapter.source_code,
                        ev_err,
                        exc_info=True,
                    )

            logger.info(
                "Adapter %s completed successfully. Published %d/%d events.",
                adapter.source_code,
                published_count,
                len(events),
            )
        except Exception as e:
            logger.error(
                "Adapter %s failed during ingestion cycle: %s",
                adapter.source_code,
                e,
                exc_info=True,
            )


async def trigger_retention_cycle(dry_run: bool = False) -> None:
    """Trigger data retention cycle to prune and archive expired records."""
    if not getattr(settings, "DATA_RETENTION_ENABLED", True):
        return

    logger.info("Starting scheduled data retention cycle...")
    try:
        async with async_session_factory() as session:
            result = await retention_service.run_retention_cycle(
                session=session,
                retention_days=settings.DATA_RETENTION_DAYS,
                dry_run=dry_run,
            )
            await session.commit()
            logger.info(
                "Data retention cycle completed successfully: archived=%d, deleted_reports=%d, "
                "deleted_obs=%d, deleted_evidence=%d in %.2fms",
                result.reports_archived,
                result.reports_deleted,
                result.observations_deleted,
                result.evidence_deleted,
                result.duration_ms,
            )
    except Exception as e:
        logger.error("Failed to execute data retention cycle: %s", e, exc_info=True)


async def main() -> int:
    """Run the Ingestion Scheduler standalone process with graceful signal handling."""
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

    logger.info("Initializing standalone Ingestion Scheduler process...")

    try:
        # Loop until stop event is set
        poll_interval = getattr(settings, "INGESTION_SCHEDULER_INTERVAL_SECONDS", 60.0)
        retention_interval = getattr(settings, "DATA_RETENTION_RUN_INTERVAL_SECONDS", 86400.0)
        last_retention_run = 0.0

        while not stop_event.is_set():
            try:
                await trigger_ingestion_cycle()
            except Exception as loop_err:
                logger.error(
                    "Unexpected error in ingestion scheduler cycle: %s",
                    loop_err,
                    exc_info=True,
                )

            # Check if retention cycle is due
            now_ts = time.time()
            if now_ts - last_retention_run >= retention_interval:
                try:
                    await trigger_retention_cycle()
                    last_retention_run = now_ts
                except Exception as ret_err:
                    logger.error(
                        "Unexpected error in retention scheduler cycle: %s",
                        ret_err,
                        exc_info=True,
                    )

            # Wait for next cycle or shutdown signal
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=poll_interval)
            except asyncio.TimeoutError:
                pass  # Timeout means we continue to the next cycle

        return 0
    except asyncio.CancelledError:
        logger.info("Worker process task cancelled")
        return 0
    except Exception as e:
        logger.critical("Fatal error in Ingestion Scheduler process: %s", e, exc_info=True)
        return 1
    finally:
        logger.info("Closing Redis connection pools...")
        try:
            await redis_client.close()
        except Exception as e:
            logger.warning("Error closing Redis client: %s", e)
        logger.info("Ingestion Scheduler process shutdown complete")


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
