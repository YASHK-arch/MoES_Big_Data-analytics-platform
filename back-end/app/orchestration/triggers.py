"""Targeted incremental triggers for intelligence updates.

Guarantees:
- New evidence/observations trigger targeted credibility recomputation only for affected reports.
- No whole-database table scans or N^2 iterations.
- Human verification updates do not trigger automated machine credibility re-scoring.
"""

from __future__ import annotations

import logging
import uuid
from datetime import timedelta
from typing import List, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.intelligence.credibility_engine import credibility_engine
from app.intelligence.evidence_linking_engine import evidence_linking_engine
from app.intelligence.observation_corroboration_engine import observation_corroboration_engine
from app.models.evidence import EvidenceItem
from app.models.observation import WeatherObservation
from app.models.report import WeatherReport
from app.orchestration.events import (
    StageName,
)
from app.orchestration.incident_pipeline import incident_pipeline
from app.orchestration.models import PipelineOrchestrationState

logger = logging.getLogger(__name__)


async def on_incident_ingested(
    db: AsyncSession,
    incident_id: uuid.UUID,
    commit: bool = True,
    force: bool = False,
) -> PipelineOrchestrationState:
    """Trigger full forward intelligence pipeline for a newly ingested incident."""
    logger.info("Triggering full pipeline for new incident %s", incident_id)
    return await incident_pipeline.execute_pipeline(
        db=db, incident_id=incident_id, commit=commit, force=force
    )


async def on_evidence_ingested(
    db: AsyncSession,
    evidence_id: uuid.UUID,
    commit: bool = True,
) -> List[uuid.UUID]:
    """Targeted trigger: Match candidate incidents for new evidence and recompute credibility.

    Only incidents that are successfully matched and linked have their credibility re-evaluated.
    """
    stmt = select(EvidenceItem).where(EvidenceItem.id == evidence_id)
    res = await db.execute(stmt)
    evidence = res.scalar_one_or_none()

    if not evidence:
        logger.warning("EvidenceItem %s not found for targeted trigger.", evidence_id)
        return []

    # 1. Match and link candidate incidents
    link_results = await evidence_linking_engine.evaluate_and_link_evidence(
        db=db, evidence=evidence
    )
    affected_ids: List[uuid.UUID] = []

    # 2. Targeted credibility recomputation only for affected reports
    for lr in link_results:
        if lr.is_linked:
            affected_ids.append(lr.incident_id)
            await incident_pipeline.execute_single_stage(
                db=db,
                incident_id=lr.incident_id,
                stage_name=StageName.CREDIBILITY,
                commit=False,
            )

    if commit:
        await db.commit()

    logger.info(
        "Evidence %s ingested -> targeted credibility updated for %d incidents.",
        evidence_id,
        len(affected_ids),
    )
    return affected_ids


async def on_observation_ingested(
    db: AsyncSession,
    observation_id: uuid.UUID,
    commit: bool = True,
) -> List[uuid.UUID]:
    """Targeted trigger: Match candidate incidents for new observation and recompute credibility.

    Only incidents with active corroborations have their credibility re-evaluated.
    """
    stmt = select(WeatherObservation).where(WeatherObservation.id == observation_id)
    res = await db.execute(stmt)
    obs = res.scalar_one_or_none()

    if not obs:
        logger.warning("WeatherObservation %s not found for targeted trigger.", observation_id)
        return []

    # 1. Spatial/temporal query for candidate incidents near observation station
    policy = observation_corroboration_engine.scorer.policy
    time_window = timedelta(hours=policy.time_window_hours)
    time_min = obs.observed_at - time_window
    time_max = obs.observed_at + time_window

    from geoalchemy2 import Geography

    cand_stmt = (
        select(WeatherReport)
        .join(WeatherObservation, WeatherObservation.id == obs.id)
        .where(
            WeatherReport.geom.isnot(None),
            WeatherReport.occurred_at >= time_min,
            WeatherReport.occurred_at <= time_max,
            func.ST_DWithin(
                func.cast(WeatherReport.geom, Geography),
                func.cast(WeatherObservation.geom, Geography),
                policy.spatial_radius_meters,
            ),
        )
        .order_by(WeatherReport.occurred_at.desc())
        .limit(50)
    )

    cand_res = await db.execute(cand_stmt)
    candidates = list(cand_res.scalars().all())

    affected_ids: List[uuid.UUID] = []
    for inc in candidates:
        corr_res = await observation_corroboration_engine.evaluate_single_pair(
            db=db,
            incident=inc,
            observation=obs,
        )
        if corr_res.is_persisted:
            affected_ids.append(inc.id)
            await incident_pipeline.execute_single_stage(
                db=db,
                incident_id=inc.id,
                stage_name=StageName.CREDIBILITY,
                commit=False,
            )

    if commit:
        await db.commit()

    logger.info(
        "Observation %s ingested -> targeted credibility updated for %d incidents.",
        observation_id,
        len(affected_ids),
    )
    return affected_ids


async def on_duplicate_cluster_updated(
    db: AsyncSession,
    cluster_id: uuid.UUID,
) -> List[uuid.UUID]:
    """Targeted trigger: Recompute credibility for all member reports in an affected cluster."""
    results = await credibility_engine.recompute_for_cluster(db=db, cluster_id=cluster_id)
    return [r.incident_id for r in results]


async def on_human_verification_updated(
    db: AsyncSession,
    report_id: uuid.UUID,
    new_status: str,
) -> Optional[WeatherReport]:
    """Human verification trigger: Updates operator state and records audit log.

    CRITICAL: Does NOT trigger machine credibility recomputation.
    """
    stmt = select(WeatherReport).where(WeatherReport.id == report_id)
    res = await db.execute(stmt)
    report = res.scalar_one_or_none()

    if not report:
        return None

    # Report verification status is updated by authorized operators, machine score untouched
    report.verification_status = new_status.upper()
    await db.commit()
    logger.info(
        "Human verification updated for report %s -> status: %s (machine credibility untouched).",
        report_id,
        new_status,
    )
    return report


async def on_physical_observation_updated(
    db: AsyncSession,
    incident_id: uuid.UUID,
    commit: bool = True,
) -> bool:
    """Late-arriving physical weather observation triggers credibility recompute and outbox/SSE."""
    from app.intelligence.physical_corroboration.service import (
        physical_corroboration_service,
    )
    from app.orchestration.handlers import StageName
    from app.orchestration.incident_pipeline import incident_pipeline

    stmt = select(WeatherReport).where(WeatherReport.id == incident_id)
    res = await db.execute(stmt)
    report = res.scalar_one_or_none()
    if not report:
        return False

    phys_record = await physical_corroboration_service.corroborate_incident(
        db=db, report=report, force_run=True
    )
    if phys_record is not None:
        physical_corroboration_service.stage_corroboration_event(
            db=db, report=report, record=phys_record
        )

    # Trigger credibility stage recomputation
    await incident_pipeline.execute_single_stage(
        db=db,
        incident_id=incident_id,
        stage_name=StageName.CREDIBILITY,
        commit=False,
    )

    if commit:
        await db.commit()
    return True
