"""Data Retention and Cold-Storage Archival Service (C2).

Periodically prunes historical records older than a configurable retention window (default 6 days)
across weather_reports, weather_observations, and evidence_items.
Verified weather reports are copied to weather_reports_archive before deletion to preserve
historical analytics and audit integrity.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.archive import WeatherReportArchive
from app.models.corroboration import IncidentObservationCorroboration
from app.models.duplicate import DuplicateCluster, DuplicateMember
from app.models.evidence import EvidenceItem, IncidentEvidenceLink
from app.models.media import ReportMedia
from app.models.observation import WeatherObservation
from app.models.report import WeatherReport
from app.models.verification import VerificationEvent

logger = logging.getLogger(__name__)


@dataclass
class RetentionResult:
    retention_days: int
    cutoff_date: datetime
    dry_run: bool
    reports_archived: int = 0
    reports_deleted: int = 0
    observations_deleted: int = 0
    evidence_deleted: int = 0
    duration_ms: float = 0.0
    errors: List[str] = field(default_factory=list)


class DataRetentionService:
    """Service to execute retention and archival cycles across database tables."""

    def __init__(self, batch_size: Optional[int] = None) -> None:
        self.batch_size = batch_size or settings.DATA_RETENTION_BATCH_SIZE

    async def run_retention_cycle(
        self,
        session: AsyncSession,
        retention_days: Optional[int] = None,
        dry_run: bool = False,
    ) -> RetentionResult:
        """Execute a retention cycle.

        Args:
            session: Asynchronous database session.
            retention_days: Retention horizon in days (defaults to settings.DATA_RETENTION_DAYS).
            dry_run: When True, queries and counts records without writing or deleting.

        Returns:
            RetentionResult with detailed metrics.
        """
        t0 = time.perf_counter()
        days = retention_days if retention_days is not None else settings.DATA_RETENTION_DAYS
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)

        result = RetentionResult(
            retention_days=days,
            cutoff_date=cutoff,
            dry_run=dry_run,
        )

        logger.info(
            "Starting data retention cycle (retention_days=%d, cutoff=%s, dry_run=%s)",
            days,
            cutoff.isoformat(),
            dry_run,
        )

        try:
            # ─────────────────────────────────────────────────────────────────
            # 1. Archive VERIFIED WeatherReports
            # ─────────────────────────────────────────────────────────────────
            verified_stmt = (
                select(WeatherReport)
                .where(
                    WeatherReport.occurred_at < cutoff,
                    WeatherReport.verification_status == "VERIFIED",
                )
                .order_by(WeatherReport.occurred_at.asc())
            )
            verified_res = await session.execute(verified_stmt)
            verified_reports = list(verified_res.scalars().all())

            if not dry_run and verified_reports:
                for chunk_start in range(0, len(verified_reports), self.batch_size):
                    chunk = verified_reports[chunk_start : chunk_start + self.batch_size]
                    archive_records = [
                        {
                            "id": r.id,
                            "tracking_id": r.tracking_id,
                            "source_id": r.source_id,
                            "external_id": r.external_id,
                            "category_id": r.category_id,
                            "reported_category": r.reported_category,
                            "severity": r.severity,
                            "title": r.title,
                            "description": r.description,
                            "location_name": r.location_name,
                            "geom": r.geom,
                            "latitude": r.latitude,
                            "longitude": r.longitude,
                            "occurred_at": r.occurred_at,
                            "processing_status": r.processing_status,
                            "verification_status": r.verification_status,
                            "credibility_score": r.credibility_score,
                            "credibility_explanation": r.credibility_explanation,
                            "text_embedding": r.text_embedding,
                            "raw_payload": r.raw_payload,
                            "original_created_at": r.created_at,
                        }
                        for r in chunk
                    ]
                    insert_stmt = (
                        pg_insert(WeatherReportArchive)
                        .values(archive_records)
                        .on_conflict_do_nothing(index_elements=["id"])
                    )
                    await session.execute(insert_stmt)
                    await session.flush()

            result.reports_archived = len(verified_reports)

            # ─────────────────────────────────────────────────────────────────
            # 2. Delete Expired WeatherReports (All expired reports)
            # ─────────────────────────────────────────────────────────────────
            expired_reports_stmt = (
                select(WeatherReport.id)
                .where(WeatherReport.occurred_at < cutoff)
            )
            expired_rep_res = await session.execute(expired_reports_stmt)
            expired_rep_ids = list(expired_rep_res.scalars().all())

            if not dry_run and expired_rep_ids:
                for chunk_start in range(0, len(expired_rep_ids), self.batch_size):
                    chunk_ids = expired_rep_ids[chunk_start : chunk_start + self.batch_size]

                    # Clean up dependent child records not covered by automatic DB cascade
                    await session.execute(
                        delete(VerificationEvent).where(VerificationEvent.report_id.in_(chunk_ids))
                    )
                    await session.execute(
                        delete(DuplicateMember).where(DuplicateMember.report_id.in_(chunk_ids))
                    )
                    await session.execute(
                        delete(DuplicateCluster).where(DuplicateCluster.primary_report_id.in_(chunk_ids))
                    )
                    await session.execute(
                        delete(ReportMedia).where(ReportMedia.report_id.in_(chunk_ids))
                    )
                    await session.execute(
                        delete(IncidentEvidenceLink).where(IncidentEvidenceLink.report_id.in_(chunk_ids))
                    )
                    await session.execute(
                        delete(IncidentObservationCorroboration).where(
                            IncidentObservationCorroboration.report_id.in_(chunk_ids)
                        )
                    )
                    await session.execute(
                        delete(WeatherReport).where(WeatherReport.id.in_(chunk_ids))
                    )
                    await session.flush()

            result.reports_deleted = len(expired_rep_ids)

            # ─────────────────────────────────────────────────────────────────
            # 3. Delete Expired WeatherObservations
            # ─────────────────────────────────────────────────────────────────
            expired_obs_stmt = (
                select(WeatherObservation.id)
                .where(WeatherObservation.observed_at < cutoff)
            )
            expired_obs_res = await session.execute(expired_obs_stmt)
            expired_obs_ids = list(expired_obs_res.scalars().all())

            if not dry_run and expired_obs_ids:
                for chunk_start in range(0, len(expired_obs_ids), self.batch_size):
                    chunk_obs_ids = expired_obs_ids[chunk_start : chunk_start + self.batch_size]
                    await session.execute(
                        delete(IncidentObservationCorroboration).where(
                            IncidentObservationCorroboration.observation_id.in_(chunk_obs_ids)
                        )
                    )
                    await session.execute(
                        delete(WeatherObservation).where(WeatherObservation.id.in_(chunk_obs_ids))
                    )
                    await session.flush()

            result.observations_deleted = len(expired_obs_ids)

            # ─────────────────────────────────────────────────────────────────
            # 4. Delete Expired EvidenceItems
            # ─────────────────────────────────────────────────────────────────
            effective_pub_time = func.coalesce(EvidenceItem.published_at, EvidenceItem.captured_at)
            expired_evi_stmt = (
                select(EvidenceItem.id)
                .where(effective_pub_time < cutoff)
            )
            expired_evi_res = await session.execute(expired_evi_stmt)
            expired_evi_ids = list(expired_evi_res.scalars().all())

            if not dry_run and expired_evi_ids:
                for chunk_start in range(0, len(expired_evi_ids), self.batch_size):
                    chunk_evi_ids = expired_evi_ids[chunk_start : chunk_start + self.batch_size]
                    await session.execute(
                        delete(IncidentEvidenceLink).where(
                            IncidentEvidenceLink.evidence_id.in_(chunk_evi_ids)
                        )
                    )
                    await session.execute(
                        delete(EvidenceItem).where(EvidenceItem.id.in_(chunk_evi_ids))
                    )
                    await session.flush()

            result.evidence_deleted = len(expired_evi_ids)

        except Exception as e:
            logger.error("Data retention cycle encountered error: %s", e, exc_info=True)
            result.errors.append(str(e))
            raise

        finally:
            result.duration_ms = round((time.perf_counter() - t0) * 1000, 2)
            logger.info(
                "Data retention cycle completed in %.2fms (archived=%d, deleted_reports=%d, "
                "deleted_obs=%d, deleted_evidence=%d, dry_run=%s)",
                result.duration_ms,
                result.reports_archived,
                result.reports_deleted,
                result.observations_deleted,
                result.evidence_deleted,
                result.dry_run,
            )

        return result


retention_service = DataRetentionService()
