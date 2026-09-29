"""Typed stage handlers and event registry for intelligence orchestration.

Coordinates frozen intelligence components without duplicating scoring or clustering logic.
Guarantees compare-before-write stale result protection, failure isolation, and idempotency.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from typing import Optional, Protocol

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.intelligence.clustering_engine import IncidentClusteringEngine, clustering_engine
from app.intelligence.credibility_collector import CredibilityCollector, credibility_collector
from app.intelligence.credibility_engine import CredibilityEngine, credibility_engine
from app.intelligence.credibility_explanation_builder import (
    CredibilityExplanationBuilder,
    credibility_explanation_builder,
)
from app.intelligence.credibility_scorer import CredibilityScorer, credibility_scorer
from app.intelligence.evidence_candidate_generator import (
    EvidenceCandidateGenerator,
    evidence_candidate_generator,
)
from app.intelligence.evidence_linking_engine import EvidenceLinkingEngine, evidence_linking_engine
from app.intelligence.evidence_scorer import EvidenceScorer, evidence_scorer
from app.intelligence.observation_corroboration_engine import (
    ObservationCorroborationEngine,
    observation_corroboration_engine,
)
from app.intelligence.resolver import LocationResolver, location_resolver
from app.intelligence.schemas import IncidentCredibilityInputs
from app.models.evidence import EvidenceItem
from app.models.report import WeatherReport
from app.orchestration.events import (
    StageExecutionResult,
    StageName,
    StageOutcome,
)
from app.orchestration.retry_policy import retry_policy

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Fingerprint Helper Utilities
# ─────────────────────────────────────────────────────────────────────────────


def compute_credibility_fingerprint(inputs: IncidentCredibilityInputs) -> str:
    """Compute deterministic SHA256 fingerprint for all credibility inputs.

    Includes:
    - Incident core fields + source base trust
    - Duplicate cluster member count
    - Sorted evidence link parameters (provenance, confidence, role, derived lineage)
    - Sorted observation corroboration parameters (station, score, relationship, trend points)
    - Negative contradictions
    Volatile wall-clock timestamps (e.g. now()) are strictly excluded.
    """
    evi_tuples = sorted(
        [
            (
                g.provenance_key,
                round(g.max_confidence, 4),
                round(g.role_weight, 4),
                g.article_count,
                g.source_family.value,
                g.is_derived_lineage,
            )
            for g in inputs.evidence_groups
        ]
    )

    obs_tuples = sorted(
        [
            (
                s.station_key,
                round(s.corroboration_score, 4),
                round(s.relationship_weight, 4),
                s.source_family.value,
                s.points_count,
            )
            for s in inputs.observation_stations
        ]
    )

    contra_tuples = sorted(
        [
            (
                c.signal_source_key,
                round(c.contradiction_score, 4),
                c.is_diagnostic,
                c.is_physical_sensor,
            )
            for c in inputs.negative_contradictions
        ]
    )

    fingerprint_dict = {
        "incident_id": str(inputs.incident_id),
        "source_code": inputs.source_code,
        "source_base_trust": round(inputs.source_base_trust, 4),
        "origin_family": inputs.origin_family.value,
        "has_coordinates": inputs.has_coordinates,
        "has_timestamp": inputs.has_timestamp,
        "has_location_name": inputs.has_location_name,
        "has_description": inputs.has_description,
        "has_category": inputs.has_category,
        "cluster_member_count": inputs.cluster_member_count,
        "evidence_groups": evi_tuples,
        "observation_stations": obs_tuples,
        "negative_contradictions": contra_tuples,
    }

    serialized = json.dumps(fingerprint_dict, sort_keys=True)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


# ─────────────────────────────────────────────────────────────────────────────
# Stage Handler Protocol & Concrete Handlers
# ─────────────────────────────────────────────────────────────────────────────


class StageHandler(Protocol):
    async def execute(self, db: AsyncSession, report: WeatherReport) -> StageExecutionResult: ...


class LocationStageHandler:
    """Wraps LocationResolver to resolve geographic points and administrative entities."""

    def __init__(self, resolver: Optional[LocationResolver] = None) -> None:
        self.resolver = resolver or location_resolver

    async def execute(self, db: AsyncSession, report: WeatherReport) -> StageExecutionResult:
        t0 = time.perf_counter()
        try:
            full_text = f"{report.title} {report.description or ''}".strip()
            res = self.resolver.resolve(
                text=full_text,
                latitude=report.latitude,
                longitude=report.longitude,
                location_name=report.location_name,
            )

            duration_ms = round((time.perf_counter() - t0) * 1000, 2)

            # Soft dependency check: determine outcome
            if res.latitude is not None and res.longitude is not None:
                outcome = StageOutcome.SUCCESS_WITH_RESULTS
            elif res.city or res.place_name:
                outcome = StageOutcome.SUCCESS_WITH_RESULTS
            else:
                outcome = StageOutcome.SUCCESS_WITH_INSUFFICIENT_DATA

            # Raw input fingerprint for location
            fp_payload = f"{report.title}|{report.description}|{report.latitude}|{report.longitude}"
            fp = hashlib.sha256(fp_payload.encode("utf-8")).hexdigest()

            return StageExecutionResult(
                stage_name=StageName.LOCATION,
                outcome=outcome,
                fingerprint=fp,
                duration_ms=duration_ms,
                results_summary={
                    "resolution_method": res.resolution_method.value,
                    "confidence": res.confidence,
                    "resolution_status": res.resolution_status.value,
                    "latitude": res.latitude,
                    "longitude": res.longitude,
                },
            )
        except Exception as e:
            duration_ms = round((time.perf_counter() - t0) * 1000, 2)
            logger.error("LocationStageHandler failed for report %s: %s", report.id, e)
            return StageExecutionResult(
                stage_name=StageName.LOCATION,
                outcome=StageOutcome.RETRYABLE_FAILURE,
                duration_ms=duration_ms,
                error_class=retry_policy.classify_error(e),
                error_message=str(e),
            )


class DuplicateStageHandler:
    """Wraps IncidentClusteringEngine to evaluate semantic duplicates and manage clusters."""

    def __init__(self, clustering: Optional[IncidentClusteringEngine] = None) -> None:
        self.clustering = clustering or clustering_engine

    async def execute(self, db: AsyncSession, report: WeatherReport) -> StageExecutionResult:
        t0 = time.perf_counter()
        try:
            cluster_res = await self.clustering.evaluate_and_cluster(db=db, report=report)
            duration_ms = round((time.perf_counter() - t0) * 1000, 2)

            is_clustered = cluster_res.cluster_id is not None
            outcome = (
                StageOutcome.SUCCESS_WITH_RESULTS
                if is_clustered
                else StageOutcome.SUCCESS_WITH_NO_MATCH
            )

            fp_payload = (
                f"{report.id}|{report.latitude}|{report.longitude}|"
                f"{report.occurred_at}|{report.title}|{cluster_res.cluster_id}"
            )
            fp = hashlib.sha256(fp_payload.encode("utf-8")).hexdigest()

            # When a new report clusters with an existing report, trigger targeted credibility update
            # on the matched report so its crowd corroboration factor reflects the new cluster size.
            # Enforce consistent lock ordering (by ascending report ID) to prevent deadlocks
            # between concurrent pipelines clustering with each other.
            if is_clustered and cluster_res.matched_report_id:
                try:
                    from app.orchestration.incident_pipeline import incident_pipeline

                    first_id, second_id = (
                        (report.id, cluster_res.matched_report_id)
                        if report.id < cluster_res.matched_report_id
                        else (cluster_res.matched_report_id, report.id)
                    )
                    await db.execute(
                        select(WeatherReport.id)
                        .where(WeatherReport.id.in_([first_id, second_id]))
                        .order_by(WeatherReport.id)
                        .with_for_update()
                    )

                    await incident_pipeline.execute_single_stage(
                        db=db,
                        incident_id=cluster_res.matched_report_id,
                        stage_name=StageName.CREDIBILITY,
                        commit=False,
                    )
                except Exception as ex:
                    logger.warning(
                        "Failed to update credibility for matched cluster incident %s: %s",
                        cluster_res.matched_report_id,
                        ex,
                    )

            return StageExecutionResult(
                stage_name=StageName.DUPLICATE,
                outcome=outcome,
                fingerprint=fp,
                duration_ms=duration_ms,
                results_summary={
                    "is_clustered": is_clustered,
                    "cluster_id": str(cluster_res.cluster_id) if cluster_res.cluster_id else None,
                    "decision": cluster_res.decision.value,
                    "candidate_count": cluster_res.candidate_count,
                },
            )
        except Exception as e:
            duration_ms = round((time.perf_counter() - t0) * 1000, 2)
            logger.error("DuplicateStageHandler failed for report %s: %s", report.id, e)
            return StageExecutionResult(
                stage_name=StageName.DUPLICATE,
                outcome=StageOutcome.RETRYABLE_FAILURE,
                duration_ms=duration_ms,
                error_class=retry_policy.classify_error(e),
                error_message=str(e),
            )


class EvidenceStageHandler:
    """Discovers matching digital evidence items and manages IncidentEvidenceLinks."""

    def __init__(
        self,
        candidate_gen: Optional[EvidenceCandidateGenerator] = None,
        scorer: Optional[EvidenceScorer] = None,
        linking_engine: Optional[EvidenceLinkingEngine] = None,
    ) -> None:
        self.candidate_gen = candidate_gen or evidence_candidate_generator
        self.scorer = scorer or evidence_scorer
        self.linking_engine = linking_engine or evidence_linking_engine

    async def execute(self, db: AsyncSession, report: WeatherReport) -> StageExecutionResult:
        t0 = time.perf_counter()
        try:
            # Query candidate evidence items for this report
            # (Matches published within temporal window and spatial radius)
            time_min = report.occurred_at - self.candidate_gen.max_window
            time_max = report.occurred_at + self.candidate_gen.max_window

            stmt = (
                select(EvidenceItem)
                .where(
                    EvidenceItem.published_at >= time_min,
                    EvidenceItem.published_at <= time_max,
                )
                .limit(self.candidate_gen.default_limit)
            )

            res = await db.execute(stmt)
            candidate_evidence = list(res.scalars().all())

            links_count = 0
            for ev in candidate_evidence:
                link_results = await self.linking_engine.evaluate_and_link_evidence(
                    db=db, evidence=ev
                )
                for lr in link_results:
                    if lr.incident_id == report.id and lr.is_linked:
                        links_count += 1

            duration_ms = round((time.perf_counter() - t0) * 1000, 2)
            outcome = (
                StageOutcome.SUCCESS_WITH_RESULTS
                if links_count > 0
                else StageOutcome.SUCCESS_WITH_NO_MATCH
            )

            fp_payload = f"{report.id}|{len(candidate_evidence)}|{links_count}"
            fp = hashlib.sha256(fp_payload.encode("utf-8")).hexdigest()

            return StageExecutionResult(
                stage_name=StageName.EVIDENCE,
                outcome=outcome,
                fingerprint=fp,
                duration_ms=duration_ms,
                results_summary={
                    "candidates_evaluated": len(candidate_evidence),
                    "active_links_count": links_count,
                },
            )
        except Exception as e:
            duration_ms = round((time.perf_counter() - t0) * 1000, 2)
            logger.error("EvidenceStageHandler failed for report %s: %s", report.id, e)
            return StageExecutionResult(
                stage_name=StageName.EVIDENCE,
                outcome=StageOutcome.RETRYABLE_FAILURE,
                duration_ms=duration_ms,
                error_class=retry_policy.classify_error(e),
                error_message=str(e),
            )


class ObservationStageHandler:
    """Wraps ObservationCorroborationEngine to match sensor stations and trend telemetry."""

    def __init__(self, corroboration: Optional[ObservationCorroborationEngine] = None) -> None:
        self.corroboration = corroboration or observation_corroboration_engine

    async def execute(self, db: AsyncSession, report: WeatherReport) -> StageExecutionResult:
        t0 = time.perf_counter()
        try:
            results = await self.corroboration.evaluate_and_corroborate(db=db, incident=report)
            duration_ms = round((time.perf_counter() - t0) * 1000, 2)

            outcome = (
                StageOutcome.SUCCESS_WITH_RESULTS
                if len(results) > 0
                else StageOutcome.SUCCESS_WITH_NO_MATCH
            )

            fp_payload = f"{report.id}|{len(results)}"
            fp = hashlib.sha256(fp_payload.encode("utf-8")).hexdigest()

            return StageExecutionResult(
                stage_name=StageName.OBSERVATION,
                outcome=outcome,
                fingerprint=fp,
                duration_ms=duration_ms,
                results_summary={
                    "corroborations_count": len(results),
                    "relationships": [r.relationship_type.value for r in results],
                },
            )
        except Exception as e:
            duration_ms = round((time.perf_counter() - t0) * 1000, 2)
            logger.error("ObservationStageHandler failed for report %s: %s", report.id, e)
            return StageExecutionResult(
                stage_name=StageName.OBSERVATION,
                outcome=StageOutcome.RETRYABLE_FAILURE,
                duration_ms=duration_ms,
                error_class=retry_policy.classify_error(e),
                error_message=str(e),
            )


class CredibilityStageHandler:
    """Evaluates multi-source credibility with compare-before-write stale result protection."""

    def __init__(
        self,
        collector: Optional[CredibilityCollector] = None,
        scorer: Optional[CredibilityScorer] = None,
        builder: Optional[CredibilityExplanationBuilder] = None,
        engine: Optional[CredibilityEngine] = None,
    ) -> None:
        self.collector = collector or credibility_collector
        self.scorer = scorer or credibility_scorer
        self.builder = builder or credibility_explanation_builder
        self.engine = engine or credibility_engine

    async def execute(self, db: AsyncSession, report: WeatherReport) -> StageExecutionResult:
        t0 = time.perf_counter()
        try:
            # 1. Collect inputs & capture initial fingerprint F1
            inputs = await self.collector.collect_inputs(db=db, incident_id=report.id)
            if not inputs:
                return StageExecutionResult(
                    stage_name=StageName.CREDIBILITY,
                    outcome=StageOutcome.PERMANENT_FAILURE,
                    error_message=f"Incident {report.id} not found for credibility scoring",
                )

            f1 = compute_credibility_fingerprint(inputs)

            # 2. Pure deterministic mathematical scoring (outside long transaction)
            signals = self.scorer.score_incident(inputs)
            assessment = self.builder.build_assessment(
                incident_id=report.id,
                inputs=inputs,
                signals=signals,
            )

            # 3. Compare-before-write: verify current DB state F2 == F1 before persisting
            latest_inputs = await self.collector.collect_inputs(db=db, incident_id=report.id)
            if not latest_inputs:
                f2 = None
            else:
                f2 = compute_credibility_fingerprint(latest_inputs)

            if f1 != f2:
                logger.warning(
                    "Stale credibility calculation for %s (%s != %s). Aborting write.",
                    report.id,
                    f1[:8],
                    str(f2)[:8] if f2 else "None",
                )
                duration_ms = round((time.perf_counter() - t0) * 1000, 2)
                return StageExecutionResult(
                    stage_name=StageName.CREDIBILITY,
                    outcome=StageOutcome.SKIPPED_STALE,
                    fingerprint=f1,
                    duration_ms=duration_ms,
                    error_message="Input state changed during computation; skipped stale write.",
                )

            # 4. Atomic persistence into WeatherReport entity
            report.credibility_score = signals.final_credibility_score
            report.credibility_explanation = assessment.model_dump(mode="json")
            await db.flush()

            duration_ms = round((time.perf_counter() - t0) * 1000, 2)
            return StageExecutionResult(
                stage_name=StageName.CREDIBILITY,
                outcome=StageOutcome.SUCCESS_WITH_RESULTS,
                fingerprint=f1,
                duration_ms=duration_ms,
                results_summary={
                    "credibility_score": signals.final_credibility_score,
                    "applied_cap": signals.applied_cap,
                    "independent_family_count": assessment.provenance.independent_family_count,
                },
            )
        except Exception as e:
            duration_ms = round((time.perf_counter() - t0) * 1000, 2)
            logger.error("CredibilityStageHandler failed for report %s: %s", report.id, e)
            return StageExecutionResult(
                stage_name=StageName.CREDIBILITY,
                outcome=StageOutcome.RETRYABLE_FAILURE,
                duration_ms=duration_ms,
                error_class=retry_policy.classify_error(e),
                error_message=str(e),
            )


# Default singleton instances
location_stage_handler = LocationStageHandler()
duplicate_stage_handler = DuplicateStageHandler()
evidence_stage_handler = EvidenceStageHandler()
observation_stage_handler = ObservationStageHandler()
credibility_stage_handler = CredibilityStageHandler()
