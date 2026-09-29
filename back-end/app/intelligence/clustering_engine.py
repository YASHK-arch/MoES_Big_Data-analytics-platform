import logging
import uuid
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.intelligence.candidate_generator import CandidateGenerator, candidate_generator
from app.intelligence.duplicate_scorer import DuplicateScorer, duplicate_scorer
from app.intelligence.schemas import (
    ClusterAssignmentResult,
    DuplicateAssessment,
    DuplicateDecision,
)
from app.models.category import EventCategory
from app.models.duplicate import DuplicateCluster, DuplicateMember
from app.models.report import WeatherReport

logger = logging.getLogger(__name__)


class IncidentClusteringEngine:
    """Production clustering engine for semantic duplicate assessment and cluster management.

    Separation of Concerns:
    - Automated duplicate clustering attaches duplicate memberships without overwriting
      human verification status (`verification_status`).
    - Primary selection is deterministic based on occurrence time, credibility, and UUID.
    """

    def __init__(
        self,
        candidate_gen: Optional[CandidateGenerator] = None,
        scorer: Optional[DuplicateScorer] = None,
    ) -> None:
        self.candidate_gen = candidate_gen or candidate_generator
        self.scorer = scorer or duplicate_scorer

    @staticmethod
    def select_primary_report(rep_a: WeatherReport, rep_b: WeatherReport) -> WeatherReport:
        """Deterministic primary selection policy: earliest occurrence -> credibility -> UUID."""
        # 1. Earliest reliable occurrence
        if rep_a.occurred_at != rep_b.occurred_at:
            return rep_a if rep_a.occurred_at < rep_b.occurred_at else rep_b

        # 2. Higher credibility score
        if rep_a.credibility_score != rep_b.credibility_score:
            return rep_a if rep_a.credibility_score > rep_b.credibility_score else rep_b

        # 3. Deterministic UUID ordering
        return rep_a if str(rep_a.id) < str(rep_b.id) else rep_b

    async def evaluate_and_cluster(
        self,
        db: AsyncSession,
        report: WeatherReport,
    ) -> ClusterAssignmentResult:
        """Assess a report for duplication and maintain duplicate clusters without data loss."""
        # 1. Retrieve candidates via PostGIS spatial & temporal gates
        query_res = await self.candidate_gen.get_candidates(
            db=db,
            report_id=report.id,
            geom=report.geom,
            occurred_at=report.occurred_at,
        )

        candidates = query_res.candidates
        is_truncated = query_res.is_truncated
        cand_count = len(candidates)

        if not candidates:
            report.processing_status = "PROCESSED"
            await db.flush()
            return ClusterAssignmentResult(
                report_id=report.id,
                decision=DuplicateDecision.DISTINCT,
                cluster_id=None,
                is_primary=False,
                matched_report_id=None,
                candidate_count=0,
                is_truncated=False,
                assessment=None,
            )

        # Get incoming report category code
        cat_code_a: Optional[str] = None
        if report.category_id:
            cat_stmt = select(EventCategory).where(EventCategory.id == report.category_id)
            cat_res = await db.execute(cat_stmt)
            cat_obj = cat_res.scalar_one_or_none()
            if cat_obj and cat_obj.category_code:
                cat_code_a = cat_obj.category_code
        if not cat_code_a and report.reported_category and report.reported_category.strip():
            cat_code_a = report.reported_category.strip()
        if not cat_code_a:
            cat_code_a = "OTHER"

        # 2. Evaluate pairwise assessments against all candidates
        best_assessment: Optional[DuplicateAssessment] = None
        matched_report: Optional[WeatherReport] = None

        for cand in candidates:
            cat_code_b: Optional[str] = None
            if cand.category_id:
                cand_cat_stmt = select(EventCategory).where(EventCategory.id == cand.category_id)
                cand_cat_res = await db.execute(cand_cat_stmt)
                cand_cat_obj = cand_cat_res.scalar_one_or_none()
                if cand_cat_obj and cand_cat_obj.category_code:
                    cat_code_b = cand_cat_obj.category_code
            if not cat_code_b and cand.reported_category and cand.reported_category.strip():
                cat_code_b = cand.reported_category.strip()
            if not cat_code_b:
                cat_code_b = "OTHER"

            assessment = self.scorer.score_pair(
                report_a_id=report.id,
                report_b_id=cand.id,
                title_a=report.title,
                title_b=cand.title,
                desc_a=report.description,
                desc_b=cand.description,
                cat_a=cat_code_a,
                cat_b=cat_code_b,
                lat_a=report.latitude,
                lon_a=report.longitude,
                lat_b=cand.latitude,
                lon_b=cand.longitude,
                time_a=report.occurred_at,
                time_b=cand.occurred_at,
                loc_name_a=report.location_name,
                loc_name_b=cand.location_name,
                vec_a=report.text_embedding,
                vec_b=cand.text_embedding,
            )

            if best_assessment is None or assessment.overall_score > best_assessment.overall_score:
                best_assessment = assessment
                matched_report = cand

        if best_assessment is None or matched_report is None:
            return ClusterAssignmentResult(
                report_id=report.id,
                decision=DuplicateDecision.DISTINCT,
                cluster_id=None,
                is_primary=False,
                matched_report_id=None,
                candidate_count=cand_count,
                is_truncated=is_truncated,
                assessment=None,
            )

        # 3. Handle Confirmed DUPLICATE
        if best_assessment.decision == DuplicateDecision.DUPLICATE:
            cluster_id = await self._attach_to_cluster(
                db=db,
                new_report=report,
                reference_report=matched_report,
                similarity_score=best_assessment.overall_score,
            )
            # Update processing status without mutating human verification status
            report.processing_status = "PROCESSED"
            await db.flush()

            logger.info(
                f"Report {report.id} clustered with {matched_report.id} "
                f"(score={best_assessment.overall_score:.2f}) -> Cluster {cluster_id}"
            )
            return ClusterAssignmentResult(
                report_id=report.id,
                decision=DuplicateDecision.DUPLICATE,
                cluster_id=cluster_id,
                is_primary=False,
                matched_report_id=matched_report.id,
                candidate_count=cand_count,
                is_truncated=is_truncated,
                assessment=best_assessment,
            )

        # 4. Handle POSSIBLE_MATCH
        if best_assessment.decision == DuplicateDecision.POSSIBLE_MATCH:
            report.processing_status = "PROCESSED"
            await db.flush()
            logger.info(
                f"Report {report.id} is POSSIBLE_MATCH with {matched_report.id} "
                f"(score={best_assessment.overall_score:.2f}) - flagged for review"
            )
            return ClusterAssignmentResult(
                report_id=report.id,
                decision=DuplicateDecision.POSSIBLE_MATCH,
                cluster_id=None,
                is_primary=False,
                matched_report_id=matched_report.id,
                candidate_count=cand_count,
                is_truncated=is_truncated,
                assessment=best_assessment,
            )

        # 5. Handle DISTINCT
        report.processing_status = "PROCESSED"
        await db.flush()
        return ClusterAssignmentResult(
            report_id=report.id,
            decision=DuplicateDecision.DISTINCT,
            cluster_id=None,
            is_primary=False,
            matched_report_id=None,
            candidate_count=cand_count,
            is_truncated=is_truncated,
            assessment=best_assessment,
        )

    async def _attach_to_cluster(
        self,
        db: AsyncSession,
        new_report: WeatherReport,
        reference_report: WeatherReport,
        similarity_score: float,
    ) -> uuid.UUID:
        """Idempotently attach duplicate report to DuplicateCluster using primary selection."""
        # Check if new report is already associated with any cluster
        existing_new_member_stmt = select(DuplicateMember).where(
            DuplicateMember.report_id == new_report.id
        )
        existing_new_member_res = await db.execute(existing_new_member_stmt)
        existing_new_member = existing_new_member_res.scalar_one_or_none()
        if existing_new_member:
            return existing_new_member.cluster_id

        # Check if reference report is already primary of a cluster
        cluster_stmt = select(DuplicateCluster).where(
            DuplicateCluster.primary_report_id == reference_report.id
        )
        cluster_res = await db.execute(cluster_stmt)
        cluster = cluster_res.scalar_one_or_none()

        # If not primary, check if reference report is a member of an existing cluster
        if not cluster:
            member_stmt = select(DuplicateMember).where(
                DuplicateMember.report_id == reference_report.id
            )
            member_res = await db.execute(member_stmt)
            existing_member = member_res.scalar_one_or_none()
            if existing_member:
                c_stmt = select(DuplicateCluster).where(
                    DuplicateCluster.id == existing_member.cluster_id
                )
                c_res = await db.execute(c_stmt)
                cluster = c_res.scalar_one_or_none()

        if cluster:
            if new_report.id == cluster.primary_report_id:
                return cluster.id
            # Check if new report is already member
            check_stmt = select(DuplicateMember).where(
                DuplicateMember.cluster_id == cluster.id,
                DuplicateMember.report_id == new_report.id,
            )
            check_res = await db.execute(check_stmt)
            if not check_res.scalar_one_or_none():
                member = DuplicateMember(
                    cluster_id=cluster.id,
                    report_id=new_report.id,
                    similarity_score=similarity_score,
                )
                db.add(member)
                cluster.member_count += 1
                await db.flush()
            return cluster.id
        else:
            # Deterministically choose primary anchor
            primary_rep = self.select_primary_report(reference_report, new_report)
            member_rep = new_report if primary_rep.id == reference_report.id else reference_report

            new_cluster = DuplicateCluster(
                primary_report_id=primary_rep.id,
                cluster_radius_meters=self.scorer.max_radius,
                centroid_geom=primary_rep.geom,
                member_count=2,
            )
            db.add(new_cluster)
            await db.flush()

            member = DuplicateMember(
                cluster_id=new_cluster.id,
                report_id=member_rep.id,
                similarity_score=similarity_score,
            )
            db.add(member)
            await db.flush()
            return new_cluster.id


clustering_engine = IncidentClusteringEngine()
