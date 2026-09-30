import math
import re
import uuid
from datetime import datetime, timezone
from typing import Optional

from app.core.config import settings
from app.intelligence.gazetteer import INDIAN_CITIES
from app.intelligence.resolver import location_resolver
from app.intelligence.schemas import (
    EvidenceLinkAssessment,
    EvidenceLinkSignalBreakdown,
    EvidenceRelationship,
)
from app.intelligence.semantic_similarity import semantic_vectorizer


class EvidenceScorer:
    """Multi-signal evidence linking engine evaluating external evidence relevance to incidents.

    NOTE: Initial thresholds and weights are v1 heuristic policy parameters, not ground-truth.
    """

    def __init__(
        self,
        max_spatial_radius_meters: Optional[float] = None,
        max_time_window_hours: Optional[float] = None,
        supporting_threshold: Optional[float] = None,
        related_threshold: Optional[float] = None,
        contextual_threshold: Optional[float] = None,
        engine_version: Optional[str] = None,
        policy_version: Optional[str] = None,
        semantic_method: Optional[str] = None,
    ) -> None:
        self.max_radius = max_spatial_radius_meters or settings.EVIDENCE_SPATIAL_RADIUS_METERS
        self.max_window_hours = max_time_window_hours or settings.EVIDENCE_TIME_WINDOW_HOURS
        self.supporting_threshold = supporting_threshold or settings.EVIDENCE_SUPPORTING_THRESHOLD
        self.related_threshold = related_threshold or settings.EVIDENCE_RELATED_THRESHOLD
        self.contextual_threshold = contextual_threshold or settings.EVIDENCE_CONTEXTUAL_THRESHOLD
        self.engine_version = engine_version or settings.EVIDENCE_LINK_ENGINE_VERSION
        self.policy_version = policy_version or "v1"
        self.semantic_method = semantic_method or settings.DUPLICATE_SEMANTIC_METHOD

    @staticmethod
    def haversine_distance_meters(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """Calculate great-circle distance in meters between two coordinates."""
        r = 6371000.0
        phi1 = math.radians(lat1)
        phi2 = math.radians(lat2)
        delta_phi = math.radians(lat2 - lat1)
        delta_lambda = math.radians(lon2 - lon1)

        a = (
            math.sin(delta_phi / 2.0) ** 2
            + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0) ** 2
        )
        c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
        return r * c

    def _assess_category_relevance(self, evidence_text: str, incident_cat: str) -> float:
        """Calculate category relevance score between evidence text and incident hazard category."""
        clean_text = evidence_text.lower()
        clean_cat = (incident_cat or "OTHER").upper()

        # Non-weather metaphor rejection
        non_weather_cues = [
            "stadium",
            "tournament",
            "cricket",
            "match",
            "tickets",
            "cinema",
            "celebrity",
            "box office",
        ]
        weather_cues = [
            "rainfall",
            "waterlogging",
            "submerged",
            "inundated",
            "monsoon",
            "cloudburst",
        ]
        if any(w in clean_text for w in non_weather_cues) and not any(
            w in clean_text for w in weather_cues
        ):
            return 0.0

        # Incompatibility hard checks
        if clean_cat in ("FLOOD_WATERLOGGING", "HEAVY_RAINFALL"):
            if "heatwave" in clean_text or "heat wave" in clean_text or "drought" in clean_text:
                if not any(
                    w in clean_text
                    for w in [
                        "heavy rain",
                        "waterlogging",
                        "flooding",
                        "submerged",
                        "inundated",
                        "cloudburst",
                    ]
                ):
                    return 0.0
        elif clean_cat == "HEATWAVE":
            if "flash flood" in clean_text or "inundation" in clean_text:
                return 0.0

        cat_keywords = {
            "FLOOD_WATERLOGGING": [
                "flood",
                "flooding",
                "waterlog",
                "waterlogging",
                "inundat",
                "submerged",
                "subway",
                "overflow",
                "drainage",
                "water accumulation",
                "underpass",
                "danger mark",
                "danger level",
            ],
            "HEAVY_RAINFALL": [
                "rain",
                "rainfall",
                "downpour",
                "monsoon",
                "shower",
                "cloudburst",
                "precipitation",
                "deluge",
            ],
            "THUNDERSTORM": [
                "thunderstorm",
                "storm",
                "thunder",
                "lightning",
                "gust",
                "gale",
                "squall",
                "tree fall",
                "tree topple",
                "uprooted tree",
            ],
            "LIGHTNING": ["lightning", "thunder", "strike", "electrocution"],
            "CYCLONE": ["cyclone", "storm surge", "depression", "gale", "coastal storm"],
            "LANDSLIDE": ["landslide", "mudslide", "rockfall", "debris", "ghat road blocked"],
            "HEATWAVE": ["heatwave", "heat wave", "extreme temperature", "loo", "scorching"],
            "COLDWAVE": ["coldwave", "cold wave", "frost", "chill", "freeze"],
            "DROUGHT": ["drought", "dry spell", "water scarcity", "famine", "crop failure"],
        }

        keywords = cat_keywords.get(clean_cat, ["weather", "rain", "storm", "flood"])
        matches = sum(1 for kw in keywords if kw in clean_text)

        if matches >= 2:
            return 1.0 if clean_cat != "OTHER" else 0.7
        elif matches == 1:
            return 0.8 if clean_cat != "OTHER" else 0.5
        elif any(
            kw in clean_text
            for kw in ["rain", "storm", "flood", "alert", "weather", "warning", "monsoon"]
        ):
            return 0.5
        return 0.2

    @staticmethod
    def _is_contextual_text(text: str) -> bool:
        """Detect whether text indicates general preparedness, review, or advisory."""
        clean = text.lower()
        contextual_patterns = [
            r"\bpreparedness\b",
            r"\breview meeting\b",
            r"\bmonsoon preparedness\b",
            r"\badvisory issued\b",
            r"\bgovernment reviews\b",
            r"\bmonitoring situation\b",
            r"\bprecautionary measure\b",
            r"\bbriefed authorities\b",
            r"\bcontingency plan\b",
        ]
        return any(re.search(pat, clean) for pat in contextual_patterns)

    @staticmethod
    def _is_contradictory_text(text: str) -> bool:
        """Detect whether text indicates an explicit denial, rumour debunking, or all-clear."""
        clean = text.lower()
        contradictory_patterns = [
            r"\bfake news\b",
            r"\brumour\b",
            r"\bdenies reports\b",
            r"\bno waterlogging\b",
            r"\btraffic completely normal\b",
            r"\bno truth\b",
            r"\bdebunked\b",
            r"\bclaims rejected\b",
        ]
        return any(re.search(pat, clean) for pat in contradictory_patterns)

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
        """Evaluate an external evidence item against a target incident report."""
        # 1. Prepare Text Payloads
        inc_full_text = (
            f"{incident_title} {incident_desc or ''} {incident_loc_name or ''} {incident_cat}"
        ).strip()
        evi_full_text = f"{evidence_title} {evidence_snippet or ''}".strip()

        # 2. Semantic Text Similarity
        semantic_score = semantic_vectorizer.cosine_similarity(
            evi_full_text,
            inc_full_text,
        )

        # 3. Category Relevance
        cat_score = self._assess_category_relevance(evi_full_text, incident_cat)

        # 4. Location Resolution & Spatial Proximity
        evi_loc_res = location_resolver.resolve(text=evi_full_text)
        inc_loc_res = location_resolver.resolve(
            text=inc_full_text,
            latitude=incident_lat,
            longitude=incident_lon,
            location_name=incident_loc_name,
        )

        spatial_distance: Optional[float] = None
        spatial_score = 0.0
        entity_score = 0.5

        # Identify cities and states from coords, resolver, and text
        inc_has_coords = incident_lat is not None and incident_lon is not None
        inc_text_res = location_resolver.resolve(text=inc_full_text)
        inc_city = inc_loc_res.city or inc_text_res.city
        inc_state = inc_loc_res.state or inc_text_res.state

        if inc_has_coords and (not inc_city or not inc_state):
            assert incident_lat is not None and incident_lon is not None
            for c_data in INDIAN_CITIES.values():
                if "lat" in c_data and "lon" in c_data:
                    d = self.haversine_distance_meters(
                        incident_lat, incident_lon, c_data["lat"], c_data["lon"]
                    )
                    if d <= 50000.0:
                        inc_city = inc_city or c_data.get("city")
                        inc_state = inc_state or c_data.get("state")
                        break

        if not inc_city and incident_loc_name:
            loc_clean = incident_loc_name.lower()
            cities = [
                "mumbai",
                "delhi",
                "bengaluru",
                "chennai",
                "kolkata",
                "hyderabad",
                "pune",
                "kochi",
                "guwahati",
                "patna",
                "shimla",
                "dehradun",
                "amritsar",
                "thane",
                "puri",
            ]
            for c in cities:
                if c in loc_clean:
                    inc_city = c.capitalize()
                    break

        if inc_city and not inc_state:
            c_key = inc_city.lower()
            if c_key in INDIAN_CITIES:
                inc_state = INDIAN_CITIES[c_key].get("state")

        evi_has_coords = (
            evi_loc_res.latitude is not None and evi_loc_res.longitude is not None
        )
        evi_text_res = location_resolver.resolve(text=evi_full_text)
        evi_city = evi_loc_res.city or evi_text_res.city
        evi_state = evi_loc_res.state or evi_text_res.state

        if evi_has_coords and (not evi_city or not evi_state):
            assert evi_loc_res.latitude is not None and evi_loc_res.longitude is not None
            for c_data in INDIAN_CITIES.values():
                if "lat" in c_data and "lon" in c_data:
                    d = self.haversine_distance_meters(
                        evi_loc_res.latitude, evi_loc_res.longitude, c_data["lat"], c_data["lon"]
                    )
                    if d <= 50000.0:
                        evi_city = evi_city or c_data.get("city")
                        evi_state = evi_state or c_data.get("state")
                        break

        if evi_city and not evi_state:
            c_key = evi_city.lower()
            if c_key in INDIAN_CITIES:
                evi_state = INDIAN_CITIES[c_key].get("state")

        # Foreign Country Check
        foreign_kws = [
            "nepal",
            "pakistan",
            "bangladesh",
            "sri lanka",
            "bhutan",
            "myanmar",
            "china",
            "afghanistan",
            "tibet",
        ]
        clean_evi = evi_full_text.lower()
        is_foreign = (evi_loc_res.country and evi_loc_res.country.lower() != "india") or any(
            re.search(rf"\b{kw}\b", clean_evi) for kw in foreign_kws
        )

        has_coords = inc_has_coords and evi_has_coords
        if has_coords:
            assert incident_lat is not None and incident_lon is not None
            assert evi_loc_res.latitude is not None and evi_loc_res.longitude is not None
            spatial_distance = self.haversine_distance_meters(
                incident_lat, incident_lon, evi_loc_res.latitude, evi_loc_res.longitude
            )
            if spatial_distance <= self.max_radius:
                spatial_score = max(0.0, 1.0 - (spatial_distance / self.max_radius))
            else:
                spatial_score = 0.0

        def is_same_city(c1: Optional[str], c2: Optional[str]) -> bool:
            if not c1 or not c2:
                return False
            c1_l = c1.lower()
            c2_l = c2.lower()
            if c1_l == c2_l:
                return True
            if "delhi" in c1_l and "delhi" in c2_l:
                return True
            if "mumbai" in c1_l and "mumbai" in c2_l:
                return True
            if ("kurla" in c1_l and "mumbai" in c2_l) or ("kurla" in c2_l and "mumbai" in c1_l):
                return True
            b1 = "bengaluru" in c1_l or "bangalore" in c1_l
            b2 = "bengaluru" in c2_l or "bangalore" in c2_l
            return b1 and b2

        if evi_city and inc_city:
            if is_same_city(evi_city, inc_city):
                has_loc_match = evi_loc_res.locality and (
                    (
                        inc_loc_res.locality
                        and evi_loc_res.locality.lower() == inc_loc_res.locality.lower()
                    )
                    or (evi_loc_res.locality.lower() in inc_full_text.lower())
                )
                entity_score = 1.0 if has_loc_match else 0.8
            else:
                entity_score = 0.0
        elif (
            evi_state
            and inc_state
            and evi_state.lower() == inc_state.lower()
        ):
            entity_score = 0.6
        elif evi_loc_res.place_name and inc_loc_res.place_name:
            if evi_loc_res.place_name.lower() in inc_full_text.lower():
                entity_score = 0.85

        # 5. Temporal Proximity (Lag between Incident occurrence and Evidence publication)
        temporal_delta_hours: Optional[float] = None
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

        # 6. Source Provenance Context (contextual signal, not automated truth)
        src_type_clean = (evidence_source_type or "").upper()
        if src_type_clean in ("GDELT", "NEWS_PORTAL", "GOVERNMENT_PIB", "OFFICIAL_BULLETIN"):
            source_context_score = 0.7
        elif src_type_clean in ("MASTODON", "SOCIAL_MEDIA"):
            source_context_score = 0.6
        else:
            source_context_score = 0.5

        signals = EvidenceLinkSignalBreakdown(
            spatial_distance_meters=round(spatial_distance, 1)
            if spatial_distance is not None
            else None,
            spatial_score=round(spatial_score, 4),
            temporal_delta_hours=round(temporal_delta_hours, 2)
            if temporal_delta_hours is not None
            else None,
            temporal_score=round(temporal_score, 4),
            semantic_similarity=round(semantic_score, 4),
            entity_compatibility_score=round(entity_score, 4),
            category_relevance_score=round(cat_score, 4),
            source_context_score=round(source_context_score, 4),
        )

        # =========================================================================
        # 7. DECISION POLICY & HARD GATES
        # =========================================================================
        # Gate 1: Foreign location vs Indian incident -> IRRELEVANT
        if is_foreign:
            return EvidenceLinkAssessment(
                incident_id=incident_id,
                evidence_id=evidence_id,
                relationship_type=EvidenceRelationship.IRRELEVANT,
                overall_score=0.0,
                signals=signals,
                explanation=(
                    f"Evidence refers to foreign territory ({evi_loc_res.country}), "
                    "irrelevant to Indian incident."
                ),
                engine_version=self.engine_version,
                policy_version=self.policy_version,
                semantic_method=self.semantic_method,
                assessed_at=datetime.now(timezone.utc),
            )

        # Gate 2: Incompatible hazard category -> IRRELEVANT
        if cat_score == 0.0:
            return EvidenceLinkAssessment(
                incident_id=incident_id,
                evidence_id=evidence_id,
                relationship_type=EvidenceRelationship.IRRELEVANT,
                overall_score=0.0,
                signals=signals,
                explanation=(
                    f"Incompatible hazard between evidence text and incident ({incident_cat})."
                ),
                engine_version=self.engine_version,
                policy_version=self.policy_version,
                semantic_method=self.semantic_method,
                assessed_at=datetime.now(timezone.utc),
            )

        # Gate 3: Confirmed spatial distance exceeds maximum radius -> IRRELEVANT
        if spatial_distance is not None and spatial_distance > self.max_radius:
            return EvidenceLinkAssessment(
                incident_id=incident_id,
                evidence_id=evidence_id,
                relationship_type=EvidenceRelationship.IRRELEVANT,
                overall_score=0.0,
                signals=signals,
                explanation=(
                    f"Distance ({spatial_distance / 1000:.1f}km) exceeds max radius "
                    f"({self.max_radius / 1000:.1f}km)."
                ),
                engine_version=self.engine_version,
                policy_version=self.policy_version,
                semantic_method=self.semantic_method,
                assessed_at=datetime.now(timezone.utc),
            )

        # Gate 4: Confirmed different cities -> IRRELEVANT
        if evi_city and inc_city and not is_same_city(evi_city, inc_city):
            return EvidenceLinkAssessment(
                incident_id=incident_id,
                evidence_id=evidence_id,
                relationship_type=EvidenceRelationship.IRRELEVANT,
                overall_score=0.0,
                signals=signals,
                explanation=f"Evidence is in a different city ({evi_city} vs {inc_city}).",
                engine_version=self.engine_version,
                policy_version=self.policy_version,
                semantic_method=self.semantic_method,
                assessed_at=datetime.now(timezone.utc),
            )

        # Gate 4b: Both states known and different -> IRRELEVANT
        if (
            evi_state
            and inc_state
            and evi_state.strip().lower() != inc_state.strip().lower()
        ):
            return EvidenceLinkAssessment(
                incident_id=incident_id,
                evidence_id=evidence_id,
                relationship_type=EvidenceRelationship.IRRELEVANT,
                overall_score=0.0,
                signals=signals,
                explanation=f"Evidence is in a different state ({evi_state} vs {inc_state}).",
                engine_version=self.engine_version,
                policy_version=self.policy_version,
                semantic_method=self.semantic_method,
                assessed_at=datetime.now(timezone.utc),
            )

        # Gate 4c: Neither side has coordinates and no matching state or city -> IRRELEVANT
        if not inc_has_coords and not evi_has_coords:
            if inc_state or inc_city or evi_state or evi_city:
                matching_city = is_same_city(evi_city, inc_city)
                matching_state = bool(
                    evi_state
                    and inc_state
                    and evi_state.strip().lower() == inc_state.strip().lower()
                )
                if not matching_city and not matching_state:
                    return EvidenceLinkAssessment(
                        incident_id=incident_id,
                        evidence_id=evidence_id,
                        relationship_type=EvidenceRelationship.IRRELEVANT,
                        overall_score=0.0,
                        signals=signals,
                        explanation=(
                            "Neither incident nor evidence has coordinates, and no matching state "
                            f"or city found ({evi_city or evi_state} vs {inc_city or inc_state})."
                        ),
                        engine_version=self.engine_version,
                        policy_version=self.policy_version,
                        semantic_method=self.semantic_method,
                        assessed_at=datetime.now(timezone.utc),
                    )

        # Gate 5: Extreme temporal mismatch (> 48h horizon) -> IRRELEVANT
        if temporal_delta_hours is not None and temporal_delta_hours > self.max_window_hours:
            return EvidenceLinkAssessment(
                incident_id=incident_id,
                evidence_id=evidence_id,
                relationship_type=EvidenceRelationship.IRRELEVANT,
                overall_score=0.0,
                signals=signals,
                explanation=(
                    f"Evidence published {temporal_delta_hours:.1f}h away, "
                    f"exceeding {self.max_window_hours:.0f}h window."
                ),
                engine_version=self.engine_version,
                policy_version=self.policy_version,
                semantic_method=self.semantic_method,
                assessed_at=datetime.now(timezone.utc),
            )

        # Check for explicit Contradiction
        if self._is_contradictory_text(evi_full_text) and entity_score >= 0.70:
            return EvidenceLinkAssessment(
                incident_id=incident_id,
                evidence_id=evidence_id,
                relationship_type=EvidenceRelationship.CONTRADICTORY,
                overall_score=0.85,
                signals=signals,
                explanation=(
                    "Evidence contains explicit denial or debunking regarding the incident."
                ),
                engine_version=self.engine_version,
                policy_version=self.policy_version,
                semantic_method=self.semantic_method,
                assessed_at=datetime.now(timezone.utc),
            )

        # Calculate composite score
        overall = (
            0.30 * semantic_score
            + 0.25 * entity_score
            + 0.20 * temporal_score
            + 0.15 * cat_score
            + 0.10 * spatial_score
        )

        # Contextual check (Government review / preparedness)
        is_state_advisory = bool(
            evi_state
            and not evi_city
            and not evi_loc_res.locality
            and inc_state
            and evi_state.lower() == inc_state.lower()
        )
        is_contextual = self._is_contextual_text(evi_full_text) or is_state_advisory

        # One side has coordinates and the other only state/city: compare state; -0.10 if city unknown
        one_sided_coords = inc_has_coords != evi_has_coords
        if one_sided_coords and (not inc_city or not evi_city) and not is_contextual:
            overall = max(0.0, overall - 0.10)

        if is_contextual and overall >= self.contextual_threshold:
            return EvidenceLinkAssessment(
                incident_id=incident_id,
                evidence_id=evidence_id,
                relationship_type=EvidenceRelationship.CONTEXTUAL,
                overall_score=round(overall, 4),
                signals=signals,
                explanation=(
                    "Contextual evidence concerning regional preparedness/advisory, "
                    "not direct event verification."
                ),
                engine_version=self.engine_version,
                policy_version=self.policy_version,
                semantic_method=self.semantic_method,
                assessed_at=datetime.now(timezone.utc),
            )

        # Supporting Evidence
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
                explanation=(
                    f"Supporting evidence with high semantic relevance ({semantic_score:.2f}) "
                    "and matching location/timeframe."
                ),
                engine_version=self.engine_version,
                policy_version=self.policy_version,
                semantic_method=self.semantic_method,
                assessed_at=datetime.now(timezone.utc),
            )

        # Related Evidence (broader area or moderate text match)
        if overall >= self.related_threshold and (entity_score >= 0.50 or semantic_score >= 0.40):
            return EvidenceLinkAssessment(
                incident_id=incident_id,
                evidence_id=evidence_id,
                relationship_type=EvidenceRelationship.RELATED,
                overall_score=round(overall, 4),
                signals=signals,
                explanation=f"Related report in broader region (similarity {overall:.2f}).",
                engine_version=self.engine_version,
                policy_version=self.policy_version,
                semantic_method=self.semantic_method,
                assessed_at=datetime.now(timezone.utc),
            )

        # Distinct / Irrelevant
        return EvidenceLinkAssessment(
            incident_id=incident_id,
            evidence_id=evidence_id,
            relationship_type=EvidenceRelationship.IRRELEVANT,
            overall_score=round(overall, 4),
            signals=signals,
            explanation=f"Irrelevant to incident: score {overall:.2f} below link threshold.",
            engine_version=self.engine_version,
            policy_version=self.policy_version,
            semantic_method=self.semantic_method,
            assessed_at=datetime.now(timezone.utc),
        )


evidence_scorer = EvidenceScorer()
