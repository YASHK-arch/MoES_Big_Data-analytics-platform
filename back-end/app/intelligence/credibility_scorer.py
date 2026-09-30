"""Pure mathematical deterministic credibility scorer for incidents.

No database access or network I/O.
Computes headroom-bounded additive credibility with diminishing returns,
provenance-aware syndication collapse, physical station deduplication,
source diversity multipliers, and policy caps.
"""

import math
from typing import Optional, Set

from app.core.config import settings
from app.intelligence.schemas import (
    CredibilitySignalBreakdown,
    DigitalEvidenceGroupInput,
    IncidentCredibilityInputs,
    SourceFamily,
)

VERIFICATION_THRESHOLDS: tuple[float, ...] = (0.45, 0.50, 0.65, 0.70, 0.80, 0.82, 0.85, 0.88)
MAX_WEAK_LINK_CONTRIBUTION: float = 0.03


WEAK_RELATIONSHIP_TYPES: set[str] = {"RELATED", "CONTEXTUAL"}


class CredibilityScorer:
    """Pure deterministic mathematical credibility scoring engine."""

    def __init__(
        self,
        quality_floor_factor: Optional[float] = None,
        quality_scale_factor: Optional[float] = None,
        support_crowd_weight: Optional[float] = None,
        support_evidence_weight: Optional[float] = None,
        support_observation_weight: Optional[float] = None,
        diversity_increment: Optional[float] = None,
        max_negative_penalty: Optional[float] = None,
        diag_obs_weight: Optional[float] = None,
        diag_evi_weight: Optional[float] = None,
        cap_uncorroborated_citizen: Optional[float] = None,
        cap_uncorroborated_official: Optional[float] = None,
        cap_single_provenance: Optional[float] = None,
        cap_physical_only: Optional[float] = None,
        cap_max_machine: Optional[float] = None,
        total_physical_cap: Optional[float] = None,
    ) -> None:
        self.quality_floor = (
            quality_floor_factor
            if quality_floor_factor is not None
            else settings.CREDIBILITY_QUALITY_FLOOR_FACTOR
        )
        self.quality_scale = (
            quality_scale_factor
            if quality_scale_factor is not None
            else settings.CREDIBILITY_QUALITY_SCALE_FACTOR
        )
        self.weight_crowd = (
            support_crowd_weight
            if support_crowd_weight is not None
            else settings.CREDIBILITY_SUPPORT_CROWD_WEIGHT
        )
        self.weight_evidence = (
            support_evidence_weight
            if support_evidence_weight is not None
            else settings.CREDIBILITY_SUPPORT_EVIDENCE_WEIGHT
        )
        self.weight_observation = (
            support_observation_weight
            if support_observation_weight is not None
            else settings.CREDIBILITY_SUPPORT_OBSERVATION_WEIGHT
        )
        self.diversity_inc = (
            diversity_increment
            if diversity_increment is not None
            else settings.CREDIBILITY_DIVERSITY_INCREMENT
        )
        self.max_negative_penalty = (
            max_negative_penalty
            if max_negative_penalty is not None
            else settings.CREDIBILITY_MAX_NEGATIVE_PENALTY
        )
        self.diag_obs_weight = (
            diag_obs_weight if diag_obs_weight is not None else settings.CREDIBILITY_DIAG_OBS_WEIGHT
        )
        self.diag_evi_weight = (
            diag_evi_weight if diag_evi_weight is not None else settings.CREDIBILITY_DIAG_EVI_WEIGHT
        )
        self.cap_citizen = (
            cap_uncorroborated_citizen
            if cap_uncorroborated_citizen is not None
            else settings.CREDIBILITY_CAP_UNCORROBORATED_CITIZEN
        )
        self.cap_official = (
            cap_uncorroborated_official
            if cap_uncorroborated_official is not None
            else settings.CREDIBILITY_CAP_UNCORROBORATED_OFFICIAL
        )
        self.cap_single_prov = (
            cap_single_provenance
            if cap_single_provenance is not None
            else settings.CREDIBILITY_CAP_SINGLE_PROVENANCE
        )
        self.cap_physical_only = (
            cap_physical_only
            if cap_physical_only is not None
            else settings.CREDIBILITY_CAP_PHYSICAL_ONLY
        )
        self.cap_max = (
            cap_max_machine if cap_max_machine is not None else settings.CREDIBILITY_CAP_MAX_MACHINE
        )
        self.total_physical_cap = (
            total_physical_cap
            if total_physical_cap is not None
            else getattr(settings, "PHYSICAL_CORROBORATION_TOTAL_CAP", 0.10)
        )

    def _compute_raw_signals(
        self,
        inputs: IncidentCredibilityInputs,
    ) -> CredibilitySignalBreakdown:
        """Compute the raw mathematical credibility breakdown from normalized inputs."""
        # 1. Source Prior
        s_prior = max(0.10, min(0.95, float(inputs.source_base_trust)))

        # 2. Report Quality
        s_quality = (
            0.30 * (1.0 if inputs.has_coordinates else 0.0)
            + 0.25 * (1.0 if inputs.has_timestamp else 0.0)
            + 0.20 * (1.0 if inputs.has_location_name else 0.0)
            + 0.15 * (1.0 if inputs.has_description else 0.0)
            + 0.10 * (1.0 if inputs.has_category else 0.0)
        )
        s_quality = max(0.0, min(1.0, s_quality))

        # 3. Base Incident Anchor
        b_incident = s_prior * (self.quality_floor + self.quality_scale * s_quality)
        b_incident = max(0.0, min(1.0, b_incident))

        # 4. Crowd Cluster Signal (with exponential diminishing returns)
        k = max(1, inputs.cluster_member_count)
        if k > 1:
            s_crowd = 1.0 - math.exp(-(k - 1) / 3.0)
        else:
            s_crowd = 0.0
        s_crowd = max(0.0, min(1.0, s_crowd))

        # 5. Grouped Digital Evidence (with logarithmic diminishing returns per provenance group)
        if inputs.evidence_groups:
            prod_e = 1.0
            for grp in inputs.evidence_groups:
                count = max(1, grp.article_count)
                diminishing = 1.0 + 0.20 * math.log(1.0 + count - 1.0)
                v_u = min(1.0, (grp.max_confidence * grp.role_weight) * diminishing)
                prod_e *= 1.0 - 0.50 * v_u
            s_evidence = max(0.0, min(1.0, 1.0 - prod_e))
        else:
            s_evidence = 0.0

        # 6. Physical Observation Telemetry (grouped by physical station)
        if inputs.observation_stations:
            prod_o = 1.0
            for stn in inputs.observation_stations:
                y_v = min(1.0, stn.corroboration_score * stn.relationship_weight)
                prod_o *= 1.0 - 0.60 * y_v
            raw_s_observation = max(0.0, min(1.0, 1.0 - prod_o))
            # P5: Total physical credibility contribution capped by config (no double counting)
            s_observation = min(self.total_physical_cap, raw_s_observation)
        else:
            s_observation = 0.0

        # 7. Synthesized External Support Score
        s_support = min(
            1.0,
            self.weight_crowd * s_crowd
            + self.weight_evidence * s_evidence
            + self.weight_observation * s_observation,
        )

        # 8. Source Family Diversity Accounting
        participating_families: Set[SourceFamily] = {inputs.origin_family}
        for grp in inputs.evidence_groups:
            if not grp.is_derived_lineage and (grp.max_confidence * grp.role_weight) > 0.10:
                participating_families.add(grp.source_family)
        for stn in inputs.observation_stations:
            if (stn.corroboration_score * stn.relationship_weight) > 0.10:
                participating_families.add(stn.source_family)

        n_indep_fam = max(1, len(participating_families))
        d_diversity = 1.0 + self.diversity_inc * (n_indep_fam - 1)

        # 9. Support Delta (Headroom Bounded)
        headroom = max(0.0, 1.0 - b_incident)
        delta_support = headroom * min(1.0, s_support * d_diversity)

        # 10. Positive Pre-Penalty Score
        c_positive = b_incident + delta_support

        # 11. Bounded Negative Contradiction Penalty
        if inputs.negative_contradictions:
            prod_neg = 1.0
            for c in inputs.negative_contradictions:
                if c.is_diagnostic:
                    w = self.diag_obs_weight if c.is_physical_sensor else self.diag_evi_weight
                    prod_neg *= 1.0 - w * c.contradiction_score
            p_negative = min(
                self.max_negative_penalty,
                (1.0 - prod_neg) * self.max_negative_penalty,
            )
        else:
            p_negative = 0.0

        # 12. Penalized Score
        c_penalized = c_positive - p_negative

        # 13. Policy Cap Determination
        has_crowd = s_crowd > 0.01
        has_evi = s_evidence > 0.01
        has_obs = s_observation > 0.01
        has_corroboration = has_crowd or has_evi or has_obs

        if not has_corroboration:
            if inputs.origin_family == SourceFamily.CITIZEN:
                applicable_cap = self.cap_citizen
            elif inputs.origin_family == SourceFamily.OFFICIAL:
                applicable_cap = self.cap_official
            else:
                applicable_cap = 0.75
        elif n_indep_fam == 1:
            applicable_cap = self.cap_single_prov
        elif not has_evi and not has_crowd and has_obs and n_indep_fam == 2:
            applicable_cap = self.cap_physical_only
        else:
            applicable_cap = self.cap_max

        # 14. Final Score (Clamped strictly to [0.0000, 0.9800])
        final_score = round(max(0.0000, min(c_penalized, applicable_cap, self.cap_max)), 4)

        return CredibilitySignalBreakdown(
            source_prior=round(s_prior, 4),
            report_quality_score=round(s_quality, 4),
            incident_baseline=round(b_incident, 4),
            crowd_cluster_score=round(s_crowd, 4),
            digital_evidence_score=round(s_evidence, 4),
            physical_observation_score=round(s_observation, 4),
            synthesized_support=round(s_support, 4),
            diversity_multiplier=round(d_diversity, 4),
            support_delta=round(delta_support, 4),
            positive_score=round(c_positive, 4),
            negative_penalty=round(p_negative, 4),
            penalized_score=round(c_penalized, 4),
            applied_cap=round(applicable_cap, 4),
            final_credibility_score=final_score,
        )

    @staticmethod
    def _is_weak_group(grp: DigitalEvidenceGroupInput) -> bool:
        """Check if group represents weak evidence (keyed on relationship type RELATED/CONTEXTUAL)."""
        if grp.relationship_type is not None:
            return grp.relationship_type.upper() in WEAK_RELATIONSHIP_TYPES
        return grp.role_weight < 0.8

    def score_incident(
        self,
        inputs: IncidentCredibilityInputs,
    ) -> CredibilitySignalBreakdown:
        """Compute incident credibility breakdown with capped weak link contributions."""
        # Key on relationship type: RELATED and CONTEXTUAL links
        has_weak = any(self._is_weak_group(grp) for grp in inputs.evidence_groups)
        if not has_weak:
            return self._compute_raw_signals(inputs)

        # 1. Compute full raw signals
        full_signals = self._compute_raw_signals(inputs)

        # 2. Compute signals with only strong evidence (excluding RELATED and CONTEXTUAL)
        strong_groups = [grp for grp in inputs.evidence_groups if not self._is_weak_group(grp)]
        strong_inputs = inputs.model_copy(update={"evidence_groups": strong_groups})
        strong_signals = self._compute_raw_signals(strong_inputs)

        s_strong = strong_signals.final_credibility_score
        s_full = full_signals.final_credibility_score

        if s_full <= s_strong:
            return full_signals

        # 3. Cap weak link boost: max +0.03 over strong baseline
        max_allowed = s_strong + MAX_WEAK_LINK_CONTRIBUTION

        # 4. Invariant: weak links can never be the sole reason to cross any verification priority threshold
        next_thresholds = [t for t in VERIFICATION_THRESHOLDS if t > s_strong]
        if next_thresholds:
            t_next = min(next_thresholds)
            if max_allowed >= t_next:
                max_allowed = round(t_next - 0.0001, 4)

        capped_score = round(min(s_full, max_allowed), 4)
        return full_signals.model_copy(update={"final_credibility_score": capped_score})


credibility_scorer = CredibilityScorer()
