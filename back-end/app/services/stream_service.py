import json
import logging
from typing import Dict, List, Optional, Tuple

from app.core.config import settings
from app.core.redis import AsyncRedisClient, redis_client
from app.ingestion.schemas import (
    NormalizedEvidenceEvent,
    NormalizedIngestionEvent,
    NormalizedObservationEvent,
)

logger = logging.getLogger(__name__)


class StreamService:
    """Service abstraction for publishing and consuming normalized events over Redis Streams."""

    DEFAULT_STREAM = "stream:weather:events"
    DEFAULT_GROUP = "group:weather:processors"

    DEFAULT_OBSERVATION_STREAM = "stream:weather:observations"
    DEFAULT_OBSERVATION_GROUP = "group:weather:observation_processors"

    DEFAULT_EVIDENCE_STREAM = "stream:weather:evidence"
    DEFAULT_EVIDENCE_GROUP = "group:weather:evidence_processors"

    DEFAULT_ORCHESTRATION_STREAM = "stream:weather:orchestration"
    DEFAULT_ORCHESTRATION_GROUP = "group:weather:orchestrators"
    DEFAULT_DEAD_LETTER_STREAM = "stream:weather:dead_letter"

    def __init__(self, client: Optional[AsyncRedisClient] = None) -> None:
        self.client = client or redis_client

    async def publish_event(
        self,
        event: NormalizedIngestionEvent,
        stream_name: Optional[str] = None,
    ) -> str:
        """Publish a normalized ingestion event payload to a Redis Stream."""
        stream = stream_name or self.DEFAULT_STREAM
        event_dict = event.model_dump(mode="json")
        payload_fields = {
            "event_id": str(event.event_id),
            "source_code": event.source_code,
            "external_id": event.external_id or "",
            "category_code": event.category_code or "OTHER",
            "severity": event.severity,
            "title": event.title,
            "occurred_at": event.occurred_at.isoformat(),
            "data": json.dumps(event_dict),
        }

        try:
            msg_id = await self.client.xadd(stream, payload_fields)
            logger.info(
                f"Published event '{event.event_id}' ({event.source_code}) to '{stream}': {msg_id}"
            )
            return msg_id
        except Exception as e:
            logger.error(f"Failed to publish ingestion event to Redis Stream '{stream}': {e}")
            raise

    async def publish_observation(
        self,
        observation: NormalizedObservationEvent,
        stream_name: Optional[str] = None,
    ) -> str:
        """Publish a normalized observation payload to the observation Redis Stream."""
        stream = stream_name or self.DEFAULT_OBSERVATION_STREAM
        obs_dict = observation.model_dump(mode="json")
        payload_fields = {
            "event_id": str(observation.event_id),
            "source_code": observation.source_code,
            "external_id": observation.external_id or "",
            "station_code": observation.station_code,
            "station_name": observation.station_name,
            "observed_at": observation.observed_at.isoformat(),
            "data": json.dumps(obs_dict),
        }

        try:
            msg_id = await self.client.xadd(stream, payload_fields)
            logger.info(
                f"Published observation '{observation.event_id}' "
                f"({observation.station_code}) to '{stream}': {msg_id}"
            )
            return msg_id
        except Exception as e:
            logger.error(f"Failed to publish observation to Redis Stream '{stream}': {e}")
            raise

    async def publish_evidence(
        self,
        evidence: NormalizedEvidenceEvent,
        stream_name: Optional[str] = None,
    ) -> str:
        """Publish a normalized evidence item to the evidence Redis Stream."""
        stream = stream_name or self.DEFAULT_EVIDENCE_STREAM
        ev_dict = evidence.model_dump(mode="json")
        payload_fields = {
            "event_id": str(evidence.event_id),
            "source_code": evidence.source_code,
            "external_id": evidence.external_id,
            "title": evidence.title,
            "domain": evidence.publisher_domain or "",
            "published_at": evidence.published_at.isoformat() if evidence.published_at else "",
            "data": json.dumps(ev_dict),
        }

        try:
            msg_id = await self.client.xadd(stream, payload_fields)
            logger.info(
                f"Published evidence '{evidence.event_id}' "
                f"({evidence.publisher_domain}) to '{stream}': {msg_id}"
            )
            return msg_id
        except Exception as e:
            logger.error(f"Failed to publish evidence to Redis Stream '{stream}': {e}")
            raise

    async def ensure_consumer_group(
        self,
        stream_name: Optional[str] = None,
        group_name: Optional[str] = None,
    ) -> bool:
        """Ensure a consumer group exists on the target stream."""
        stream = stream_name or self.DEFAULT_STREAM
        group = group_name or self.DEFAULT_GROUP
        return await self.client.xgroup_create(stream, group, id_str="0", mkstream=True)

    async def _read_stream_with_recovery(
        self,
        stream: str,
        group: str,
        consumer_name: str,
        count: int = 10,
        block_ms: Optional[int] = 2000,
        from_id: str = ">",
        claim_idle_ms: Optional[int] = None,
    ) -> List[Tuple[str, Dict[str, str]]]:
        """Read entries with XAUTOCLAIM recovery for unacknowledged idle messages."""
        await self.ensure_consumer_group(stream, group)
        entries_to_process: List[Tuple[str, Dict[str, str]]] = []

        if from_id == ">":
            idle_ms = (
                claim_idle_ms
                if claim_idle_ms is not None
                else getattr(settings, "STREAM_CLAIM_IDLE_MS", 60000)
            )
            max_attempts = getattr(settings, "STREAM_MAX_DELIVERY_ATTEMPTS", 3)
            try:
                _, claimed = await self.client.xautoclaim(
                    stream=stream,
                    group=group,
                    consumer=consumer_name,
                    min_idle_time_ms=idle_ms,
                    count=count,
                )
                if claimed:
                    pending_details = await self.client.xpending_detail(
                        stream, group, count=max(count * 2, 50)
                    )
                    delivery_map = {item["id"]: item["deliveries"] for item in pending_details}

                    for msg_id, fields in claimed:
                        deliveries = delivery_map.get(msg_id, 1)
                        if deliveries > max_attempts:
                            logger.error(
                                "Message %s on %s exceeded max delivery attempts (%d > %d), routing to DLQ",
                                msg_id,
                                stream,
                                deliveries,
                                max_attempts,
                            )
                            dlq_fields = dict(fields)
                            dlq_fields["original_stream"] = stream
                            dlq_fields["original_msg_id"] = msg_id
                            dlq_fields["dlq_reason"] = f"Exceeded max delivery attempts ({deliveries})"
                            await self.client.xadd(self.DEFAULT_DEAD_LETTER_STREAM, dlq_fields)
                            await self.client.xack(stream, group, msg_id)
                        else:
                            entries_to_process.append((msg_id, fields))
            except Exception as e:
                logger.warning("Failed during XAUTOCLAIM in stream_service: %s", e)

        remaining_count = count - len(entries_to_process)
        if remaining_count > 0:
            raw_results = await self.client.xreadgroup(
                group=group,
                consumer=consumer_name,
                streams={stream: from_id},
                count=remaining_count,
                block_ms=block_ms if not entries_to_process else 0,
            )
            for _, entries in raw_results:
                entries_to_process.extend(entries)

        return entries_to_process

    async def read_events(
        self,
        group_name: Optional[str] = None,
        consumer_name: str = "worker-1",
        count: int = 10,
        block_ms: Optional[int] = 2000,
        stream_name: Optional[str] = None,
        from_id: str = ">",
        claim_idle_ms: Optional[int] = None,
    ) -> List[Tuple[str, NormalizedIngestionEvent]]:
        """Read a batch of events from the stream for this consumer group."""
        stream = stream_name or self.DEFAULT_STREAM
        group = group_name or self.DEFAULT_GROUP

        raw_entries = await self._read_stream_with_recovery(
            stream=stream,
            group=group,
            consumer_name=consumer_name,
            count=count,
            block_ms=block_ms,
            from_id=from_id,
            claim_idle_ms=claim_idle_ms,
        )

        events: List[Tuple[str, NormalizedIngestionEvent]] = []
        for msg_id, fields in raw_entries:
            try:
                if "data" in fields:
                    data_dict = json.loads(fields["data"])
                    event = NormalizedIngestionEvent.model_validate(data_dict)
                else:
                    event = NormalizedIngestionEvent.model_validate(fields)
                events.append((msg_id, event))
            except Exception as e:
                logger.error(f"Failed to deserialize stream message '{msg_id}': {e}")
                # Acknowledge unrecoverable malformed message so queue does not block
                await self.client.xack(stream, group, msg_id)

        return events

    async def read_observations(
        self,
        group_name: Optional[str] = None,
        consumer_name: str = "worker-obs-1",
        count: int = 10,
        block_ms: Optional[int] = 2000,
        stream_name: Optional[str] = None,
        from_id: str = ">",
        claim_idle_ms: Optional[int] = None,
    ) -> List[Tuple[str, NormalizedObservationEvent]]:
        """Read a batch of observations from the observation stream for this consumer group."""
        stream = stream_name or self.DEFAULT_OBSERVATION_STREAM
        group = group_name or self.DEFAULT_OBSERVATION_GROUP

        raw_entries = await self._read_stream_with_recovery(
            stream=stream,
            group=group,
            consumer_name=consumer_name,
            count=count,
            block_ms=block_ms,
            from_id=from_id,
            claim_idle_ms=claim_idle_ms,
        )

        observations: List[Tuple[str, NormalizedObservationEvent]] = []
        for msg_id, fields in raw_entries:
            try:
                if "data" in fields:
                    data_dict = json.loads(fields["data"])
                    obs = NormalizedObservationEvent.model_validate(data_dict)
                else:
                    obs = NormalizedObservationEvent.model_validate(fields)
                observations.append((msg_id, obs))
            except Exception as e:
                logger.error(
                    f"Failed to deserialize observation stream message '{msg_id}': {e}"
                )
                # Acknowledge unrecoverable malformed message so queue does not block
                await self.client.xack(stream, group, msg_id)

        return observations

    async def read_evidence(
        self,
        group_name: Optional[str] = None,
        consumer_name: str = "worker-ev-1",
        count: int = 10,
        block_ms: Optional[int] = 2000,
        stream_name: Optional[str] = None,
        from_id: str = ">",
        claim_idle_ms: Optional[int] = None,
    ) -> List[Tuple[str, NormalizedEvidenceEvent]]:
        """Read a batch of evidence from the evidence stream for this consumer group."""
        stream = stream_name or self.DEFAULT_EVIDENCE_STREAM
        group = group_name or self.DEFAULT_EVIDENCE_GROUP

        raw_entries = await self._read_stream_with_recovery(
            stream=stream,
            group=group,
            consumer_name=consumer_name,
            count=count,
            block_ms=block_ms,
            from_id=from_id,
            claim_idle_ms=claim_idle_ms,
        )

        evidence_items: List[Tuple[str, NormalizedEvidenceEvent]] = []
        for msg_id, fields in raw_entries:
            try:
                if "data" in fields:
                    data_dict = json.loads(fields["data"])
                    ev = NormalizedEvidenceEvent.model_validate(data_dict)
                else:
                    ev = NormalizedEvidenceEvent.model_validate(fields)
                evidence_items.append((msg_id, ev))
            except Exception as e:
                logger.error(f"Failed to deserialize evidence stream message '{msg_id}': {e}")
                # Acknowledge unrecoverable malformed message so queue does not block
                await self.client.xack(stream, group, msg_id)

        return evidence_items

    async def get_pending_summary(
        self,
        stream_name: Optional[str] = None,
        group_name: Optional[str] = None,
    ) -> dict:
        """Fetch summary of pending unacknowledged messages in the consumer group PEL."""
        stream = stream_name or self.DEFAULT_STREAM
        group = group_name or self.DEFAULT_GROUP
        return await self.client.xpending(stream, group)

    async def ack_event(
        self,
        message_id: str,
        stream_name: Optional[str] = None,
        group_name: Optional[str] = None,
    ) -> bool:
        """Acknowledge a processed stream event."""
        stream = stream_name or self.DEFAULT_STREAM
        group = group_name or self.DEFAULT_GROUP
        ack_count = await self.client.xack(stream, group, message_id)
        return ack_count > 0

    async def ack_observation(
        self,
        message_id: str,
        stream_name: Optional[str] = None,
        group_name: Optional[str] = None,
    ) -> bool:
        """Acknowledge a processed observation stream event."""
        stream = stream_name or self.DEFAULT_OBSERVATION_STREAM
        group = group_name or self.DEFAULT_OBSERVATION_GROUP
        ack_count = await self.client.xack(stream, group, message_id)
        return ack_count > 0

    async def ack_evidence(
        self,
        message_id: str,
        stream_name: Optional[str] = None,
        group_name: Optional[str] = None,
    ) -> bool:
        """Acknowledge a processed evidence stream event."""
        stream = stream_name or self.DEFAULT_EVIDENCE_STREAM
        group = group_name or self.DEFAULT_EVIDENCE_GROUP
        ack_count = await self.client.xack(stream, group, message_id)
        return ack_count > 0


stream_service = StreamService()
