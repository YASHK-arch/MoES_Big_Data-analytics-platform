"""Benchmark v2 comparison: Pre-L1 logic vs New Logic across 65 benchmark pairs."""

import json
import logging
import re
import sys
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.core.config import settings
from app.intelligence.evidence_evaluation_dataset import EVIDENCE_BENCHMARK_PAIRS
from app.intelligence.evidence_scorer import EvidenceScorer, evidence_scorer
from app.intelligence.resolver import location_resolver
from app.intelligence.schemas import (
    EvidenceLinkAssessment,
    EvidenceLinkSignalBreakdown,
    EvidenceRelationship,
)
from app.intelligence.semantic_similarity import semantic_vectorizer

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class PreL1EvidenceScorer(EvidenceScorer):
    """Simulates pre-L1 evidence scoring logic prior to location gates and threshold bump."""

    def __init__(self) -> None:
        super().__init__()
        self.related_threshold = 0.45  # Pre-L1 threshold

    def score_link(
        self,
        incident_id: uuid.UUID,
        evidence_id: uuid.UUID,
        incident_title: str,
        incident_desc: Optional[str],
        incident_cat: str,
        incident_lat: Optional[float],
        incident_lon: Optional[float],
        incident_time: Optional[datetime],
        incident_loc_name: Optional[str],
        evidence_title: str,
        evidence_snippet: Optional[str],
        evidence_source_type: str,
        evidence_pub_time: Optional[datetime],
        evidence_url: Optional[str] = None,
        evidence_domain: Optional[str] = None,
    ) -> EvidenceLinkAssessment:
        inc_full_text = (
            f"{incident_title} {incident_desc or ''} {incident_loc_name or ''} {incident_cat}"
        ).strip()
        evi_full_text = f"{evidence_title} {evidence_snippet or ''}".strip()

        semantic_score = semantic_vectorizer.cosine_similarity(evi_full_text, inc_full_text)
        cat_score = self._assess_category_relevance(evi_full_text, incident_cat)

        evi_loc_res = location_resolver.resolve(text=evi_full_text)
        inc_loc_res = location_resolver.resolve(
            text=inc_full_text,
            latitude=incident_lat,
            longitude=incident_lon,
            location_name=incident_loc_name,
        )

        spatial_distance = None
        spatial_score = 0.0
        entity_score = 0.5

        inc_city = inc_loc_res.city
        inc_state = inc_loc_res.state
        if not inc_city and incident_loc_name:
            loc_clean = incident_loc_name.lower()
            cities = ["mumbai", "delhi", "bengaluru", "chennai", "kolkata", "hyderabad", "pune"]
            for c in cities:
                if c in loc_clean:
                    inc_city = c.capitalize()
                    break

        evi_city = evi_loc_res.city
        has_coords = (
            incident_lat is not None
            and incident_lon is not None
            and evi_loc_res.latitude is not None
            and evi_loc_res.longitude is not None
        )
        if has_coords:
            assert incident_lat is not None and incident_lon is not None
            assert evi_loc_res.latitude is not None and evi_loc_res.longitude is not None
            spatial_distance = self.haversine_distance_meters(
                incident_lat, incident_lon, evi_loc_res.latitude, evi_loc_res.longitude
            )
            if spatial_distance <= self.max_radius:
                spatial_score = max(0.0, 1.0 - (spatial_distance / self.max_radius))

        def is_same_city(c1: Optional[str], c2: Optional[str]) -> bool:
            if not c1 or not c2:
                return False
            return c1.lower() == c2.lower()

        if evi_city and inc_city:
            entity_score = 0.8 if is_same_city(evi_city, inc_city) else 0.0
        elif (
            evi_loc_res.state
            and inc_loc_res.state
            and evi_loc_res.state.lower() == inc_loc_res.state.lower()
        ):
            entity_score = 0.6

        temporal_delta_hours = None
        temporal_score = 0.5
        if incident_time and evidence_pub_time:
            delta_sec = (evidence_pub_time - incident_time).total_seconds()
            temporal_delta_hours = abs(delta_sec) / 3600.0
            if temporal_delta_hours <= 2.0:
                temporal_score = 1.0
            elif temporal_delta_hours <= 24.0:
                temporal_score = 1.0 - (0.3 * ((temporal_delta_hours - 2.0) / 22.0))
            elif temporal_delta_hours <= self.max_window_hours:
                temporal_score = 0.7 - (0.4 * ((temporal_delta_hours - 24.0) / 24.0))
            else:
                temporal_score = 0.0

        src_type_clean = (evidence_source_type or "").upper()
        if src_type_clean in ("GDELT", "NEWS_PORTAL", "GOVERNMENT_PIB", "OFFICIAL_BULLETIN"):
            source_context_score = 0.7
        elif src_type_clean in ("MASTODON", "SOCIAL_MEDIA"):
            source_context_score = 0.6
        else:
            source_context_score = 0.5

        signals = EvidenceLinkSignalBreakdown(
            spatial_distance_meters=round(spatial_distance, 1) if spatial_distance else None,
            spatial_score=round(spatial_score, 4),
            temporal_delta_hours=round(temporal_delta_hours, 2) if temporal_delta_hours else None,
            temporal_score=round(temporal_score, 4),
            semantic_similarity=round(semantic_score, 4),
            entity_compatibility_score=round(entity_score, 4),
            category_relevance_score=round(cat_score, 4),
            source_context_score=round(source_context_score, 4),
        )

        # Foreign check
        clean_evi = evi_full_text.lower()
        if (evi_loc_res.country and evi_loc_res.country.lower() != "india") or any(
            re.search(rf"\b{kw}\b", clean_evi) for kw in ["nepal", "pakistan", "bangladesh"]
        ):
            return EvidenceLinkAssessment(
                incident_id=incident_id,
                evidence_id=evidence_id,
                relationship_type=EvidenceRelationship.IRRELEVANT,
                overall_score=0.0,
                signals=signals,
                explanation="Foreign territory",
                engine_version="pre-l1",
                policy_version="pre-l1",
                semantic_method="sparse_tfidf_ngram_v1",
                assessed_at=datetime.now(timezone.utc),
            )

        if cat_score == 0.0:
            return EvidenceLinkAssessment(
                incident_id=incident_id,
                evidence_id=evidence_id,
                relationship_type=EvidenceRelationship.IRRELEVANT,
                overall_score=0.0,
                signals=signals,
                explanation="Incompatible hazard",
                engine_version="pre-l1",
                policy_version="pre-l1",
                semantic_method="sparse_tfidf_ngram_v1",
                assessed_at=datetime.now(timezone.utc),
            )

        if spatial_distance is not None and spatial_distance > self.max_radius:
            return EvidenceLinkAssessment(
                incident_id=incident_id,
                evidence_id=evidence_id,
                relationship_type=EvidenceRelationship.IRRELEVANT,
                overall_score=0.0,
                signals=signals,
                explanation="Distance exceeds max radius",
                engine_version="pre-l1",
                policy_version="pre-l1",
                semantic_method="sparse_tfidf_ngram_v1",
                assessed_at=datetime.now(timezone.utc),
            )

        if evi_city and inc_city and not is_same_city(evi_city, inc_city):
            return EvidenceLinkAssessment(
                incident_id=incident_id,
                evidence_id=evidence_id,
                relationship_type=EvidenceRelationship.IRRELEVANT,
                overall_score=0.0,
                signals=signals,
                explanation="Different city",
                engine_version="pre-l1",
                policy_version="pre-l1",
                semantic_method="sparse_tfidf_ngram_v1",
                assessed_at=datetime.now(timezone.utc),
            )

        if temporal_delta_hours is not None and temporal_delta_hours > self.max_window_hours:
            return EvidenceLinkAssessment(
                incident_id=incident_id,
                evidence_id=evidence_id,
                relationship_type=EvidenceRelationship.IRRELEVANT,
                overall_score=0.0,
                signals=signals,
                explanation="Temporal mismatch",
                engine_version="pre-l1",
                policy_version="pre-l1",
                semantic_method="sparse_tfidf_ngram_v1",
                assessed_at=datetime.now(timezone.utc),
            )

        overall = (
            0.30 * semantic_score
            + 0.25 * entity_score
            + 0.20 * temporal_score
            + 0.15 * cat_score
            + 0.10 * spatial_score
        )

        is_contextual = self._is_contextual_text(evi_full_text)
        if is_contextual and overall >= self.contextual_threshold:
            return EvidenceLinkAssessment(
                incident_id=incident_id,
                evidence_id=evidence_id,
                relationship_type=EvidenceRelationship.CONTEXTUAL,
                overall_score=round(overall, 4),
                signals=signals,
                explanation="Contextual",
                engine_version="pre-l1",
                policy_version="pre-l1",
                semantic_method="sparse_tfidf_ngram_v1",
                assessed_at=datetime.now(timezone.utc),
            )

        if (
            overall >= self.supporting_threshold
            and semantic_score >= 0.35
            and entity_score >= 0.70
            and temporal_score >= 0.50
        ):
            return EvidenceLinkAssessment(
                incident_id=incident_id,
                evidence_id=evidence_id,
                relationship_type=EvidenceRelationship.SUPPORTING,
                overall_score=round(overall, 4),
                signals=signals,
                explanation="Supporting",
                engine_version="pre-l1",
                policy_version="pre-l1",
                semantic_method="sparse_tfidf_ngram_v1",
                assessed_at=datetime.now(timezone.utc),
            )

        if overall >= self.related_threshold and (entity_score >= 0.50 or semantic_score >= 0.40):
            return EvidenceLinkAssessment(
                incident_id=incident_id,
                evidence_id=evidence_id,
                relationship_type=EvidenceRelationship.RELATED,
                overall_score=round(overall, 4),
                signals=signals,
                explanation="Related",
                engine_version="pre-l1",
                policy_version="pre-l1",
                semantic_method="sparse_tfidf_ngram_v1",
                assessed_at=datetime.now(timezone.utc),
            )

        return EvidenceLinkAssessment(
            incident_id=incident_id,
            evidence_id=evidence_id,
            relationship_type=EvidenceRelationship.IRRELEVANT,
            overall_score=round(overall, 4),
            signals=signals,
            explanation="Irrelevant",
            engine_version="pre-l1",
            policy_version="pre-l1",
            semantic_method="sparse_tfidf_ngram_v1",
            assessed_at=datetime.now(timezone.utc),
        )


def evaluate(scorer: EvidenceScorer, name: str) -> Dict[str, Any]:
    tp = 0
    fp = 0
    fn = 0
    tn = 0
    failed_cases = []

    for pair in EVIDENCE_BENCHMARK_PAIRS:
        res = scorer.score_link(
            incident_id=uuid.uuid4(),
            evidence_id=uuid.uuid4(),
            incident_title=pair["inc_title"],
            incident_desc=pair.get("inc_desc"),
            incident_cat=pair["inc_cat"],
            incident_lat=pair.get("inc_lat"),
            incident_lon=pair.get("inc_lon"),
            incident_time=pair.get("inc_time"),
            incident_loc_name=pair.get("inc_loc"),
            evidence_title=pair["evi_title"],
            evidence_snippet=pair.get("evi_desc"),
            evidence_source_type=pair.get("evi_source", "NEWS_PORTAL"),
            evidence_pub_time=pair.get("evi_pub_time"),
        )
        expected_is_link = pair["expected"] != EvidenceRelationship.IRRELEVANT
        actual_is_link = res.relationship_type != EvidenceRelationship.IRRELEVANT

        if expected_is_link and actual_is_link:
            tp += 1
        elif not expected_is_link and actual_is_link:
            fp += 1
            failed_cases.append({"id": pair["id"], "type": "FALSE_POSITIVE", "got": res.relationship_type.value, "score": res.overall_score})
        elif expected_is_link and not actual_is_link:
            fn += 1
            failed_cases.append({"id": pair["id"], "type": "FALSE_NEGATIVE", "got": res.relationship_type.value, "score": res.overall_score})
        else:
            tn += 1

    precision = tp / (tp + fp) if (tp + fp) > 0 else 1.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 1.0
    f1 = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0.0

    return {
        "name": name,
        "total_pairs": len(EVIDENCE_BENCHMARK_PAIRS),
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "tn": tn,
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "failed_cases": failed_cases,
    }


if __name__ == "__main__":
    pre_l1_res = evaluate(PreL1EvidenceScorer(), "Pre-L1 Logic (Baseline)")
    new_res = evaluate(evidence_scorer, "New L1/L2 Logic")

    print(json.dumps({"pre_l1": pre_l1_res, "new_l1": new_res}, indent=2))
