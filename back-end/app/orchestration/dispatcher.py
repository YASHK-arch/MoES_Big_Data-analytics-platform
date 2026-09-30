"""Redis Streams event dispatcher, worker consumer, and DLQ manager for orchestration.

Consumes from `stream:weather:orchestration` under consumer group `group:weather:orchestrators`.
Routes events via typed handler registry with at-least-once safety and DLQ replay.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import settings
from app.core.redis import AsyncRedisClient, redis_client
from app.db.session import async_session_factory
from app.orchestration.events import (
    AggregateType,
    FailureClass,
    OrchestrationEvent,
    OrchestrationEventType,
    StageExecutionResult,
    StageName,
    StageOutcome,
)
from app.orchestration.models import DeadLetterJob
from app.orchestration.retry_policy import RetryPolicy, retry_policy
from app.orchestration.triggers import (
    on_duplicate_cluster_updated,
    on_evidence_ingested,
    on_incident_ingested,
    on_observation_ingested,
)

logger = logging.getLogger(__name__)


class OrchestrationDispatcher:
    """Consumes and routes orchestration events from Redis Streams."""

    DEFAULT_STREAM = "stream:weather:orchestration"
    DEFAULT_GROUP = "group:weather:orchestrators"
    DEAD_LETTER_STREAM = "stream:weather:dead_letter"

    def __init__(
        self,
        client: Optional[AsyncRedisClient] = None,
        session_factory: Optional[async_sessionmaker[AsyncSession]] = None,
        retry_mgr: Optional[RetryPolicy] = None,
        consumer_name: str = "orchestrator-worker-1",
    ) -> None:
        self.client = client or redis_client
        self.session_factory = session_factory or async_session_factory
        self.retry_mgr = retry_mgr or retry_policy
        self.consumer_name = consumer_name
        self._claim_cursor: str = "0-0"

    async def publish_event(
        self,
        event: OrchestrationEvent,
        stream_name: Optional[str] = None,
    ) -> str:
        """Publish an orchestration event to Redis Stream."""
        stream = stream_name or self.DEFAULT_STREAM
        event_dict = event.model_dump(mode="json")
        payload_fields = {
            "event_id": str(event.event_id),
            "event_type": event.event_type.value,
            "aggregate_type": event.aggregate_type.value,
            "aggregate_id": str(event.aggregate_id),
            "correlation_id": event.correlation_id,
            "attempt": str(event.attempt),
            "data": json.dumps(event_dict),
        }

        msg_id = await self.client.xadd(stream, payload_fields)
        logger.info(
            "Published event %s (%s) to %s: %s",
            event.event_id,
            event.event_type.value,
            stream,
            msg_id,
        )
        return msg_id

    async def route_to_dead_letter(
        self,
        event: OrchestrationEvent,
        error_class: FailureClass,
        error_message: str,
        stage_name: Optional[str] = None,
    ) -> str:
        """Persist unrecoverable or max-attempt-exceeded event to the Dead Letter Queue."""
        dlq_job = DeadLetterJob(
            job_id=str(event.event_id),
            event_type=event.event_type.value,
            aggregate_type=event.aggregate_type.value,
            aggregate_id=str(event.aggregate_id),
            attempt=event.attempt,
            first_failed_at=event.created_at,
            dead_lettered_at=datetime.now(timezone.utc),
            error_class=error_class.value,
            error_message=error_message,
            stage_name=stage_name,
            payload=event.payload,
        )

        msg_id = await self.client.xadd(
            self.DEAD_LETTER_STREAM,
            {
                "job_id": dlq_job.job_id,
                "event_type": dlq_job.event_type,
                "error": dlq_job.error_message,
                "data": json.dumps(dlq_job.model_dump(mode="json")),
            },
        )
        logger.error(
            "Event %s routed to DLQ stream %s: %s (error: %s)",
            event.event_id,
            self.DEAD_LETTER_STREAM,
            msg_id,
            error_message,
        )
        return msg_id

    async def process_event(
        self,
        db: AsyncSession,
        event: OrchestrationEvent,
    ) -> StageExecutionResult:
        """Route an individual orchestration event to its appropriate trigger/handler."""
        try:
            # 1. New incident ingested -> run full pipeline
            if event.event_type == OrchestrationEventType.INCIDENT_INGESTED:
                state = await on_incident_ingested(db=db, incident_id=event.aggregate_id)
                return StageExecutionResult(
                    stage_name=state.last_successful_stage or StageName.LOCATION,
                    outcome=StageOutcome.SUCCESS_WITH_RESULTS,
                    results_summary={"overall_readiness": state.overall_readiness.value},
                )

            # 2. New evidence item ingested -> run targeted evidence trigger
            elif event.event_type == OrchestrationEventType.EVIDENCE_LINK_MODIFIED:
                if event.aggregate_type == AggregateType.EVIDENCE_ITEM:
                    affected = await on_evidence_ingested(db=db, evidence_id=event.aggregate_id)
                    return StageExecutionResult(
                        stage_name=StageName.EVIDENCE,
                        outcome=StageOutcome.SUCCESS_WITH_RESULTS,
                        affected_incident_ids=affected,
                    )
                else:
                    return StageExecutionResult(
                        stage_name=StageName.EVIDENCE,
                        outcome=StageOutcome.SUCCESS_WITH_RESULTS,
                    )

            # 3. New observation ingested -> run targeted observation trigger
            elif event.event_type == OrchestrationEventType.OBSERVATION_CORROBORATION_MODIFIED:
                if event.aggregate_type == AggregateType.WEATHER_OBSERVATION:
                    affected = await on_observation_ingested(
                        db=db, observation_id=event.aggregate_id
                    )
                    return StageExecutionResult(
                        stage_name=StageName.OBSERVATION,
                        outcome=StageOutcome.SUCCESS_WITH_RESULTS,
                        affected_incident_ids=affected,
                    )
                else:
                    return StageExecutionResult(
                        stage_name=StageName.OBSERVATION,
                        outcome=StageOutcome.SUCCESS_WITH_RESULTS,
                    )

            # 4. Duplicate cluster modified -> run cluster trigger
            elif event.event_type == OrchestrationEventType.DUPLICATE_CLUSTER_MODIFIED:
                affected = await on_duplicate_cluster_updated(db=db, cluster_id=event.aggregate_id)
                return StageExecutionResult(
                    stage_name=StageName.DUPLICATE,
                    outcome=StageOutcome.SUCCESS_WITH_RESULTS,
                    affected_incident_ids=affected,
                )

            # 5. Unknown event type -> permanent failure
            else:
                logger.error("Unknown or unhandled event type: %s", event.event_type)
                return StageExecutionResult(
                    stage_name=StageName.LOCATION,
                    outcome=StageOutcome.PERMANENT_FAILURE,
                    error_class=FailureClass.PERMANENT,
                    error_message=f"Unhandled event type '{event.event_type}'",
                )

        except Exception as exc:
            err_class = self.retry_mgr.classify_error(exc)
            logger.error(
                "Error processing orchestration event %s: %s", event.event_id, exc, exc_info=True
            )
            return StageExecutionResult(
                stage_name=StageName.CREDIBILITY,
                outcome=(
                    StageOutcome.RETRYABLE_FAILURE
                    if err_class == FailureClass.TRANSIENT
                    else StageOutcome.PERMANENT_FAILURE
                ),
                error_class=err_class,
                error_message=str(exc),
            )

    async def read_events(
        self,
        count: int = 10,
        block_ms: Optional[int] = 2000,
        from_id: str = ">",
        claim_idle_ms: Optional[int] = None,
    ) -> List[Tuple[str, OrchestrationEvent]]:
        """Read a batch of orchestration events from Redis Streams, reclaiming idle unacked messages first."""
        await self.client.xgroup_create(
            self.DEFAULT_STREAM, self.DEFAULT_GROUP, id_str="0", mkstream=True
        )

        entries_to_process: List[Tuple[str, Dict[str, str]]] = []

        if from_id == ">":
            idle_ms = (
                claim_idle_ms
                if claim_idle_ms is not None
                else getattr(settings, "STREAM_CLAIM_IDLE_MS", 60000)
            )
            max_attempts = getattr(settings, "STREAM_MAX_DELIVERY_ATTEMPTS", 3)
            try:
                next_start, claimed = await self.client.xautoclaim(
                    stream=self.DEFAULT_STREAM,
                    group=self.DEFAULT_GROUP,
                    consumer=self.consumer_name,
                    min_idle_time_ms=idle_ms,
                    start_id=self._claim_cursor,
                    count=count,
                )
                self._claim_cursor = next_start if next_start else "0-0"
                if claimed:
                    pending_details = await self.client.xpending_detail(
                        self.DEFAULT_STREAM, self.DEFAULT_GROUP, count=max(count * 2, 50)
                    )
                    delivery_map = {item["id"]: item["deliveries"] for item in pending_details}

                    for msg_id, fields in claimed:
                        deliveries = delivery_map.get(msg_id, 1)
                        if deliveries > max_attempts:
                            logger.error(
                                "Event %s exceeded max delivery attempts (%d > %d), routing to DLQ",
                                msg_id,
                                deliveries,
                                max_attempts,
                            )
                            try:
                                data_dict = json.loads(fields.get("data", "{}"))
                                ev = OrchestrationEvent.model_validate(data_dict)
                                await self.route_to_dead_letter(
                                    event=ev,
                                    error_class=FailureClass.PERMANENT,
                                    error_message=f"Exceeded max delivery attempts ({deliveries}/{max_attempts})",
                                    stage_name=StageName.LOCATION.value,
                                )
                            except Exception:
                                await self.client.xadd(
                                    self.DEAD_LETTER_STREAM,
                                    {
                                        "msg_id": msg_id,
                                        "reason": f"Exceeded max deliveries ({deliveries})",
                                        "fields": json.dumps(fields),
                                    },
                                )
                            await self.client.xack(self.DEFAULT_STREAM, self.DEFAULT_GROUP, msg_id)
                        else:
                            entries_to_process.append((msg_id, fields))
            except Exception as e:
                logger.warning("Failed during XAUTOCLAIM in dispatcher: %s", e)

        remaining_count = count - len(entries_to_process)
        if remaining_count > 0:
            raw_results = await self.client.xreadgroup(
                group=self.DEFAULT_GROUP,
                consumer=self.consumer_name,
                streams={self.DEFAULT_STREAM: from_id},
                count=remaining_count,
                block_ms=block_ms if not entries_to_process else None,
            )
            for _, entries in raw_results:
                entries_to_process.extend(entries)

        events: List[Tuple[str, OrchestrationEvent]] = []
        for msg_id, fields in entries_to_process:
            try:
                if "data" in fields:
                    data_dict = json.loads(fields["data"])
                    ev = OrchestrationEvent.model_validate(data_dict)
                else:
                    ev = OrchestrationEvent.model_validate(fields)
                events.append((msg_id, ev))
            except Exception as e:
                logger.error("Failed to parse orchestration stream message '%s': %s", msg_id, e)
                # Acknowledge unrecoverable malformed message so queue does not block
                await self.client.xack(self.DEFAULT_STREAM, self.DEFAULT_GROUP, msg_id)

        return events

    async def process_batch(
        self,
        count: int = 10,
        block_ms: Optional[int] = 1000,
    ) -> List[Tuple[str, StageExecutionResult]]:
        """Fetch a batch of orchestration events from Redis, process, and ACK or route to DLQ."""
        events = await self.read_events(count=count, block_ms=block_ms)
        results: List[Tuple[str, StageExecutionResult]] = []

        if not events:
            return results

        async with self.session_factory() as session:
            for msg_id, event in events:
                res = await self.process_event(db=session, event=event)
                results.append((msg_id, res))

                if res.outcome in (
                    StageOutcome.SUCCESS_WITH_RESULTS,
                    StageOutcome.SUCCESS_WITH_NO_MATCH,
                    StageOutcome.SUCCESS_WITH_INSUFFICIENT_DATA,
                    StageOutcome.SKIPPED_NOT_APPLICABLE,
                    StageOutcome.SKIPPED_STALE,
                ):
                    # Successfully completed -> ACK message
                    await self.client.xack(self.DEFAULT_STREAM, self.DEFAULT_GROUP, msg_id)
                elif (
                    res.error_class == FailureClass.TRANSIENT and event.attempt < event.max_attempts
                ):
                    # Transient error: schedule retry with backoff
                    retry_event = event.model_copy(deep=True)
                    retry_event.attempt += 1
                    delay = self.retry_mgr.calculate_backoff_seconds(retry_event.attempt)
                    logger.warning(
                        "Scheduling retry for event %s (attempt %d/%d) in %.1fs",
                        event.event_id,
                        retry_event.attempt,
                        event.max_attempts,
                        delay,
                    )
                    await self.client.xack(self.DEFAULT_STREAM, self.DEFAULT_GROUP, msg_id)
                    await self.publish_event(retry_event)
                else:
                    # Max attempts reached or permanent failure -> Route to DLQ & ACK
                    await self.route_to_dead_letter(
                        event=event,
                        error_class=res.error_class,
                        error_message=res.error_message or "Unknown failure",
                        stage_name=res.stage_name.value,
                    )
                    await self.client.xack(self.DEFAULT_STREAM, self.DEFAULT_GROUP, msg_id)

        return results

    async def replay_dead_letter_job(
        self,
        db: AsyncSession,
        event_dict: Dict[str, Any],
    ) -> StageExecutionResult:
        """Replay a dead-lettered job by resetting attempt count to 1 and re-dispatching."""
        event_dict["attempt"] = 1
        event = OrchestrationEvent.model_validate(event_dict)
        logger.info("Replaying dead-letter job %s (%s)", event.event_id, event.event_type.value)
        return await self.process_event(db=db, event=event)


orchestration_dispatcher = OrchestrationDispatcher()
