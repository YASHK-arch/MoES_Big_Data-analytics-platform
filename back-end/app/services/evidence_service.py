import logging
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ingestion.schemas import NormalizedEvidenceEvent
from app.models.evidence import EvidenceItem
from app.models.outbox import RealtimeOutbox
from app.models.source import Source
from app.services.realtime_service import RealtimeService, realtime_service

logger = logging.getLogger(__name__)


class EvidenceService:
    """Service handling persistence, idempotency, and retrieval of secondary evidence items."""

    def __init__(self, realtime_svc: Optional[RealtimeService] = None) -> None:
        self.realtime_svc = realtime_svc or realtime_service

    async def get_or_create_source(
        self,
        session: AsyncSession,
        source_code: str = "GDELT_DOC",
        name: Optional[str] = None,
        source_type: Optional[str] = None,
        base_trust_score: Optional[float] = None,
    ) -> Source:
        """Fetch existing evidence source or register a new one idempotently."""
        normalized_code = source_code.strip().upper()
        stmt = select(Source).where(Source.source_code == normalized_code)
        result = await session.execute(stmt)
        source = result.scalar_one_or_none()

        if source is not None:
            if base_trust_score is not None:
                source.base_trust_score = base_trust_score
            else:
                from app.ingestion.registry import adapter_registry

                registered = adapter_registry.get(normalized_code)
                if registered:
                    source.base_trust_score = registered.base_trust_score
            return source

        resolved_trust = base_trust_score
        resolved_name = name
        resolved_type = source_type or "RSS"

        from app.ingestion.registry import adapter_registry

        registered = adapter_registry.get(normalized_code)
        if registered:
            if resolved_trust is None:
                resolved_trust = registered.base_trust_score
            if not resolved_name:
                resolved_name = registered.source_name
            resolved_type = registered.source_type

        source = Source(
            source_code=normalized_code,
            name=resolved_name or f"Evidence Source {normalized_code}",
            source_type=resolved_type,
            base_trust_score=resolved_trust if resolved_trust is not None else 0.70,
            is_active=True,
        )
        session.add(source)
        await session.flush()
        logger.info(f"Registered evidence source: {normalized_code} (trust: {source.base_trust_score})")

        return source

    async def ingest_normalized_evidence(
        self,
        session: AsyncSession,
        event: NormalizedEvidenceEvent,
        stage_outbox: bool = True,
    ) -> EvidenceItem:
        """Persist or update an external evidence item idempotently via (source_id, external_id)."""
        source = await self.get_or_create_source(
            session=session,
            source_code=event.source_code,
        )

        stmt = select(EvidenceItem).where(
            EvidenceItem.source_id == source.id,
            EvidenceItem.external_id == event.external_id,
        )
        result = await session.execute(stmt)
        existing: Optional[EvidenceItem] = result.scalar_one_or_none()

        orch_outbox_row: Optional[RealtimeOutbox] = None

        if existing:
            existing.title = event.title
            existing.url = event.url
            existing.publisher_domain = event.publisher_domain
            existing.language = event.language
            existing.published_at = event.published_at
            existing.text_snippet = event.text_snippet
            existing.sha256_hash = event.sha256_hash
            existing.raw_payload = event.raw_payload

            if stage_outbox:
                orch_outbox_row = self.realtime_svc.stage_evidence_orchestration_trigger(
                    session=session,
                    evidence=existing,
                )

            await session.commit()
            await session.refresh(existing)

            if orch_outbox_row is not None:
                await self.realtime_svc.publish_staged_outbox(orch_outbox_row)

            logger.debug(
                f"Updated existing evidence item '{existing.external_id}' "
                f"({existing.publisher_domain})"
            )
            return existing

        evidence = EvidenceItem(
            source_id=source.id,
            external_id=event.external_id,
            evidence_type=event.evidence_type,
            title=event.title,
            url=event.url,
            publisher_domain=event.publisher_domain,
            language=event.language,
            published_at=event.published_at,
            captured_at=event.captured_at,
            text_snippet=event.text_snippet,
            sha256_hash=event.sha256_hash,
            raw_payload=event.raw_payload,
        )
        session.add(evidence)
        await session.flush()

        if stage_outbox:
            orch_outbox_row = self.realtime_svc.stage_evidence_orchestration_trigger(
                session=session,
                evidence=evidence,
            )

        await session.commit()
        await session.refresh(evidence)

        if orch_outbox_row is not None:
            await self.realtime_svc.publish_staged_outbox(orch_outbox_row)

        logger.info(
            f"Persisted new evidence item '{evidence.external_id}' ({evidence.publisher_domain})"
        )
        return evidence


evidence_service = EvidenceService()
