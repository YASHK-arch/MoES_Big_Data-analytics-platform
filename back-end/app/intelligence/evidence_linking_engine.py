import logging
import uuid
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.intelligence.evidence_candidate_generator import (
    EvidenceCandidateGenerator,
    evidence_candidate_generator,
)
from app.intelligence.evidence_scorer import EvidenceScorer, evidence_scorer
from app.intelligence.schemas import (
    EvidenceLinkAssessment,
    EvidenceLinkResult,
    EvidenceRelationship,
)
from app.models.category import EventCategory
from app.models.evidence import EvidenceItem, IncidentEvidenceLink
from app.models.report import WeatherReport
from app.models.source import Source

logger = logging.getLogger(__name__)


class EvidenceLinkingEngine:
    """Production engine for Incident <-> Evidence matching, assessment, and link persistence.

    Safety Guarantees:
    - Never modifies WeatherReport.verification_status.
    - Never merges or deletes incidents or evidence items.
    - Never overwrites human operator decisions (is_human_override = True).
    - Multi-incident independence: Link assessment is pair-specific ((report_id, evidence_id)).
    - Idempotent updates on re-evaluation.
    """

    def __init__(
        self,
        candidate_gen: Optional[EvidenceCandidateGenerator] = None,
        scorer: Optional[EvidenceScorer] = None,
    ) -> None:
        self.candidate_gen = candidate_gen or evidence_candidate_generator
        self.scorer = scorer or evidence_scorer

    async def evaluate_and_link_evidence(
        self,
        db: AsyncSession,
        evidence: EvidenceItem,
    ) -> List[EvidenceLinkResult]:
        """Evaluate an EvidenceItem against candidate incidents and persist valid links."""
        candidates, is_truncated = await self.candidate_gen.get_incident_candidates_for_evidence(
            db=db,
            evidence=evidence,
        )

        results: List[EvidenceLinkResult] = []

        if not candidates:
            return results

        source_type = evidence.evidence_type
        if evidence.source_id:
            src_stmt = select(Source.source_type).where(Source.id == evidence.source_id)
            src_res = await db.execute(src_stmt)
            src_val = src_res.scalar_one_or_none()
            if src_val:
                source_type = src_val

        for incident in candidates:
            cat_code = "OTHER"
            if incident.category_id:
                cat_stmt = select(EventCategory).where(EventCategory.id == incident.category_id)
                cat_res = await db.execute(cat_stmt)
                cat_obj = cat_res.scalar_one_or_none()
                if cat_obj:
                    cat_code = cat_obj.category_code

            assessment = self.scorer.score_link(
                incident_id=incident.id,
                evidence_id=evidence.id,
                incident_title=incident.title,
                incident_desc=incident.description,
                incident_cat=cat_code,
                incident_lat=incident.latitude,
                incident_lon=incident.longitude,
                incident_time=incident.occurred_at,
                incident_loc_name=incident.location_name,
                evidence_title=evidence.title,
                evidence_snippet=evidence.text_snippet,
                evidence_source_type=source_type,
                evidence_pub_time=evidence.published_at or evidence.captured_at,
                evidence_url=evidence.url,
                evidence_domain=evidence.publisher_domain,
            )

            # Persist or update link
            if assessment.relationship_type != EvidenceRelationship.IRRELEVANT:
                link_id = await self._persist_link(
                    db=db,
                    incident_id=incident.id,
                    evidence_id=evidence.id,
                    relationship=assessment.relationship_type,
                    confidence=assessment.overall_score,
                    assessment=assessment,
                )
                results.append(
                    EvidenceLinkResult(
                        link_id=link_id,
                        incident_id=incident.id,
                        evidence_id=evidence.id,
                        relationship_type=assessment.relationship_type,
                        confidence_score=assessment.overall_score,
                        is_linked=True,
                        assessment=assessment,
                    )
                )
            else:
                # If an automated link previously existed for this pair, update it safely
                updated_id = await self._handle_irrelevant_transition(
                    db=db,
                    incident_id=incident.id,
                    evidence_id=evidence.id,
                    assessment=assessment,
                )
                results.append(
                    EvidenceLinkResult(
                        link_id=updated_id,
                        incident_id=incident.id,
                        evidence_id=evidence.id,
                        relationship_type=EvidenceRelationship.IRRELEVANT,
                        confidence_score=assessment.overall_score,
                        is_linked=False,
                        assessment=assessment,
                    )
                )

        return results

    async def evaluate_and_link_report(
        self,
        db: AsyncSession,
        report: WeatherReport,
        candidate_evidence: List[EvidenceItem],
    ) -> List[EvidenceLinkResult]:
        """Evaluate candidate evidence items directly against target incident."""
        results: List[EvidenceLinkResult] = []
        if not candidate_evidence:
            return results

        cat_code = "OTHER"
        if report.category_id:
            cat_stmt = select(EventCategory.category_code).where(EventCategory.id == report.category_id)
            cat_res = await db.execute(cat_stmt)
            cat_val = cat_res.scalar_one_or_none()
            if cat_val:
                cat_code = cat_val
        elif report.reported_category:
            cat_code = report.reported_category

        for ev in candidate_evidence:
            source_type = ev.evidence_type
            if ev.source_id:
                src_stmt = select(Source.source_type).where(Source.id == ev.source_id)
                src_res = await db.execute(src_stmt)
                src_val = src_res.scalar_one_or_none()
                if src_val:
                    source_type = src_val

            assessment = self.scorer.score_link(
                incident_id=report.id,
                evidence_id=ev.id,
                incident_title=report.title,
                incident_desc=report.description,
                incident_cat=cat_code,
                incident_lat=report.latitude,
                incident_lon=report.longitude,
                incident_time=report.occurred_at,
                incident_loc_name=report.location_name,
                evidence_title=ev.title,
                evidence_snippet=ev.text_snippet,
                evidence_source_type=source_type,
                evidence_pub_time=ev.published_at or ev.captured_at,
                evidence_url=ev.url,
                evidence_domain=ev.publisher_domain,
            )

            if assessment.relationship_type != EvidenceRelationship.IRRELEVANT:
                link_id = await self._persist_link(
                    db=db,
                    incident_id=report.id,
                    evidence_id=ev.id,
                    relationship=assessment.relationship_type,
                    confidence=assessment.overall_score,
                    assessment=assessment,
                )
                results.append(
                    EvidenceLinkResult(
                        link_id=link_id,
                        incident_id=report.id,
                        evidence_id=ev.id,
                        relationship_type=assessment.relationship_type,
                        confidence_score=assessment.overall_score,
                        is_linked=True,
                        assessment=assessment,
                    )
                )
            else:
                updated_id = await self._handle_irrelevant_transition(
                    db=db,
                    incident_id=report.id,
                    evidence_id=ev.id,
                    assessment=assessment,
                )
                results.append(
                    EvidenceLinkResult(
                        link_id=updated_id,
                        incident_id=report.id,
                        evidence_id=ev.id,
                        relationship_type=EvidenceRelationship.IRRELEVANT,
                        confidence_score=assessment.overall_score,
                        is_linked=False,
                        assessment=assessment,
                    )
                )

        return results

    async def _persist_link(
        self,
        db: AsyncSession,
        incident_id: uuid.UUID,
        evidence_id: uuid.UUID,
        relationship: EvidenceRelationship,
        confidence: float,
        assessment: EvidenceLinkAssessment,
    ) -> uuid.UUID:
        """Idempotently persist or update an IncidentEvidenceLink record with override safety."""
        stmt = select(IncidentEvidenceLink).where(
            IncidentEvidenceLink.report_id == incident_id,
            IncidentEvidenceLink.evidence_id == evidence_id,
        )
        res = await db.execute(stmt)
        existing_link = res.scalar_one_or_none()

        explanation_dict = {
            "overall_score": assessment.overall_score,
            "explanation": assessment.explanation,
            "signals": assessment.signals.model_dump(),
            "engine_version": assessment.engine_version,
            "policy_version": assessment.policy_version,
            "semantic_method": assessment.semantic_method,
            "assessed_at": assessment.assessed_at.isoformat(),
            "is_human_override": False,
        }

        if existing_link:
            # Human override protection: never overwrite an operator's manual decision
            existing_meta = existing_link.match_explanation or {}
            if existing_meta.get("is_human_override") is True:
                existing_meta["last_automated_assessment"] = explanation_dict
                existing_meta["last_evaluated_at"] = assessment.assessed_at.isoformat()
                existing_link.match_explanation = existing_meta
                await db.flush()
                return existing_link.id

            existing_link.link_role = relationship.value
            existing_link.confidence_score = confidence
            existing_link.match_explanation = explanation_dict
            await db.flush()
            return existing_link.id

        new_link = IncidentEvidenceLink(
            report_id=incident_id,
            evidence_id=evidence_id,
            link_role=relationship.value,
            confidence_score=confidence,
            match_explanation=explanation_dict,
        )
        db.add(new_link)
        await db.flush()
        return new_link.id

    async def _handle_irrelevant_transition(
        self,
        db: AsyncSession,
        incident_id: uuid.UUID,
        evidence_id: uuid.UUID,
        assessment: EvidenceLinkAssessment,
    ) -> Optional[uuid.UUID]:
        """Update existing automated link if re-evaluation transitions it to IRRELEVANT."""
        stmt = select(IncidentEvidenceLink).where(
            IncidentEvidenceLink.report_id == incident_id,
            IncidentEvidenceLink.evidence_id == evidence_id,
        )
        res = await db.execute(stmt)
        existing_link = res.scalar_one_or_none()

        if not existing_link:
            return None

        existing_meta = existing_link.match_explanation or {}
        explanation_dict = {
            "overall_score": assessment.overall_score,
            "explanation": assessment.explanation,
            "signals": assessment.signals.model_dump(),
            "engine_version": assessment.engine_version,
            "policy_version": assessment.policy_version,
            "semantic_method": assessment.semantic_method,
            "assessed_at": assessment.assessed_at.isoformat(),
            "is_human_override": existing_meta.get("is_human_override", False),
        }

        # Do not overwrite human decision
        if existing_meta.get("is_human_override") is True:
            existing_meta["last_automated_assessment"] = explanation_dict
            existing_meta["last_evaluated_at"] = assessment.assessed_at.isoformat()
            existing_link.match_explanation = existing_meta
            await db.flush()
            return existing_link.id

        existing_link.link_role = EvidenceRelationship.IRRELEVANT.value
        existing_link.confidence_score = 0.0
        existing_link.match_explanation = explanation_dict
        await db.flush()
        return existing_link.id


evidence_linking_engine = EvidenceLinkingEngine()
