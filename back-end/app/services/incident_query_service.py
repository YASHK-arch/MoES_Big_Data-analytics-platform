"""Production query service for operational incident intelligence resources.

Provides bounded, index-optimized data retrieval for incident lists, details,
sub-resources, verification queues, and geospatial layers.
"""

from __future__ import annotations

import math
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from geoalchemy2 import Geography
from geoalchemy2.functions import (
    ST_AsGeoJSON,
    ST_Distance,
    ST_DWithin,
    ST_MakeEnvelope,
    ST_MakePoint,
    ST_SetSRID,
)
from sqlalchemy import and_, case, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.intelligence.schemas import EvidenceRelationship, ObservationRelationship
from app.models.category import EventCategory
from app.models.corroboration import IncidentObservationCorroboration
from app.models.duplicate import DuplicateCluster, DuplicateMember
from app.models.evidence import EvidenceItem, IncidentEvidenceLink
from app.models.forecast import ForecastAdvisory
from app.models.observation import WeatherObservation
from app.models.report import WeatherReport
from app.orchestration.events import OverallReadiness
from app.orchestration.state import load_orchestration_state
from app.schemas.analytics import (
    AnalyticsRegionalData,
    AnalyticsTrendBucket,
    AnalyticsTrendData,
    CategoryDistributionItem,
    DashboardSummaryData,
    DiurnalDistributionItem,
    RegionalDistributionItem,
    SeverityBreakdown,
    VerificationBreakdown,
)
from app.schemas.credibility import IncidentCredibilityData
from app.schemas.duplicate import ClusterMemberSummary, IncidentClusterDetailData
from app.schemas.evidence import IncidentEvidenceItemData
from app.schemas.geo import (
    GeoJSONFeatureCollection,
    GeoJSONGeometryPoint,
    GeoJSONIncidentFeature,
    GeoJSONIncidentProperties,
)
from app.schemas.incident import (
    IncidentCorroborationCounts,
    IncidentCredibilitySummary,
    IncidentDetailOperator,
    IncidentDetailPublic,
    IncidentIntelligenceSummary,
    IncidentLocationResponse,
    IncidentSummaryResponse,
    IncidentVerificationSummary,
)
from app.schemas.intelligence import IncidentIntelligenceData, StageStatusSummary
from app.schemas.observation import (
    IncidentObservationItemData,
    ObservationMetricSummary,
)
from app.schemas.report import (
    CategoryDetail,
    MediaDetail,
    SeverityType,
    VerificationEventDetail,
)
from app.services.storage import storage_service

ID_PATTERN = re.compile(r"^[a-zA-Z0-9_-]{3,64}$")


class IncidentQueryService:
    """Read-optimized service layer for incident intelligence resources."""

    @staticmethod
    def _safe_get_media_url(m: Any) -> str:
        """Safely retrieve media presigned URL without raising exceptions or leaking secrets."""
        try:
            return storage_service.get_media_url(
                storage_key=m.storage_key,
                bucket_name=m.storage_bucket,
            )
        except Exception:
            return ""

    @staticmethod
    def _extract_category(report: WeatherReport) -> CategoryDetail:
        """Extract canonical category detail from joined model or reported field."""
        if report.category is not None:
            return CategoryDetail(
                code=report.category.category_code,
                title=report.category.title,
            )
        code = report.reported_category or "OTHER"
        return CategoryDetail(code=code, title=code.replace("_", " ").title())

    @staticmethod
    def _extract_readiness(report: WeatherReport) -> OverallReadiness:
        """Extract derived intelligence readiness from raw_payload or fallback to PENDING."""
        if report.raw_payload and isinstance(report.raw_payload, dict):
            orch = report.raw_payload.get("orchestration", {})
            if isinstance(orch, dict) and "overall_readiness" in orch:
                try:
                    return OverallReadiness(orch["overall_readiness"])
                except (ValueError, TypeError):
                    pass
        if report.processing_status == "COMPLETED":
            return OverallReadiness.INTELLIGENCE_READY
        if report.processing_status == "PARTIAL_INTELLIGENCE":
            return OverallReadiness.INTELLIGENCE_PARTIAL
        if report.processing_status == "FAILED":
            return OverallReadiness.INTELLIGENCE_FAILED
        return OverallReadiness.INTELLIGENCE_PENDING

    @staticmethod
    def _extract_severity(severity_str: Optional[str]) -> SeverityType:
        """Coerce database severity string into strict SeverityType literal."""
        if severity_str in ("LOW", "MODERATE", "HIGH", "SEVERE"):
            return severity_str  # type: ignore[return-value]
        return "MODERATE"

    async def list_incidents(
        self,
        session: AsyncSession,
        page: int = 1,
        page_size: int = 20,
        category: Optional[str] = None,
        severity: Optional[str] = None,
        verification_status: Optional[str] = None,
        min_credibility: Optional[float] = None,
        max_credibility: Optional[float] = None,
        readiness: Optional[str] = None,
        from_date: Optional[datetime] = None,
        to_date: Optional[datetime] = None,
        bbox: Optional[Tuple[float, float, float, float]] = None,
        sort_by: str = "occurred_at",
        sort_order: str = "desc",
    ) -> Tuple[List[IncidentSummaryResponse], int, int, bool, bool]:
        """List and filter weather incidents with bounded deterministic pagination."""
        stmt = select(WeatherReport).options(
            selectinload(WeatherReport.category),
            selectinload(WeatherReport.media),
        )
        count_stmt = select(func.count(WeatherReport.id))

        filters: List[Any] = []

        if category:
            clean_cat = category.strip().upper()
            filters.append(
                (WeatherReport.reported_category == clean_cat)
                | (
                    WeatherReport.category_id.in_(
                        select(EventCategory.id).where(EventCategory.category_code == clean_cat)
                    )
                )
            )

        if severity:
            filters.append(WeatherReport.severity == severity.strip().upper())

        if verification_status:
            statuses = [s.strip().upper() for s in verification_status.split(",") if s.strip()]
            if statuses:
                filters.append(WeatherReport.verification_status.in_(statuses))

        if min_credibility is not None:
            filters.append(WeatherReport.credibility_score >= min_credibility)

        if max_credibility is not None:
            filters.append(WeatherReport.credibility_score <= max_credibility)

        if readiness:
            clean_readiness = readiness.strip().upper()
            filters.append(
                func.jsonb_extract_path_text(
                    WeatherReport.raw_payload, "orchestration", "overall_readiness"
                )
                == clean_readiness
            )

        if from_date is not None:
            filters.append(WeatherReport.occurred_at >= from_date)

        if to_date is not None:
            filters.append(WeatherReport.occurred_at <= to_date)

        if bbox:
            min_lon, min_lat, max_lon, max_lat = bbox
            envelope = ST_MakeEnvelope(min_lon, min_lat, max_lon, max_lat, 4326)
            filters.append(WeatherReport.geom.isnot(None))
            filters.append(envelope.ST_Intersects(WeatherReport.geom))

        if filters:
            stmt = stmt.where(*filters)
            count_stmt = count_stmt.where(*filters)

        total_records_res = await session.execute(count_stmt)
        total_records = total_records_res.scalar() or 0

        # Sorting logic with mandatory tiebreaker id DESC
        sort_col: Any = WeatherReport.occurred_at
        if sort_by == "credibility_score":
            sort_col = WeatherReport.credibility_score
        elif sort_by == "created_at":
            sort_col = WeatherReport.created_at

        if sort_order.lower() == "asc":
            stmt = stmt.order_by(sort_col.asc(), WeatherReport.id.desc())
        else:
            stmt = stmt.order_by(sort_col.desc(), WeatherReport.id.desc())

        offset = (page - 1) * page_size
        stmt = stmt.offset(offset).limit(page_size)

        res = await session.execute(stmt)
        reports = res.scalars().all()

        total_pages = math.ceil(total_records / page_size) if total_records > 0 else 1
        has_next = page < total_pages
        has_prev = page > 1

        summaries = [
            IncidentSummaryResponse(
                id=r.id,
                tracking_id=r.tracking_id,
                title=r.title,
                category=self._extract_category(r),
                severity=self._extract_severity(r.severity),
                location=IncidentLocationResponse(
                    name=r.location_name,
                    latitude=r.latitude,
                    longitude=r.longitude,
                ),
                occurred_at=r.occurred_at,
                verification_status=r.verification_status,
                credibility_score=r.credibility_score,
                credibility_reason=r.credibility_reason,
                credibility_explanation=r.credibility_explanation,
                readiness=self._extract_readiness(r),
                media_count=len(r.media) if r.media else 0,
                created_at=r.created_at,
            )
            for r in reports
        ]

        return summaries, total_records, total_pages, has_next, has_prev

    async def get_incident_detail(
        self,
        session: AsyncSession,
        identifier: str,
        is_operator: bool = False,
    ) -> Optional[IncidentDetailPublic | IncidentDetailOperator]:
        """Fetch operational incident detail with bounded aggregate summaries."""
        clean_id = identifier.strip()
        stmt = select(WeatherReport).options(
            selectinload(WeatherReport.category),
            selectinload(WeatherReport.media),
        )
        if is_operator:
            stmt = stmt.options(selectinload(WeatherReport.verification_events))

        try:
            val_uuid = uuid.UUID(clean_id)
            stmt = stmt.where(WeatherReport.id == val_uuid)
        except ValueError:
            stmt = stmt.where(WeatherReport.tracking_id == clean_id)

        res = await session.execute(stmt)
        report = res.scalar_one_or_none()
        if not report:
            return None

        # Aggregate counts via fast subqueries
        evi_count_stmt = select(func.count(IncidentEvidenceLink.id)).where(
            IncidentEvidenceLink.report_id == report.id
        )
        obs_count_stmt = select(func.count(IncidentObservationCorroboration.id)).where(
            IncidentObservationCorroboration.report_id == report.id
        )

        evi_res = await session.execute(evi_count_stmt)
        evidence_count = evi_res.scalar() or 0

        obs_res = await session.execute(obs_count_stmt)
        observation_count = obs_res.scalar() or 0

        # Cluster membership check
        clus_stmt = (
            select(DuplicateMember, DuplicateCluster)
            .join(DuplicateCluster, DuplicateMember.cluster_id == DuplicateCluster.id)
            .where(DuplicateMember.report_id == report.id)
        )
        clus_res = await session.execute(clus_stmt)
        clus_row = clus_res.first()

        cluster_size = 1
        is_rep = True
        if clus_row:
            dm, dc = clus_row
            cluster_size = dc.member_count
            is_rep = dm.report_id == dc.primary_report_id

        # Media items with safe presigned URLs
        media_items: List[MediaDetail] = []
        if report.media:
            for m in report.media:
                media_items.append(
                    MediaDetail(
                        id=m.id,
                        media_type=m.media_type,
                        url=self._safe_get_media_url(m),
                        sha256_hash=m.sha256_hash,
                    )
                )

        # Location details
        loc_resp = IncidentLocationResponse(
            name=report.location_name,
            latitude=report.latitude,
            longitude=report.longitude,
            resolution_status="RESOLVED" if report.latitude and report.longitude else "UNRESOLVED",
        )

        # Credibility summary
        cred_exp = None
        pos_drivers: List[str] = []
        neg_drivers: List[str] = []
        flags: List[str] = []
        if report.credibility_explanation and isinstance(report.credibility_explanation, dict):
            cred_exp = report.credibility_explanation.get("explanation_text") or report.credibility_explanation.get("explanation")
            pos_drivers = report.credibility_explanation.get("positive_drivers") or []
            neg_drivers = report.credibility_explanation.get("negative_drivers") or []
            flags = report.credibility_explanation.get("uncertainty_flags") or []
        elif isinstance(report.credibility_explanation, str):
            cred_exp = report.credibility_explanation

        cred_resp = IncidentCredibilitySummary(
            score=report.credibility_score,
            is_machine_assessed=True,
            explanation=cred_exp,
            reason=report.credibility_reason,
            positive_drivers=pos_drivers,
            negative_drivers=neg_drivers,
            uncertainty_flags=flags,
        )

        # Verification summary
        ver_resp = IncidentVerificationSummary(
            status=report.verification_status,
            is_human_verified=report.verification_status in ("VERIFIED", "REJECTED"),
        )

        # Intelligence status summary
        orch_state = load_orchestration_state(report)
        intel_resp = IncidentIntelligenceSummary(
            overall_readiness=orch_state.overall_readiness,
            last_computed_at=orch_state.last_updated_at,
        )

        counts = IncidentCorroborationCounts(
            evidence_count=evidence_count,
            observation_count=observation_count,
            duplicate_cluster_size=cluster_size,
            is_cluster_representative=is_rep,
        )

        if not is_operator:
            return IncidentDetailPublic(
                id=report.id,
                tracking_id=report.tracking_id,
                title=report.title,
                description=report.description,
                category=self._extract_category(report),
                severity=self._extract_severity(report.severity),
                location=loc_resp,
                occurred_at=report.occurred_at,
                credibility=cred_resp,
                verification=ver_resp,
                intelligence_status=intel_resp,
                summaries=counts,
                media=media_items,
                created_at=report.created_at,
            )

        # Operator model includes audit events and orchestration stage details
        history_items: List[VerificationEventDetail] = []
        if getattr(report, "verification_events", None):
            sorted_events = sorted(
                report.verification_events,
                key=lambda e: e.created_at,
                reverse=True,
            )
            for ev in sorted_events:
                history_items.append(
                    VerificationEventDetail(
                        id=ev.id,
                        previous_status=ev.previous_status,
                        new_status=ev.new_status,
                        notes=ev.notes,
                        action_metadata=ev.action_metadata,
                        created_at=ev.created_at,
                        reviewer_name="Authorized Reviewer",
                    )
                )

        stage_data: Dict[str, Any] = {}
        for s_name, s_model in orch_state.stages.items():
            stage_data[s_name.value] = s_model.model_dump()

        return IncidentDetailOperator(
            id=report.id,
            tracking_id=report.tracking_id,
            title=report.title,
            description=report.description,
            category=self._extract_category(report),
            severity=self._extract_severity(report.severity),
            location=loc_resp,
            occurred_at=report.occurred_at,
            credibility=cred_resp,
            verification=ver_resp,
            intelligence_status=intel_resp,
            summaries=counts,
            media=media_items,
            created_at=report.created_at,
            verification_history=history_items,
            orchestration_stages=stage_data,
        )

    async def get_incident_credibility(
        self,
        session: AsyncSession,
        identifier: str,
    ) -> Optional[IncidentCredibilityData]:
        """Fetch canonical credibility assessment breakdown."""
        clean_id = identifier.strip()
        stmt = select(WeatherReport)
        try:
            val_uuid = uuid.UUID(clean_id)
            stmt = stmt.where(WeatherReport.id == val_uuid)
        except ValueError:
            stmt = stmt.where(WeatherReport.tracking_id == clean_id)

        res = await session.execute(stmt)
        report = res.scalar_one_or_none()
        if not report:
            return None

        exp_data = report.credibility_explanation or {}
        if not isinstance(exp_data, dict):
            exp_data = {}

        explanation_text = exp_data.get(
            "explanation_text",
            f"Machine-assessed credibility score of {report.credibility_score:.4f}.",
        )
        pos_drivers = exp_data.get("positive_drivers", [])
        neg_drivers = exp_data.get("negative_drivers", [])
        flags = exp_data.get("uncertainty_flags", [])

        # Label derivation
        score = report.credibility_score
        label = "LOW_CREDIBILITY"
        if score >= 0.85:
            label = "VERY_HIGH_CREDIBILITY"
        elif score >= 0.70:
            label = "HIGH_CREDIBILITY"
        elif score >= 0.45:
            label = "MODERATE_CREDIBILITY"

        now = datetime.now(timezone.utc)

        # 1. Primary source: credibility_explanation["assessed_at"]
        calc_time: Optional[datetime] = None
        assessed_at_raw = exp_data.get("assessed_at")
        if isinstance(assessed_at_raw, str):
            try:
                calc_time = datetime.fromisoformat(assessed_at_raw.replace("Z", "+00:00"))
            except (ValueError, TypeError):
                calc_time = None
        elif isinstance(assessed_at_raw, datetime):
            calc_time = assessed_at_raw

        # 2. Fallbacks: report.updated_at -> report.created_at -> now
        if calc_time is None:
            calc_time = report.updated_at or report.created_at or now

        if calc_time.tzinfo is None:
            calc_time = calc_time.replace(tzinfo=timezone.utc)

        return IncidentCredibilityData(
            incident_id=report.id,
            score=score,
            is_machine_assessed=True,
            label=label,
            base_trust_prior=exp_data.get("source_prior", 0.50),
            engine_version=exp_data.get("engine_version", "v1"),
            policy_version=exp_data.get("policy_version", "v1"),
            explanation_text=explanation_text,
            positive_drivers=pos_drivers,
            negative_drivers=neg_drivers,
            uncertainty_flags=flags,
            last_calculated_at=calc_time,
        )

    async def get_incident_intelligence_status(
        self,
        session: AsyncSession,
        identifier: str,
    ) -> Optional[IncidentIntelligenceData]:
        """Fetch orchestration status and per-stage execution telemetry."""
        clean_id = identifier.strip()
        stmt = select(WeatherReport)
        try:
            val_uuid = uuid.UUID(clean_id)
            stmt = stmt.where(WeatherReport.id == val_uuid)
        except ValueError:
            stmt = stmt.where(WeatherReport.tracking_id == clean_id)

        res = await session.execute(stmt)
        report = res.scalar_one_or_none()
        if not report:
            return None

        orch = load_orchestration_state(report)
        stages_summary: Dict[str, StageStatusSummary] = {}
        for s_name, s_model in orch.stages.items():
            stages_summary[s_name.value] = StageStatusSummary(
                status=s_model.status,
                attempt=s_model.attempt,
                duration_ms=s_model.duration_ms,
                error_message=s_model.error_message,
                summary=s_model.summary,
            )

        return IncidentIntelligenceData(
            incident_id=report.id,
            overall_readiness=orch.overall_readiness,
            last_successful_stage=orch.last_successful_stage.value
            if orch.last_successful_stage
            else None,
            last_computed_at=orch.last_updated_at,
            stages=stages_summary,
        )

    async def get_incident_evidence(
        self,
        session: AsyncSession,
        identifier: str,
        page: int = 1,
        page_size: int = 20,
    ) -> Tuple[Optional[List[IncidentEvidenceItemData]], int, int, bool, bool]:
        """Fetch paginated linked digital evidence items for an incident."""
        clean_id = identifier.strip()
        stmt = select(WeatherReport.id)
        try:
            val_uuid = uuid.UUID(clean_id)
            stmt = stmt.where(WeatherReport.id == val_uuid)
        except ValueError:
            stmt = stmt.where(WeatherReport.tracking_id == clean_id)

        res = await session.execute(stmt)
        report_id = res.scalar_one_or_none()
        if not report_id:
            return None, 0, 0, False, False

        count_stmt = select(func.count(IncidentEvidenceLink.id)).where(
            IncidentEvidenceLink.report_id == report_id
        )
        count_res = await session.execute(count_stmt)
        total_records = count_res.scalar() or 0

        offset = (page - 1) * page_size
        links_stmt = (
            select(IncidentEvidenceLink, EvidenceItem)
            .join(EvidenceItem, IncidentEvidenceLink.evidence_id == EvidenceItem.id)
            .where(IncidentEvidenceLink.report_id == report_id)
            .order_by(IncidentEvidenceLink.confidence_score.desc(), IncidentEvidenceLink.id.desc())
            .offset(offset)
            .limit(page_size)
        )
        links_res = await session.execute(links_stmt)
        rows = links_res.all()

        items: List[IncidentEvidenceItemData] = []
        for link, ev in rows:
            # Map canonical relationship enum
            rel = EvidenceRelationship.SUPPORTING
            try:
                rel = EvidenceRelationship(link.link_role)
            except ValueError:
                pass

            items.append(
                IncidentEvidenceItemData(
                    link_id=link.id,
                    evidence_id=ev.id,
                    evidence_type=ev.evidence_type,
                    publisher_domain=ev.publisher_domain,
                    title=ev.title,
                    text_snippet=ev.text_snippet[:300] if ev.text_snippet else "",
                    published_at=ev.published_at,
                    relationship=rel,
                    confidence_score=link.confidence_score,
                    provenance_group=ev.publisher_domain,
                    url=ev.url,
                    is_human_override=getattr(link, "is_human_override", False),
                )
            )

        total_pages = math.ceil(total_records / page_size) if total_records > 0 else 1
        has_next = page < total_pages
        has_prev = page > 1

        return items, total_records, total_pages, has_next, has_prev

    async def get_incident_observations(
        self,
        session: AsyncSession,
        identifier: str,
        page: int = 1,
        page_size: int = 20,
    ) -> Tuple[Optional[List[IncidentObservationItemData]], int, int, bool, bool]:
        """Fetch paginated physical observation corroborations for an incident."""
        clean_id = identifier.strip()
        stmt = select(WeatherReport.id)
        try:
            val_uuid = uuid.UUID(clean_id)
            stmt = stmt.where(WeatherReport.id == val_uuid)
        except ValueError:
            stmt = stmt.where(WeatherReport.tracking_id == clean_id)

        res = await session.execute(stmt)
        report_id = res.scalar_one_or_none()
        if not report_id:
            return None, 0, 0, False, False

        count_stmt = select(func.count(IncidentObservationCorroboration.id)).where(
            IncidentObservationCorroboration.report_id == report_id
        )
        count_res = await session.execute(count_stmt)
        total_records = count_res.scalar() or 0

        offset = (page - 1) * page_size
        cor_stmt = (
            select(IncidentObservationCorroboration, WeatherObservation)
            .join(
                WeatherObservation,
                IncidentObservationCorroboration.observation_id == WeatherObservation.id,
            )
            .where(IncidentObservationCorroboration.report_id == report_id)
            .order_by(
                IncidentObservationCorroboration.corroboration_score.desc(),
                IncidentObservationCorroboration.id.desc(),
            )
            .offset(offset)
            .limit(page_size)
        )
        cor_res = await session.execute(cor_stmt)
        rows = cor_res.all()

        items: List[IncidentObservationItemData] = []
        for cor, obs in rows:
            assessment = cor.corroboration_assessment or {}
            if not isinstance(assessment, dict):
                assessment = {}

            rel_str = assessment.get("relationship_type", "CORROBORATING")
            rel = ObservationRelationship.CORROBORATING
            try:
                rel = ObservationRelationship(rel_str)
            except ValueError:
                pass

            dist_km = 0.0
            if cor.distance_meters is not None:
                dist_km = round(cor.distance_meters / 1000.0, 2)

            metrics = ObservationMetricSummary(
                rainfall_mm_1h=obs.rainfall_mm,
                water_level_m=obs.water_level_m,
                wind_speed_kmh=obs.wind_speed_kmh,
            )

            items.append(
                IncidentObservationItemData(
                    corroboration_id=cor.id,
                    observation_id=obs.id,
                    station_code=obs.station_code,
                    station_name=obs.station_name,
                    source_code=obs.source_id.hex[:8],
                    observed_at=obs.observed_at,
                    distance_km=dist_km,
                    relationship=rel,
                    corroboration_score=cor.corroboration_score,
                    is_contradiction=bool(assessment.get("is_contradiction", False)),
                    metrics=metrics,
                    is_human_override=bool(assessment.get("is_human_override", False)),
                )
            )

        total_pages = math.ceil(total_records / page_size) if total_records > 0 else 1
        has_next = page < total_pages
        has_prev = page > 1

        return items, total_records, total_pages, has_next, has_prev

    async def get_incident_cluster(
        self,
        session: AsyncSession,
        identifier: str,
    ) -> Optional[IncidentClusterDetailData]:
        """Fetch duplicate cluster topology and member reports."""
        clean_id = identifier.strip()
        stmt = select(WeatherReport)
        try:
            val_uuid = uuid.UUID(clean_id)
            stmt = stmt.where(WeatherReport.id == val_uuid)
        except ValueError:
            stmt = stmt.where(WeatherReport.tracking_id == clean_id)

        res = await session.execute(stmt)
        report = res.scalar_one_or_none()
        if not report:
            return None

        # Check membership
        dm_stmt = select(DuplicateMember).where(DuplicateMember.report_id == report.id)
        dm_res = await session.execute(dm_stmt)
        dm = dm_res.scalar_one_or_none()

        if not dm:
            # Singleton virtual cluster
            return IncidentClusterDetailData(
                cluster_id=uuid.uuid4(),
                cluster_code=f"SINGLE-{report.tracking_id}",
                total_member_count=1,
                is_representative=True,
                representative_report_id=report.id,
                temporal_span_hours=0.0,
                members=[
                    ClusterMemberSummary(
                        report_id=report.id,
                        tracking_id=report.tracking_id,
                        similarity_score=1.0,
                        occurred_at=report.occurred_at,
                        title=report.title,
                        is_representative=True,
                    )
                ],
            )

        # Joined cluster members
        cluster_stmt = select(DuplicateCluster).where(DuplicateCluster.id == dm.cluster_id)
        clus_res = await session.execute(cluster_stmt)
        cluster = clus_res.scalar_one_or_none()
        if not cluster:
            return None

        members_stmt = (
            select(DuplicateMember, WeatherReport)
            .join(WeatherReport, DuplicateMember.report_id == WeatherReport.id)
            .where(DuplicateMember.cluster_id == cluster.id)
            .order_by(DuplicateMember.similarity_score.desc(), WeatherReport.occurred_at.asc())
        )
        members_res = await session.execute(members_stmt)
        member_rows = members_res.all()

        members_list: List[ClusterMemberSummary] = []
        occurred_times: List[datetime] = []
        for mem, rpt in member_rows:
            is_member_rep = rpt.id == cluster.primary_report_id
            if rpt.occurred_at:
                occurred_times.append(rpt.occurred_at)
            members_list.append(
                ClusterMemberSummary(
                    report_id=rpt.id,
                    tracking_id=rpt.tracking_id,
                    similarity_score=mem.similarity_score,
                    occurred_at=rpt.occurred_at,
                    title=rpt.title,
                    is_representative=is_member_rep,
                )
            )

        span_hours = 0.0
        if len(occurred_times) >= 2:
            min_t = min(occurred_times)
            max_t = max(occurred_times)
            span_hours = round((max_t - min_t).total_seconds() / 3600.0, 2)

        return IncidentClusterDetailData(
            cluster_id=cluster.id,
            cluster_code=f"CLUS-{str(cluster.id)[:8].upper()}",
            total_member_count=cluster.member_count,
            is_representative=(dm.report_id == cluster.primary_report_id),
            representative_report_id=cluster.primary_report_id,
            temporal_span_hours=span_hours,
            members=members_list,
        )

    async def get_verification_queue(
        self,
        session: AsyncSession,
        page: int = 1,
        page_size: int = 20,
        priority: Optional[str] = None,
        category: Optional[str] = None,
        jurisdiction: Optional[str] = None,
    ) -> Tuple[List[IncidentSummaryResponse], int, int, bool, bool]:
        """Operator triage queue with explicit severity ranking."""
        stmt = (
            select(WeatherReport)
            .options(
                selectinload(WeatherReport.category),
                selectinload(WeatherReport.media),
            )
            .where(WeatherReport.verification_status.in_(["PENDING", "UNDER_REVIEW"]))
        )
        count_stmt = select(func.count(WeatherReport.id)).where(
            WeatherReport.verification_status.in_(["PENDING", "UNDER_REVIEW"])
        )

        filters: List[Any] = []
        if category:
            clean_cat = category.strip().upper()
            filters.append(
                (func.upper(WeatherReport.reported_category) == clean_cat)
                | (
                    WeatherReport.category_id.in_(
                        select(EventCategory.id).where(
                            func.upper(EventCategory.category_code) == clean_cat
                        )
                    )
                )
            )

        if priority:
            clean_prio = priority.strip().upper()
            if clean_prio == "HIGH":
                filters.append(WeatherReport.severity.in_(["SEVERE", "HIGH"]))
            elif clean_prio == "NORMAL":
                filters.append(WeatherReport.severity.in_(["MODERATE", "LOW"]))

        if filters:
            stmt = stmt.where(*filters)
            count_stmt = count_stmt.where(*filters)

        total_records_res = await session.execute(count_stmt)
        total_records = total_records_res.scalar() or 0

        # Explicit integer ranking for severity: SEVERE=4, HIGH=3, MODERATE=2, LOW=1
        severity_rank = case(
            (WeatherReport.severity == "SEVERE", 4),
            (WeatherReport.severity == "HIGH", 3),
            (WeatherReport.severity == "MODERATE", 2),
            (WeatherReport.severity == "LOW", 1),
            else_=0,
        )

        # Ordering: severity_rank DESC, credibility_score DESC, occurred_at DESC, id DESC
        stmt = stmt.order_by(
            severity_rank.desc(),
            WeatherReport.credibility_score.desc(),
            WeatherReport.occurred_at.desc(),
            WeatherReport.id.desc(),
        )

        offset = (page - 1) * page_size
        stmt = stmt.offset(offset).limit(page_size)

        res = await session.execute(stmt)
        reports = res.scalars().all()

        total_pages = math.ceil(total_records / page_size) if total_records > 0 else 1
        has_next = page < total_pages
        has_prev = page > 1

        summaries = [
            IncidentSummaryResponse(
                id=r.id,
                tracking_id=r.tracking_id,
                title=r.title,
                category=self._extract_category(r),
                severity=self._extract_severity(r.severity),
                location=IncidentLocationResponse(
                    name=r.location_name,
                    latitude=r.latitude,
                    longitude=r.longitude,
                ),
                occurred_at=r.occurred_at,
                verification_status=r.verification_status,
                credibility_score=r.credibility_score,
                credibility_reason=r.credibility_reason,
                credibility_explanation=r.credibility_explanation,
                readiness=self._extract_readiness(r),
                media_count=len(r.media) if r.media else 0,
                created_at=r.created_at,
            )
            for r in reports
        ]

        return summaries, total_records, total_pages, has_next, has_prev

    async def get_geo_incidents(
        self,
        session: AsyncSession,
        bbox: Optional[Tuple[float, float, float, float]] = None,
        status: Optional[str] = None,
        category: Optional[str] = None,
        hours_ago: Optional[int] = 24,
    ) -> GeoJSONFeatureCollection:
        """Fetch GeoJSON FeatureCollection bounded by PostGIS viewport or nationwide overview."""
        stmt = (
            select(WeatherReport)
            .options(selectinload(WeatherReport.category))
            .where(WeatherReport.geom.isnot(None))
        )

        if bbox is not None:
            min_lon, min_lat, max_lon, max_lat = bbox
            envelope = ST_MakeEnvelope(min_lon, min_lat, max_lon, max_lat, 4326)
            stmt = stmt.where(envelope.ST_Intersects(WeatherReport.geom))

        if status:
            statuses = [s.strip().upper() for s in status.split(",") if s.strip()]
            if statuses:
                stmt = stmt.where(WeatherReport.verification_status.in_(statuses))

        if category:
            stmt = stmt.where(WeatherReport.reported_category == category.strip().upper())

        if hours_ago is not None and hours_ago > 0:
            # Safe temporal restriction
            stmt = stmt.where(
                WeatherReport.occurred_at >= func.now() - func.make_interval(0, 0, 0, 0, hours_ago)
            )

        stmt = stmt.order_by(WeatherReport.occurred_at.desc().nullslast(), WeatherReport.created_at.desc()).limit(500)
        res = await session.execute(stmt)
        reports = res.scalars().all()

        features: List[GeoJSONIncidentFeature] = []
        for r in reports:
            cat_code = r.category.category_code if r.category else (r.reported_category or "OTHER")
            features.append(
                GeoJSONIncidentFeature(
                    geometry=GeoJSONGeometryPoint(coordinates=[r.longitude, r.latitude]),
                    properties=GeoJSONIncidentProperties(
                        id=r.id,
                        tracking_id=r.tracking_id,
                        title=r.title,
                        category_code=cat_code,
                        severity=r.severity,
                        credibility_score=r.credibility_score,
                        credibility_reason=r.credibility_reason,
                        verification_status=r.verification_status,
                        readiness=self._extract_readiness(r).value,
                        occurred_at=r.occurred_at.isoformat(),
                        location_name=r.location_name,
                    ),
                )
            )

        return GeoJSONFeatureCollection(features=features)

    def _parse_time_range(
        self,
        time_range: Optional[str],
        from_date: Optional[datetime],
    ) -> Optional[datetime]:
        """Resolve a temporal lower bound from explicit from_date or named time_range."""
        if from_date is not None:
            return from_date
        if not time_range:
            return None
        tr = time_range.strip().lower()
        now = datetime.now(timezone.utc)
        if tr == "24h":
            return now - timedelta(hours=24)
        if tr == "48h":
            return now - timedelta(hours=48)
        if tr == "7d":
            return now - timedelta(days=7)
        if tr == "30d":
            return now - timedelta(days=30)
        return None

    def _build_aggregation_filters(
        self,
        category: Optional[str] = None,
        severity: Optional[str] = None,
        verification_status: Optional[str] = None,
        from_date: Optional[datetime] = None,
        to_date: Optional[datetime] = None,
        bbox: Optional[Tuple[float, float, float, float]] = None,
    ) -> List[Any]:
        """Build shared parameterized SQL filter clauses for aggregations."""
        filters: List[Any] = []

        if category and category.strip().upper() != "ALL":
            clean_cat = category.strip().upper()
            filters.append(
                (WeatherReport.reported_category == clean_cat)
                | (
                    WeatherReport.category_id.in_(
                        select(EventCategory.id).where(EventCategory.category_code == clean_cat)
                    )
                )
            )

        if severity and severity.strip().upper() != "ALL":
            filters.append(WeatherReport.severity == severity.strip().upper())

        if verification_status and verification_status.strip().upper() != "ALL":
            statuses = [s.strip().upper() for s in verification_status.split(",") if s.strip()]
            if statuses:
                filters.append(WeatherReport.verification_status.in_(statuses))

        if from_date is not None:
            filters.append(WeatherReport.occurred_at >= from_date)

        if to_date is not None:
            filters.append(WeatherReport.occurred_at <= to_date)

        if bbox:
            min_lon, min_lat, max_lon, max_lat = bbox
            envelope = ST_MakeEnvelope(min_lon, min_lat, max_lon, max_lat, 4326)
            filters.append(func.ST_Intersects(WeatherReport.geom, envelope))

        return filters

    async def get_dashboard_summary(
        self,
        session: AsyncSession,
        time_range: Optional[str] = "24h",
        category: Optional[str] = None,
        severity: Optional[str] = None,
        verification_status: Optional[str] = None,
        from_date: Optional[datetime] = None,
        to_date: Optional[datetime] = None,
        bbox: Optional[Tuple[float, float, float, float]] = None,
    ) -> DashboardSummaryData:
        """Compute high-efficiency SQL summary metrics for Dashboard and Analytics."""
        effective_from = self._parse_time_range(time_range, from_date)
        where_filters = self._build_aggregation_filters(
            category=category,
            severity=severity,
            verification_status=verification_status,
            from_date=effective_from,
            to_date=to_date,
            bbox=bbox,
        )

        twenty_four_hours_ago = datetime.now(timezone.utc) - timedelta(hours=24)

        # 1. Main summary metrics in single query
        summary_stmt = select(
            func.count(WeatherReport.id).label("total_count"),
            func.count(case((WeatherReport.occurred_at >= twenty_four_hours_ago, 1))).label(
                "count_24h"
            ),
            func.count(case((WeatherReport.verification_status == "VERIFIED", 1))).label(
                "verified_count"
            ),
            func.count(
                case((WeatherReport.verification_status.in_(["PENDING", "UNDER_REVIEW"]), 1))
            ).label("pending_count"),
            func.count(case((WeatherReport.verification_status == "UNDER_REVIEW", 1))).label(
                "under_review_count"
            ),
            func.count(case((WeatherReport.verification_status == "REJECTED", 1))).label(
                "rejected_count"
            ),
            func.count(case((WeatherReport.verification_status == "DUPLICATE", 1))).label(
                "duplicate_count"
            ),
            func.count(case((WeatherReport.severity.in_(["SEVERE", "HIGH"]), 1))).label(
                "severe_high_count"
            ),
            func.count(case((WeatherReport.severity == "SEVERE", 1))).label("severe_count"),
            func.count(case((WeatherReport.severity == "HIGH", 1))).label("high_count"),
            func.count(case((WeatherReport.severity == "MODERATE", 1))).label("moderate_count"),
            func.count(case((WeatherReport.severity == "LOW", 1))).label("low_count"),
        )
        if where_filters:
            summary_stmt = summary_stmt.where(and_(*where_filters))

        res = await session.execute(summary_stmt)
        row = res.one()

        total_count = int(row.total_count or 0)
        count_24h = int(row.count_24h or 0)
        last_24h_pct = round((count_24h / total_count) * 100) if total_count > 0 else 0
        verified_count = int(row.verified_count or 0)
        verified_rate = round((verified_count / total_count) * 100) if total_count > 0 else 0

        # 2. Category distribution
        cat_code_expr = func.coalesce(
            EventCategory.category_code, WeatherReport.reported_category, "OTHER"
        )
        cat_name_expr = func.coalesce(
            EventCategory.title, WeatherReport.reported_category, "Other Hazard"
        )

        cat_stmt = select(
            cat_code_expr.label("code"),
            cat_name_expr.label("name"),
            func.count(WeatherReport.id).label("cat_count"),
        ).outerjoin(EventCategory, WeatherReport.category_id == EventCategory.id)
        if where_filters:
            cat_stmt = cat_stmt.where(and_(*where_filters))

        cat_stmt = cat_stmt.group_by(cat_code_expr, cat_name_expr).order_by(
            func.count(WeatherReport.id).desc()
        )

        cat_res = await session.execute(cat_stmt)
        cat_rows = cat_res.all()

        category_items: List[CategoryDistributionItem] = []
        for c_row in cat_rows:
            c_count = int(c_row.cat_count or 0)
            c_pct = round((c_count / total_count) * 100) if total_count > 0 else 0
            category_items.append(
                CategoryDistributionItem(
                    category_code=str(c_row.code),
                    category_name=str(c_row.name),
                    count=c_count,
                    percentage=c_pct,
                )
            )

        # 3. 6-hour diurnal distribution (Asia/Kolkata timezone)
        hour_expr = func.extract("hour", func.timezone("Asia/Kolkata", WeatherReport.occurred_at))
        diurnal_stmt = select(
            func.count(case((hour_expr < 6, 1))).label("w0"),
            func.count(case((and_(hour_expr >= 6, hour_expr < 12), 1))).label("w6"),
            func.count(case((and_(hour_expr >= 12, hour_expr < 18), 1))).label("w12"),
            func.count(case((hour_expr >= 18, 1))).label("w18"),
        )
        if where_filters:
            diurnal_stmt = diurnal_stmt.where(and_(*where_filters))

        d_res = await session.execute(diurnal_stmt)
        d_row = d_res.one()

        diurnal_items = [
            DiurnalDistributionItem(
                window="00:00", label="00:00 - 06:00", count=int(d_row.w0 or 0)
            ),
            DiurnalDistributionItem(
                window="06:00", label="06:00 - 12:00", count=int(d_row.w6 or 0)
            ),
            DiurnalDistributionItem(
                window="12:00", label="12:00 - 18:00", count=int(d_row.w12 or 0)
            ),
            DiurnalDistributionItem(
                window="18:00", label="18:00 - 24:00", count=int(d_row.w18 or 0)
            ),
        ]

        return DashboardSummaryData(
            total_count=total_count,
            period_count=total_count,
            count_24h=count_24h,
            last_24h_pct=last_24h_pct,
            verification=VerificationBreakdown(
                verified_count=verified_count,
                verified_rate=verified_rate,
                pending_count=int(row.pending_count or 0),
                under_review_count=int(row.under_review_count or 0),
                rejected_count=int(row.rejected_count or 0),
                duplicate_count=int(row.duplicate_count or 0),
            ),
            severity=SeverityBreakdown(
                severe_high_count=int(row.severe_high_count or 0),
                severe_count=int(row.severe_count or 0),
                high_count=int(row.high_count or 0),
                moderate_count=int(row.moderate_count or 0),
                low_count=int(row.low_count or 0),
            ),
            category_distribution=category_items,
            diurnal_distribution=diurnal_items,
        )

    async def get_analytics_trends(
        self,
        session: AsyncSession,
        time_range: Optional[str] = "7d",
        interval: Optional[str] = None,
        category: Optional[str] = None,
        severity: Optional[str] = None,
        verification_status: Optional[str] = None,
        from_date: Optional[datetime] = None,
        to_date: Optional[datetime] = None,
        bbox: Optional[Tuple[float, float, float, float]] = None,
    ) -> AnalyticsTrendData:
        """Compute time-series activity trend buckets for analytics charts."""
        tr = (time_range or "7d").strip().lower()
        effective_interval = (interval or ("hour" if tr == "24h" else "day")).strip().lower()

        effective_from = self._parse_time_range(tr, from_date)
        where_filters = self._build_aggregation_filters(
            category=category,
            severity=severity,
            verification_status=verification_status,
            from_date=effective_from,
            to_date=to_date,
            bbox=bbox,
        )

        buckets: List[AnalyticsTrendBucket] = []

        if effective_interval == "hour":
            # 6 4-hour diurnal buckets in Asia/Kolkata operational timezone
            hour_expr = func.extract(
                "hour", func.timezone("Asia/Kolkata", WeatherReport.occurred_at)
            )
            stmt = select(
                func.count(case((hour_expr < 4, 1))).label("t0"),
                func.count(
                    case(
                        (
                            and_(
                                hour_expr < 4,
                                WeatherReport.verification_status == "VERIFIED",
                            ),
                            1,
                        )
                    )
                ).label("v0"),
                func.count(case((and_(hour_expr >= 4, hour_expr < 8), 1))).label("t4"),
                func.count(
                    case(
                        (
                            and_(
                                hour_expr >= 4,
                                hour_expr < 8,
                                WeatherReport.verification_status == "VERIFIED",
                            ),
                            1,
                        )
                    )
                ).label("v4"),
                func.count(case((and_(hour_expr >= 8, hour_expr < 12), 1))).label("t8"),
                func.count(
                    case(
                        (
                            and_(
                                hour_expr >= 8,
                                hour_expr < 12,
                                WeatherReport.verification_status == "VERIFIED",
                            ),
                            1,
                        )
                    )
                ).label("v8"),
                func.count(case((and_(hour_expr >= 12, hour_expr < 16), 1))).label("t12"),
                func.count(
                    case(
                        (
                            and_(
                                hour_expr >= 12,
                                hour_expr < 16,
                                WeatherReport.verification_status == "VERIFIED",
                            ),
                            1,
                        )
                    )
                ).label("v12"),
                func.count(case((and_(hour_expr >= 16, hour_expr < 20), 1))).label("t16"),
                func.count(
                    case(
                        (
                            and_(
                                hour_expr >= 16,
                                hour_expr < 20,
                                WeatherReport.verification_status == "VERIFIED",
                            ),
                            1,
                        )
                    )
                ).label("v16"),
                func.count(case((hour_expr >= 20, 1))).label("t20"),
                func.count(
                    case(
                        (
                            and_(
                                hour_expr >= 20,
                                WeatherReport.verification_status == "VERIFIED",
                            ),
                            1,
                        )
                    )
                ).label("v20"),
            )
            if where_filters:
                stmt = stmt.where(and_(*where_filters))

            res = await session.execute(stmt)
            r = res.one()

            buckets = [
                AnalyticsTrendBucket(
                    bucket="00:00",
                    label="00:00 - 04:00",
                    total=int(r.t0 or 0),
                    verified=int(r.v0 or 0),
                ),
                AnalyticsTrendBucket(
                    bucket="04:00",
                    label="04:00 - 08:00",
                    total=int(r.t4 or 0),
                    verified=int(r.v4 or 0),
                ),
                AnalyticsTrendBucket(
                    bucket="08:00",
                    label="08:00 - 12:00",
                    total=int(r.t8 or 0),
                    verified=int(r.v8 or 0),
                ),
                AnalyticsTrendBucket(
                    bucket="12:00",
                    label="12:00 - 16:00",
                    total=int(r.t12 or 0),
                    verified=int(r.v12 or 0),
                ),
                AnalyticsTrendBucket(
                    bucket="16:00",
                    label="16:00 - 20:00",
                    total=int(r.t16 or 0),
                    verified=int(r.v16 or 0),
                ),
                AnalyticsTrendBucket(
                    bucket="20:00",
                    label="20:00 - 24:00",
                    total=int(r.t20 or 0),
                    verified=int(r.v20 or 0),
                ),
            ]
        else:
            # Daily UTC calendar buckets
            day_expr = func.date_trunc("day", func.timezone("UTC", WeatherReport.occurred_at))
            stmt = select(
                day_expr.label("day_bucket"),
                func.count(WeatherReport.id).label("total_count"),
                func.count(case((WeatherReport.verification_status == "VERIFIED", 1))).label(
                    "verified_count"
                ),
            )
            if where_filters:
                stmt = stmt.where(and_(*where_filters))

            stmt = stmt.group_by(day_expr).order_by(day_expr.asc())

            res = await session.execute(stmt)
            rows = res.all()

            db_buckets: Dict[str, Tuple[int, int]] = {}
            for row in rows:
                if row.day_bucket is not None:
                    date_str = row.day_bucket.strftime("%Y-%m-%d")
                    db_buckets[date_str] = (
                        int(row.total_count or 0),
                        int(row.verified_count or 0),
                    )

            now_utc = datetime.now(timezone.utc)
            num_days = 7
            if tr == "30d":
                num_days = 14
            elif tr == "7d":
                num_days = 7

            for i in range(num_days - 1, -1, -1):
                d = now_utc - timedelta(days=i)
                d_key = d.strftime("%Y-%m-%d")
                label = d.strftime("%b %d")
                t, v = db_buckets.get(d_key, (0, 0))
                buckets.append(
                    AnalyticsTrendBucket(
                        bucket=f"{d_key}T00:00:00Z",
                        label=label,
                        total=t,
                        verified=v,
                    )
                )

        return AnalyticsTrendData(
            time_range=tr,
            interval=effective_interval,
            buckets=buckets,
        )

    async def get_regional_distribution(
        self,
        session: AsyncSession,
        time_range: str = "7d",
        category: Optional[str] = None,
        severity: Optional[str] = None,
        verification_status: Optional[str] = None,
        from_date: Optional[datetime] = None,
        to_date: Optional[datetime] = None,
        bbox: Optional[Tuple[float, float, float, float]] = None,
    ) -> AnalyticsRegionalData:
        """Aggregate report counts by geographical region using token matching
        and spatial envelope containment.

        Classification Order (Deterministic & Collision-Free):
        1. Token/phrase regex matching on location_name for major urban centers & states.
        2. Spatial Point-in-Polygon containment (via ST_Contains & ST_MakeEnvelope).
           - Small metro envelopes (DL) evaluated before larger parent envelopes (RJ).
        3. Fallback to 'OTHER' for unmatched areas.
        """
        tr = time_range.strip().lower() if time_range else "7d"
        eff_from = self._parse_time_range(tr, from_date)

        where_filters = self._build_aggregation_filters(
            category=category,
            severity=severity,
            verification_status=verification_status,
            from_date=eff_from,
            to_date=to_date,
            bbox=bbox,
        )

        region_names: Dict[str, str] = {
            "MH": "Maharashtra",
            "TN": "Tamil Nadu",
            "DL": "Delhi NCR",
            "KA": "Karnataka",
            "KL": "Kerala",
            "AS": "Assam",
            "RJ": "Rajasthan",
            "OTHER": "Other Regions",
        }

        # Case expression for deterministic regional categorization
        region_case = case(
            # 1. Word-boundary token matching on location_name
            (
                WeatherReport.location_name.op("~*")(
                    r"\y(mumbai|pune|nagpur|thane|nashik|maharashtra|kurla|andheri|navi mumbai)\y"
                ),
                "MH",
            ),
            (
                WeatherReport.location_name.op("~*")(
                    r"\y(chennai|coimbatore|madurai|tamil nadu|trichy|salem)\y"
                ),
                "TN",
            ),
            (
                WeatherReport.location_name.op("~*")(
                    r"\y(delhi|new delhi|noida|gurgaon|gurugram|faridabad|ghaziabad|ncr)\y"
                ),
                "DL",
            ),
            (
                WeatherReport.location_name.op("~*")(
                    r"\y(bengaluru|bangalore|mysore|karnataka|hubli|mangalore)\y"
                ),
                "KA",
            ),
            (
                WeatherReport.location_name.op("~*")(
                    r"\y(kochi|thiruvananthapuram|calicut|kerala|trivandrum|thrissur)\y"
                ),
                "KL",
            ),
            (
                WeatherReport.location_name.op("~*")(
                    r"\y(guwahati|assam|dibrugarh|silchar|jorhat|dispur)\y"
                ),
                "AS",
            ),
            (
                WeatherReport.location_name.op("~*")(
                    r"\y(jaipur|jodhpur|rajasthan|udaipur|kota|bikaner)\y"
                ),
                "RJ",
            ),
            # 2. Spatial bounding box containment (DL checked before RJ to avoid parent containment)
            (
                func.ST_Contains(
                    func.ST_MakeEnvelope(76.8, 28.4, 77.4, 28.9, 4326), WeatherReport.geom
                ),
                "DL",
            ),
            (
                func.ST_Contains(
                    func.ST_MakeEnvelope(72.6, 15.6, 80.9, 22.0, 4326), WeatherReport.geom
                ),
                "MH",
            ),
            (
                func.ST_Contains(
                    func.ST_MakeEnvelope(76.2, 8.0, 80.3, 13.5, 4326), WeatherReport.geom
                ),
                "TN",
            ),
            (
                func.ST_Contains(
                    func.ST_MakeEnvelope(74.0, 11.5, 78.6, 18.5, 4326), WeatherReport.geom
                ),
                "KA",
            ),
            (
                func.ST_Contains(
                    func.ST_MakeEnvelope(74.8, 8.3, 77.4, 12.8, 4326), WeatherReport.geom
                ),
                "KL",
            ),
            (
                func.ST_Contains(
                    func.ST_MakeEnvelope(89.7, 24.1, 96.0, 28.2, 4326), WeatherReport.geom
                ),
                "AS",
            ),
            (
                func.ST_Contains(
                    func.ST_MakeEnvelope(69.5, 23.0, 78.3, 30.2, 4326), WeatherReport.geom
                ),
                "RJ",
            ),
            else_="OTHER",
        ).label("region_code")

        stmt = select(
            region_case,
            func.count(WeatherReport.id).label("region_count"),
        )
        if where_filters:
            stmt = stmt.where(and_(*where_filters))
        stmt = stmt.group_by(region_case).order_by(
            func.count(WeatherReport.id).desc(),
            region_case.asc(),
        )

        res = await session.execute(stmt)
        rows = res.all()

        total_classified = sum(int(r.region_count or 0) for r in rows)

        regions: List[RegionalDistributionItem] = []
        for r in rows:
            code = str(r.region_code)
            count = int(r.region_count or 0)
            pct = round((count / total_classified) * 100) if total_classified > 0 else 0
            regions.append(
                RegionalDistributionItem(
                    region_code=code,
                    region_name=region_names.get(code, code),
                    count=count,
                    percentage=pct,
                )
            )

        return AnalyticsRegionalData(
            time_range=tr,
            total_classified=total_classified,
            regions=regions,
        )

    async def get_nearby_incidents(
        self,
        session: AsyncSession,
        lat: float,
        lng: float,
        radius_km: float = 25.0,
        status: Optional[str] = None,
        limit: int = 50,
    ) -> GeoJSONFeatureCollection:
        """Fetch GeoJSON FeatureCollection of incidents within radius_km around (lat, lng) for My Area dashboard."""
        center_point = ST_SetSRID(ST_MakePoint(lng, lat), 4326)
        radius_meters = radius_km * 1000.0

        stmt = (
            select(WeatherReport)
            .options(selectinload(WeatherReport.category))
            .where(
                WeatherReport.geom.isnot(None),
                ST_DWithin(
                    cast(WeatherReport.geom, Geography),
                    cast(center_point, Geography),
                    radius_meters,
                ),
            )
        )

        if status:
            statuses = [s.strip().upper() for s in status.split(",") if s.strip()]
            if statuses:
                stmt = stmt.where(WeatherReport.verification_status.in_(statuses))
        else:
            # Default citizen guardrail: VERIFIED or high-credibility UNDER_REVIEW
            stmt = stmt.where(
                (WeatherReport.verification_status == "VERIFIED")
                | (
                    (WeatherReport.verification_status == "UNDER_REVIEW")
                    & (WeatherReport.credibility_score >= 0.70)
                )
            )

        # Distance ordering from center
        dist_expr = ST_Distance(
            cast(WeatherReport.geom, Geography),
            cast(center_point, Geography),
        )
        stmt = stmt.order_by(dist_expr.asc(), WeatherReport.occurred_at.desc()).limit(limit)

        res = await session.execute(stmt)
        reports = res.scalars().all()

        features: List[GeoJSONIncidentFeature] = []
        for r in reports:
            cat_code = r.category.category_code if r.category else (r.reported_category or "OTHER")
            features.append(
                GeoJSONIncidentFeature(
                    geometry=GeoJSONGeometryPoint(coordinates=[r.longitude, r.latitude]),
                    properties=GeoJSONIncidentProperties(
                        id=r.id,
                        tracking_id=r.tracking_id,
                        title=r.title,
                        category_code=cat_code,
                        severity=r.severity,
                        credibility_score=r.credibility_score,
                        credibility_reason=r.credibility_reason,
                        verification_status=r.verification_status,
                        readiness=self._extract_readiness(r).value,
                        occurred_at=r.occurred_at.isoformat(),
                        location_name=r.location_name,
                    ),
                )
            )

        return GeoJSONFeatureCollection(features=features)

    async def get_forecast_advisories(
        self,
        session: AsyncSession,
        active_only: bool = True,
        hazard_type: Optional[str] = None,
    ) -> GeoJSONFeatureCollection:
        """Fetch GeoJSON FeatureCollection of official IMD/NDMA forecast advisories & cyclone tracks."""
        import json

        now = datetime.now(timezone.utc)
        stmt = select(ForecastAdvisory).where(ForecastAdvisory.geom.isnot(None))

        if active_only:
            stmt = stmt.where(ForecastAdvisory.valid_until >= now)

        if hazard_type:
            stmt = stmt.where(
                func.upper(ForecastAdvisory.hazard_type) == hazard_type.strip().upper()
            )

        stmt = stmt.order_by(ForecastAdvisory.valid_until.desc()).limit(100)
        res = await session.execute(stmt)
        advisories = res.scalars().all()

        features: List[GeoJSONIncidentFeature] = []
        for adv in advisories:
            geom_stmt = select(ST_AsGeoJSON(adv.geom).label("geojson_str"))
            g_res = await session.execute(geom_stmt)
            g_str = g_res.scalar()
            geom_dict = json.loads(g_str) if g_str else {"type": "Point", "coordinates": [0, 0]}

            props = GeoJSONIncidentProperties(
                id=adv.id,
                tracking_id=f"ADV-{adv.source_code}-{str(adv.id)[:6].upper()}",
                title=adv.advisory_title,
                category_code=adv.hazard_type,
                severity=adv.severity,
                credibility_score=0.95,
                credibility_reason=f"Official forecast advisory issued by {adv.source_code}.",
                verification_status="VERIFIED",
                readiness="INTELLIGENCE_READY",
                occurred_at=adv.issued_at.isoformat(),
                location_name=adv.advisory_text[:100] if adv.advisory_text else "Advisory Area",
            )
            features.append(
                GeoJSONIncidentFeature(
                    geometry=geom_dict,
                    properties=props,
                )
            )

        return GeoJSONFeatureCollection(features=features)


incident_query_service = IncidentQueryService()
