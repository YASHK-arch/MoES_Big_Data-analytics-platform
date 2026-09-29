"""Incident Lifecycle Pipeline Executor.

Orchestrates sequential and dependency-checked execution of all intelligence stages
for an incident, enforcing failure isolation, per-stage state tracking, and atomic persistence.
"""

from __future__ import annotations

import logging
import uuid
from typing import Dict, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.report import WeatherReport
from app.orchestration.dependency_graph import DependencyGraph
from app.orchestration.events import (
    FailureClass,
    OverallReadiness,
    StageExecutionResult,
    StageName,
    StageOutcome,
)
from app.orchestration.handlers import (
    CredibilityStageHandler,
    DuplicateStageHandler,
    EvidenceStageHandler,
    LocationStageHandler,
    ObservationStageHandler,
    StageHandler,
    credibility_stage_handler,
    duplicate_stage_handler,
    evidence_stage_handler,
    location_stage_handler,
    observation_stage_handler,
)
from app.orchestration.models import PipelineOrchestrationState
from app.orchestration.retry_policy import retry_policy
from app.orchestration.state import (
    SUCCESS_OUTCOMES,
    load_orchestration_state,
    update_stage_state,
)

logger = logging.getLogger(__name__)


class IncidentPipeline:
    """Production orchestrator executing the full intelligence lifecycle for an incident."""

    def __init__(
        self,
        location_handler: Optional[LocationStageHandler] = None,
        duplicate_handler: Optional[DuplicateStageHandler] = None,
        evidence_handler: Optional[EvidenceStageHandler] = None,
        observation_handler: Optional[ObservationStageHandler] = None,
        credibility_handler: Optional[CredibilityStageHandler] = None,
    ) -> None:
        self.handlers: Dict[StageName, StageHandler] = {
            StageName.LOCATION: location_handler or location_stage_handler,
            StageName.DUPLICATE: duplicate_handler or duplicate_stage_handler,
            StageName.EVIDENCE: evidence_handler or evidence_stage_handler,
            StageName.OBSERVATION: observation_handler or observation_stage_handler,
            StageName.CREDIBILITY: credibility_handler or credibility_stage_handler,
        }

    async def execute_pipeline(
        self,
        db: AsyncSession,
        incident_id: uuid.UUID,
        commit: bool = True,
        force: bool = False,
    ) -> PipelineOrchestrationState:
        """Run all eligible intelligence stages for target incident with failure isolation."""
        # 1. Fetch target incident without holding long-lived outer transaction lock across all stages
        stmt = select(WeatherReport).where(WeatherReport.id == incident_id)
        res = await db.execute(stmt)
        report = res.scalar_one_or_none()

        if not report:
            logger.warning("Incident %s not found for pipeline execution.", incident_id)
            raise ValueError(f"Incident {incident_id} not found")

        state = load_orchestration_state(report)

        # Idempotency guard: only skip when already completed and overall_readiness is INTELLIGENCE_READY.
        # Incidents with INTELLIGENCE_PARTIAL or PENDING are NOT skipped, allowing workers to retry failed stages.
        if (
            not force
            and report.processing_status == "COMPLETED"
            and state.overall_readiness == OverallReadiness.INTELLIGENCE_READY
        ):
            logger.info(
                "Incident %s is already %s with readiness %s; skipping redundant pipeline execution.",
                incident_id,
                report.processing_status,
                state.overall_readiness.value,
            )
            return state

        stages_order = DependencyGraph.get_pipeline_execution_order()
        current_report: WeatherReport = report

        for stage_name in stages_order:
            # Check prerequisites
            if not DependencyGraph.can_execute_stage(stage_name, state.stages):
                logger.info(
                    "Skipping stage %s for incident %s; prerequisites not met.",
                    stage_name.value,
                    incident_id,
                )
                continue

            current_stage_model = state.stages.get(stage_name)
            # If not forced, skip stages that already succeeded previously with at least 1 completed attempt,
            # unless it's CREDIBILITY which must re-run to incorporate newly retried enrichment stages.
            if (
                not force
                and current_stage_model is not None
                and current_stage_model.attempt > 0
                and current_stage_model.status in SUCCESS_OUTCOMES
                and stage_name != StageName.CREDIBILITY
            ):
                continue

            handler = self.handlers.get(stage_name)
            if not handler:
                continue

            current_attempt = (
                current_stage_model.attempt + 1 if current_stage_model is not None else 1
            )

            # Execute stage with strict failure isolation
            try:
                result = await handler.execute(db=db, report=report)
            except Exception as e:
                logger.error(
                    "Unhandled exception in stage %s for incident %s: %s",
                    stage_name.value,
                    incident_id,
                    e,
                )
                err_class = retry_policy.classify_error(e)
                result = StageExecutionResult(
                    stage_name=stage_name,
                    outcome=(
                        StageOutcome.RETRYABLE_FAILURE
                        if err_class == FailureClass.TRANSIENT
                        else StageOutcome.PERMANENT_FAILURE
                    ),
                    error_class=err_class,
                    error_message=str(e),
                )

            # Re-select locked row to ensure fresh JSONB snapshot before updating
            lock_stmt = (
                select(WeatherReport).where(WeatherReport.id == incident_id).with_for_update()
            )
            lock_res = await db.execute(lock_stmt)
            current_report = lock_res.scalar_one_or_none() or report

            # Update per-stage state on locked row
            state = update_stage_state(
                report=current_report,
                stage_name=stage_name,
                outcome=result.outcome,
                attempt=current_attempt,
                fingerprint=result.fingerprint,
                duration_ms=result.duration_ms,
                error_class=result.error_class,
                error_message=result.error_message,
                summary=result.results_summary,
            )

            # Flush stage state changes
            await db.flush()

        outbox_row = None
        if state.overall_readiness == OverallReadiness.INTELLIGENCE_READY:
            from app.models.outbox import RealtimeOutbox
            from app.services.realtime_service import realtime_service

            existing_outbox_stmt = (
                select(RealtimeOutbox.id)
                .where(
                    RealtimeOutbox.entity_id == str(current_report.id),
                    RealtimeOutbox.event_type == "report.intelligence_ready",
                )
                .limit(1)
            )
            existing_res = await db.execute(existing_outbox_stmt)
            if not existing_res.scalar_one_or_none():
                det_event_id = uuid.uuid5(
                    uuid.NAMESPACE_OID, f"report.intelligence_ready:{current_report.id}"
                )
                outbox_row = realtime_service.stage_intelligence_ready(
                    session=db,
                    report=current_report,
                    credibility_score=float(current_report.credibility_score or 0.0),
                    readiness=state.overall_readiness.value,
                    event_id=det_event_id,
                )

        if commit:
            from sqlalchemy.exc import IntegrityError

            try:
                await db.commit()
                if outbox_row is not None:
                    from app.services.realtime_service import realtime_service

                    await realtime_service.publish_staged_outbox(outbox_row)
            except IntegrityError:
                await db.rollback()
                logger.info(
                    "Concurrent transaction already committed state/outbox for incident %s",
                    incident_id,
                )

        logger.info(
            "Completed intelligence pipeline for incident %s -> readiness: %s",
            incident_id,
            state.overall_readiness.value,
        )
        return state

    async def execute_single_stage(
        self,
        db: AsyncSession,
        incident_id: uuid.UUID,
        stage_name: StageName,
        commit: bool = True,
    ) -> StageExecutionResult:
        """Execute a single targeted stage for an incident and persist its state."""
        stmt = select(WeatherReport).where(WeatherReport.id == incident_id)
        res = await db.execute(stmt)
        report = res.scalar_one_or_none()

        if not report:
            raise ValueError(f"Incident {incident_id} not found")

        state = load_orchestration_state(report)
        handler = self.handlers.get(stage_name)
        if not handler:
            raise ValueError(f"No handler configured for stage {stage_name}")

        current_stage_model = state.stages.get(stage_name)
        current_attempt = current_stage_model.attempt + 1 if current_stage_model is not None else 1

        try:
            result = await handler.execute(db=db, report=report)
        except Exception as e:
            logger.error(
                "Unhandled exception in stage %s for incident %s: %s",
                stage_name.value,
                incident_id,
                e,
            )
            err_class = retry_policy.classify_error(e)
            result = StageExecutionResult(
                stage_name=stage_name,
                outcome=(
                    StageOutcome.RETRYABLE_FAILURE
                    if err_class == FailureClass.TRANSIENT
                    else StageOutcome.PERMANENT_FAILURE
                ),
                error_class=err_class,
                error_message=str(e),
            )

        # Acquire narrow row-level lock on latest DB state to prevent JSONB race overwrites
        lock_stmt = select(WeatherReport).where(WeatherReport.id == incident_id).with_for_update()
        lock_res = await db.execute(lock_stmt)
        locked_report = lock_res.scalar_one_or_none() or report

        update_stage_state(
            report=locked_report,
            stage_name=stage_name,
            outcome=result.outcome,
            attempt=current_attempt,
            fingerprint=result.fingerprint,
            duration_ms=result.duration_ms,
            error_class=result.error_class,
            error_message=result.error_message,
            summary=result.results_summary,
        )

        outbox_row = None
        if stage_name == StageName.CREDIBILITY and result.outcome in (
            StageOutcome.SUCCESS_WITH_RESULTS,
            StageOutcome.SUCCESS_WITH_NO_MATCH,
            StageOutcome.SUCCESS_WITH_INSUFFICIENT_DATA,
        ):
            from app.services.realtime_service import realtime_service

            outbox_row = realtime_service.stage_intelligence_ready(
                session=db,
                report=locked_report,
                credibility_score=float(locked_report.credibility_score or 0.0),
                readiness="INTELLIGENCE_READY",
            )

        if commit:
            await db.commit()
            if outbox_row is not None:
                from app.services.realtime_service import realtime_service

                await realtime_service.publish_staged_outbox(outbox_row)

        return result


incident_pipeline = IncidentPipeline()
