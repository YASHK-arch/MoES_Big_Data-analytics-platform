"""Asynchronous database collector for incident credibility signals.

Gathers all linked duplicate clusters, digital evidence links, and physical observation
corroborations from PostgreSQL, maps them through the 5-level provenance hierarchy,
and outputs normalized IncidentCredibilityInputs for pure mathematical scoring.
"""

import logging
import uuid
from collections import defaultdict
from dataclasses import dataclass
from typing import Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.intelligence.schemas import (
    ContradictionInput,
    DigitalEvidenceGroupInput,
    EvidenceRelationship,
    IncidentCredibilityInputs,
    ObservationRelationship,
    PhysicalStationInput,
    SourceFamily,
)
from app.models.corroboration import IncidentObservationCorroboration
from app.models.duplicate import DuplicateCluster, DuplicateMember
from app.models.evidence import IncidentEvidenceLink
from app.models.report import WeatherReport

logger = logging.getLogger(__name__)


def map_source_type_to_family(source_type: Optional[str]) -> SourceFamily:
    """Map source catalog type strings to coarse SourceFamily enum."""
    if not source_type:
        return SourceFamily.OTHER
    st = source_type.upper()
    if "CITIZEN" in st:
        return SourceFamily.CITIZEN
    if any(k in st for k in ["IMD", "NDMA", "GOVERNMENT", "OFFICIAL"]):
        return SourceFamily.OFFICIAL
    if any(k in st for k in ["NEWS", "GDELT", "MEDIA", "RSS"]):
        return SourceFamily.NEWS
    if any(k in st for k in ["SOCIAL", "MASTODON", "TWITTER", "FEDIVERSE"]):
        return SourceFamily.SOCIAL
    if any(k in st for k in ["SENSOR", "CWC", "AWS", "RADAR", "SATELLITE", "TELEMETRY"]):
        return SourceFamily.SENSOR
    return SourceFamily.OTHER


@dataclass
class _ProvenanceBucket:
    max_conf: float = 0.0
    role_w: float = 0.0
    count: int = 0
    family: SourceFamily = SourceFamily.NEWS
    is_derived: bool = False
    primary_role: Optional[str] = None


@dataclass
class _StationBucket:
    max_score: float = 0.0
    rel_w: float = 0.0
    family: SourceFamily = SourceFamily.SENSOR
    points_count: int = 1


class CredibilityCollector:
    """Collects and normalizes multi-source signals for an incident."""

    async def collect_inputs(
        self,
        db: AsyncSession,
        incident_id: uuid.UUID,
    ) -> Optional[IncidentCredibilityInputs]:
        """Fetch all linked data for target incident and assemble IncidentCredibilityInputs."""
        # 1. Fetch target WeatherReport and Source
        stmt = (
            select(WeatherReport)
            .where(WeatherReport.id == incident_id)
            .options(
                selectinload(WeatherReport.source),
                selectinload(WeatherReport.category),
            )
        )
        res = await db.execute(stmt)
        incident = res.scalar_one_or_none()
        if not incident:
            logger.warning("Incident %s not found for credibility collection.", incident_id)
            return None

        source_code = incident.source.source_code if incident.source else "CITIZEN_WEB"
        source_type = incident.source.source_type if incident.source else "CITIZEN_REPORT"
        source_base_trust = incident.source.base_trust_score if incident.source else 0.60
        origin_family = map_source_type_to_family(source_type)

        # 2. Metadata completeness checks
        has_coords = (
            incident.latitude is not None
            and incident.longitude is not None
            and (incident.latitude != 0.0 or incident.longitude != 0.0)
        )
        has_time = incident.occurred_at is not None
        has_loc = bool(incident.location_name and incident.location_name.strip())
        has_desc = bool(incident.description and len(incident.description.strip()) >= 5)
        has_cat = bool(incident.category_id or incident.reported_category)

        # 3. Duplicate Cluster Membership (Crowd Signal)
        cluster_count = 1
        # Check if incident is a member of any cluster
        member_stmt = select(DuplicateMember).where(DuplicateMember.report_id == incident_id)
        member_res = await db.execute(member_stmt)
        member_row = member_res.scalar_one_or_none()

        if member_row:
            cluster_stmt = select(DuplicateCluster).where(
                DuplicateCluster.id == member_row.cluster_id
            )
            cluster_res = await db.execute(cluster_stmt)
            cluster_obj = cluster_res.scalar_one_or_none()
            if cluster_obj:
                cluster_count = max(1, cluster_obj.member_count)
        else:
            # Check if incident is primary of a cluster
            primary_stmt = select(DuplicateCluster).where(
                DuplicateCluster.primary_report_id == incident_id
            )
            primary_res = await db.execute(primary_stmt)
            primary_obj = primary_res.scalar_one_or_none()
            if primary_obj:
                cluster_count = max(1, primary_obj.member_count)

        # 4. Digital Evidence Links (Grouped by Provenance)
        evi_stmt = (
            select(IncidentEvidenceLink)
            .where(IncidentEvidenceLink.report_id == incident_id)
            .options(
                selectinload(IncidentEvidenceLink.evidence),
            )
        )
        evi_res = await db.execute(evi_stmt)
        evidence_links = list(evi_res.scalars().all())

        prov_map: Dict[str, _ProvenanceBucket] = defaultdict(_ProvenanceBucket)
        contradiction_inputs: List[ContradictionInput] = []

        for link in evidence_links:
            evidence = link.evidence
            if not evidence:
                continue

            role_str = link.link_role.upper() if link.link_role else "SUPPORTING"
            conf = float(link.confidence_score)

            # Check role weight
            if role_str == EvidenceRelationship.SUPPORTING.value:
                role_w = 1.00
            elif role_str == EvidenceRelationship.RELATED.value:
                role_w = 0.35
            elif role_str == EvidenceRelationship.CONTEXTUAL.value:
                role_w = 0.20
            elif role_str == EvidenceRelationship.CONTRADICTORY.value:
                role_w = 0.00
                contradiction_inputs.append(
                    ContradictionInput(
                        signal_source_key=f"evidence_{evidence.id}",
                        contradiction_score=conf,
                        is_diagnostic=True,
                        is_physical_sensor=False,
                    )
                )
            else:
                role_w = 0.00

            # Deterministic Provenance Hierarchy Key
            # (Approved: 1. Hash, 2. Canonical URL, 3. Wire/Agency, 4. Domain, 5. ID)
            raw_payload = evidence.raw_payload or {}
            wire_tag = raw_payload.get("wire_agency") or raw_payload.get("agency")
            canonical_url = raw_payload.get("canonical_url")
            quotes_social = bool(raw_payload.get("quotes_social") or raw_payload.get("is_derived"))

            if (
                evidence.sha256_hash
                and isinstance(evidence.sha256_hash, str)
                and evidence.sha256_hash.strip()
            ):
                prov_key = f"hash_{evidence.sha256_hash.strip().lower()}"
            elif canonical_url and isinstance(canonical_url, str) and canonical_url.strip():
                prov_key = f"canon_{canonical_url.strip().lower()}"
            elif wire_tag and isinstance(wire_tag, str) and wire_tag.strip():
                prov_key = f"wire_{wire_tag.strip().lower()}"
            elif evidence.publisher_domain and evidence.publisher_domain.strip():
                prov_key = f"domain_{evidence.publisher_domain.strip().lower()}"
            else:
                prov_key = f"evi_{evidence.id}"

            fam = map_source_type_to_family(evidence.evidence_type)
            bucket = prov_map[prov_key]
            bucket.count += 1
            bucket.max_conf = max(bucket.max_conf, conf)
            if role_w > bucket.role_w or bucket.primary_role is None:
                bucket.primary_role = role_str
            bucket.role_w = max(bucket.role_w, role_w)
            bucket.family = fam
            if quotes_social:
                bucket.is_derived = True

        evidence_groups: List[DigitalEvidenceGroupInput] = []
        for pkey, bdata in prov_map.items():
            if bdata.role_w > 0.0:
                evidence_groups.append(
                    DigitalEvidenceGroupInput(
                        provenance_key=pkey,
                        max_confidence=bdata.max_conf,
                        role_weight=bdata.role_w,
                        article_count=bdata.count,
                        source_family=bdata.family,
                        is_derived_lineage=bdata.is_derived,
                        relationship_type=bdata.primary_role,
                    )
                )

        # 5. Physical Observation Corroborations (Grouped by Station)
        obs_stmt = (
            select(IncidentObservationCorroboration)
            .where(IncidentObservationCorroboration.report_id == incident_id)
            .options(
                selectinload(IncidentObservationCorroboration.observation),
            )
        )
        obs_res = await db.execute(obs_stmt)
        corroborations = list(obs_res.scalars().all())

        station_map: Dict[str, _StationBucket] = defaultdict(_StationBucket)

        for corr in corroborations:
            obs = corr.observation
            if not obs:
                continue

            station_key = f"{obs.source_id}_{obs.station_code or 'UNKNOWN'}"
            score = float(corr.corroboration_score)

            assessment_dict = corr.corroboration_assessment or {}
            rel_str = assessment_dict.get(
                "relationship_type", ObservationRelationship.CONSISTENT.value
            )

            if rel_str == ObservationRelationship.CORROBORATING.value:
                rel_w = 1.00
            elif rel_str == ObservationRelationship.CONSISTENT.value:
                rel_w = 0.50
            elif rel_str == ObservationRelationship.WEAK.value:
                rel_w = 0.20
            elif rel_str == ObservationRelationship.CONTRADICTORY.value:
                rel_w = 0.00
                contradiction_inputs.append(
                    ContradictionInput(
                        signal_source_key=f"obs_station_{station_key}",
                        contradiction_score=score,
                        is_diagnostic=True,
                        is_physical_sensor=True,
                    )
                )
            else:
                rel_w = 0.00

            trend_info = assessment_dict.get("trend")
            points = 1
            if isinstance(trend_info, dict):
                p_val = trend_info.get("points_count")
                if isinstance(p_val, int):
                    points = p_val

            stn_bucket = station_map[station_key]
            stn_bucket.max_score = max(stn_bucket.max_score, score)
            stn_bucket.rel_w = max(stn_bucket.rel_w, rel_w)
            stn_bucket.points_count = max(stn_bucket.points_count, points)

        # 5b. S1 Physical Weather Corroborations
        try:
            from app.models.corroboration import IncidentPhysicalCorroboration

            phys_stmt = select(IncidentPhysicalCorroboration).where(
                IncidentPhysicalCorroboration.incident_id == incident_id
            )
            phys_res = await db.execute(phys_stmt)
            for pcorr in phys_res.scalars().all():
                phys_key = f"{pcorr.source}_{pcorr.station_or_grid_id or 'grid'}_{pcorr.variable}"
                score = float(pcorr.weight) if pcorr.weight > 0 else 0.60
                if pcorr.verdict == "SUPPORTS":
                    rel_w = 1.00 if pcorr.source_type == "STATION" else 0.60
                    p_bucket = station_map[phys_key]
                    p_bucket.max_score = max(p_bucket.max_score, score)
                    p_bucket.rel_w = max(p_bucket.rel_w, rel_w)
                    p_bucket.points_count = 1
                elif pcorr.verdict == "CONTRADICTS":
                    if pcorr.source_type == "STATION" or getattr(
                        settings, "PHYSICAL_CORROBORATION_ALLOW_MODEL_CONTRADICTS", False
                    ):
                        contradiction_inputs.append(
                            ContradictionInput(
                                signal_source_key=f"phys_{phys_key}",
                                contradiction_score=score,
                                is_diagnostic=True,
                                is_physical_sensor=True,
                            )
                        )
        except Exception as p_err:
            logger.warning(
                "Error collecting physical corroborations for %s: %s",
                incident_id,
                p_err,
            )

        observation_stations: List[PhysicalStationInput] = []
        for skey, sdata in station_map.items():
            if sdata.rel_w > 0.0:
                observation_stations.append(
                    PhysicalStationInput(
                        station_key=skey,
                        corroboration_score=sdata.max_score,
                        relationship_weight=sdata.rel_w,
                        source_family=SourceFamily.SENSOR,
                        points_count=sdata.points_count,
                    )
                )

        return IncidentCredibilityInputs(
            incident_id=incident_id,
            source_code=source_code,
            source_type=source_type,
            source_base_trust=source_base_trust,
            origin_family=origin_family,
            has_coordinates=has_coords,
            has_timestamp=has_time,
            has_location_name=has_loc,
            has_description=has_desc,
            has_category=has_cat,
            cluster_member_count=cluster_count,
            evidence_groups=evidence_groups,
            observation_stations=observation_stations,
            negative_contradictions=contradiction_inputs,
        )


credibility_collector = CredibilityCollector()
