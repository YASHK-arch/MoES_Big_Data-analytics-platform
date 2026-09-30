import uuid
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ResolutionStatus(str, Enum):
    """Status of geographic location resolution."""

    RESOLVED = "RESOLVED"
    AMBIGUOUS = "AMBIGUOUS"
    UNRESOLVED = "UNRESOLVED"


class ResolutionMethod(str, Enum):
    """Method utilized for geographic location determination."""

    STRUCTURED_COORDINATES = "STRUCTURED_COORDINATES"
    EXACT_ADMIN_MATCH = "EXACT_ADMIN_MATCH"
    PLACE_DICTIONARY = "PLACE_DICTIONARY"
    GEOCODER = "GEOCODER"
    NLP_ENTITY_RESOLUTION = "NLP_ENTITY_RESOLUTION"
    HUMAN_CORRECTION = "HUMAN_CORRECTION"


class DuplicateDecision(str, Enum):
    """Outcome decision of semantic duplicate evaluation."""

    DUPLICATE = "DUPLICATE"
    POSSIBLE_MATCH = "POSSIBLE_MATCH"
    DISTINCT = "DISTINCT"


class LocationCandidate(BaseModel):
    """A plausible candidate place for an extracted entity."""

    place_name: str = Field(..., description="Canonical place or administrative name.")
    locality: Optional[str] = Field(default=None, description="Sub-city locality.")
    city: Optional[str] = Field(default=None, description="City or municipal area.")
    district: Optional[str] = Field(default=None, description="Administrative district.")
    state: Optional[str] = Field(default=None, description="State or province.")
    country: str = Field(default="India", description="Country name.")
    latitude: float = Field(..., description="WGS84 decimal latitude.")
    longitude: float = Field(..., description="WGS84 decimal longitude.")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Match confidence score.")
    match_type: str = Field(default="EXACT", description="Match precision type.")


class ExtractedEntity(BaseModel):
    """Geographic entity mention identified within unstructured text."""

    text: str = Field(..., description="The raw entity substring extracted from text.")
    normalized_text: str = Field(..., description="Cleaned, lowercased entity text.")
    entity_type: str = Field(
        default="LOCATION",
        description="Entity category ('CITY', 'STATE', 'LOCALITY', 'DISTRICT', 'COUNTRY').",
    )
    start_char: int = Field(..., ge=0, description="Character offset start.")
    end_char: int = Field(..., ge=0, description="Character offset end.")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="Extraction confidence.")


class LocationResolutionResult(BaseModel):
    """Standard contract representing the result of entity and location resolution."""

    original_text: Optional[str] = Field(default=None, description="Raw input text analyzed.")
    normalized_text: Optional[str] = Field(
        default=None, description="Cleaned text after normalization."
    )
    place_name: Optional[str] = Field(default=None, description="Resolved canonical place name.")
    locality: Optional[str] = Field(default=None, description="Sub-city locality if identified.")
    city: Optional[str] = Field(default=None, description="City or urban center.")
    district: Optional[str] = Field(default=None, description="Administrative district.")
    state: Optional[str] = Field(default=None, description="State or Union Territory.")
    country: Optional[str] = Field(default="India", description="Country name.")
    latitude: Optional[float] = Field(
        default=None, ge=-90.0, le=90.0, description="Resolved WGS84 latitude."
    )
    longitude: Optional[float] = Field(
        default=None, ge=-180.0, le=180.0, description="Resolved WGS84 longitude."
    )
    confidence: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Location resolution confidence score (0.0 - 1.0).",
    )
    resolution_status: ResolutionStatus = Field(
        default=ResolutionStatus.UNRESOLVED,
        description="Resolution status ('RESOLVED', 'AMBIGUOUS', 'UNRESOLVED').",
    )
    resolution_method: ResolutionMethod = Field(
        default=ResolutionMethod.NLP_ENTITY_RESOLUTION,
        description="Provenance of how the location was resolved.",
    )
    candidates: List[LocationCandidate] = Field(
        default_factory=list,
        description="Candidate places when resolution is ambiguous or multi-option.",
    )
    provider: str = Field(
        default="internal_gazetteer",
        description="Service or gazetteer database providing the resolution.",
    )
    is_human_corrected: bool = Field(
        default=False,
        description="Flag indicating manual operator intervention/override.",
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional audit, extraction context, or bounding box details.",
    )


class DuplicateSignalBreakdown(BaseModel):
    """Detailed multi-dimensional signal breakdown of duplicate comparison."""

    spatial_distance_meters: Optional[float] = Field(
        default=None, description="Physical distance between incident coordinates."
    )
    spatial_score: float = Field(
        default=0.0, ge=0.0, le=1.0, description="Spatial proximity similarity (0.0 to 1.0)."
    )
    temporal_delta_seconds: Optional[float] = Field(
        default=None, description="Time delta between incident occurrences."
    )
    temporal_score: float = Field(
        default=0.0, ge=0.0, le=1.0, description="Temporal proximity similarity (0.0 to 1.0)."
    )
    category_compatibility_score: float = Field(
        default=0.0, ge=0.0, le=1.0, description="Hazard category compatibility (0.0 to 1.0)."
    )
    semantic_similarity: float = Field(
        default=0.0, ge=0.0, le=1.0, description="Text vector semantic cosine similarity."
    )
    entity_compatibility_score: float = Field(
        default=0.0, ge=0.0, le=1.0, description="Location entity match score."
    )
    source_relationship_score: float = Field(
        default=0.5, ge=0.0, le=1.0, description="Contextual source cross-correlation score."
    )


class DuplicateAssessment(BaseModel):
    """Explainable evaluation output comparing two incident reports for duplication."""

    candidate_report_id: uuid.UUID = Field(..., description="ID of the incoming report.")
    reference_report_id: uuid.UUID = Field(..., description="ID of the existing comparison report.")
    decision: DuplicateDecision = Field(..., description="Classification decision.")
    overall_score: float = Field(
        ..., ge=0.0, le=1.0, description="Composite duplicate similarity score."
    )
    signals: DuplicateSignalBreakdown = Field(..., description="Signal breakdown.")
    explanation: str = Field(..., description="Human-readable decision explanation.")
    model_version: str = Field(..., description="Engine/model version identifier.")
    semantic_method: str = Field(
        default="sparse_tfidf_ngram_v1",
        description="Active semantic vectorization method utilized.",
    )
    assessed_at: datetime = Field(..., description="UTC assessment timestamp.")


class CandidateQueryResult(BaseModel):
    """Result of candidate retrieval with completeness and truncation diagnostics."""

    candidates: List[Any] = Field(default_factory=list, description="Candidate report objects.")
    total_found: int = Field(default=0, description="Total candidates matching criteria.")
    candidate_limit: int = Field(default=50, description="Max candidate limit configured.")
    is_truncated: bool = Field(
        default=False, description="True if candidate count reached the query limit cap."
    )


class ClusterAssignmentResult(BaseModel):
    """Result of evaluating a report against incident duplicate clusters."""

    report_id: uuid.UUID = Field(..., description="ID of the evaluated report.")
    decision: DuplicateDecision = Field(..., description="Clustering decision.")
    cluster_id: Optional[uuid.UUID] = Field(
        default=None, description="Assigned DuplicateCluster ID if confirmed duplicate."
    )
    is_primary: bool = Field(
        default=False, description="True if report is the primary anchor of the cluster."
    )
    matched_report_id: Optional[uuid.UUID] = Field(
        default=None, description="ID of the primary/reference report matched against."
    )
    candidate_count: int = Field(default=0, description="Number of candidates evaluated.")
    is_truncated: bool = Field(
        default=False, description="True if candidate retrieval reached configured cap."
    )
    assessment: Optional[DuplicateAssessment] = Field(
        default=None, description="Detailed assessment with the best candidate match."
    )


class EvidenceRelationship(str, Enum):
    """Semantic relationship between an external evidence item and an incident."""

    SUPPORTING = "SUPPORTING"
    RELATED = "RELATED"
    CONTEXTUAL = "CONTEXTUAL"
    CONTRADICTORY = "CONTRADICTORY"
    IRRELEVANT = "IRRELEVANT"


class EvidenceLinkSignalBreakdown(BaseModel):
    """Signal decomposition for evidence-to-incident link assessment."""

    spatial_distance_meters: Optional[float] = Field(
        default=None, description="Distance between evidence location and incident (meters)."
    )
    spatial_score: float = Field(
        default=0.0, ge=0.0, le=1.0, description="Spatial proximity score."
    )
    temporal_delta_hours: Optional[float] = Field(
        default=None, description="Time delta between evidence publication and incident (hours)."
    )
    temporal_score: float = Field(
        default=0.0, ge=0.0, le=1.0, description="Temporal alignment score."
    )
    semantic_similarity: float = Field(
        default=0.0, ge=0.0, le=1.0, description="Text vector semantic cosine similarity."
    )
    entity_compatibility_score: float = Field(
        default=0.0, ge=0.0, le=1.0, description="Named location entity match score."
    )
    category_relevance_score: float = Field(
        default=0.0, ge=0.0, le=1.0, description="Hazard category relevance score."
    )
    source_context_score: float = Field(
        default=0.5, ge=0.0, le=1.0, description="Source provenance context score."
    )


class EvidenceLinkAssessment(BaseModel):
    """Source-neutral assessment comparing an evidence item against a weather incident."""

    incident_id: uuid.UUID = Field(..., description="ID of the target WeatherReport.")
    evidence_id: uuid.UUID = Field(..., description="ID of the source EvidenceItem.")
    relationship_type: EvidenceRelationship = Field(
        ..., description="Assessed relationship classification."
    )
    overall_score: float = Field(
        ..., ge=0.0, le=1.0, description="Composite link confidence score."
    )
    signals: EvidenceLinkSignalBreakdown = Field(..., description="Decomposed signal breakdown.")
    explanation: str = Field(..., description="Explainable human-readable decision summary.")
    engine_version: str = Field(
        default="v1", description="Evidence linking engine version identifier."
    )
    policy_version: str = Field(
        default="v1", description="Evidence linking policy version identifier."
    )
    semantic_method: str = Field(
        default="sparse_tfidf_ngram_v1",
        description="Semantic text vectorization method utilized.",
    )
    assessed_at: datetime = Field(..., description="UTC assessment timestamp.")


class EvidenceLinkResult(BaseModel):
    """Result of evidence linking evaluation including persistence details."""

    link_id: Optional[uuid.UUID] = Field(
        default=None, description="Assigned IncidentEvidenceLink ID if linked."
    )
    incident_id: uuid.UUID = Field(..., description="Target incident ID.")
    evidence_id: uuid.UUID = Field(..., description="Evidence item ID.")
    relationship_type: EvidenceRelationship = Field(..., description="Relationship decision.")
    confidence_score: float = Field(..., ge=0.0, le=1.0, description="Confidence score.")
    is_linked: bool = Field(
        default=False, description="True if link was established and persisted."
    )
    assessment: EvidenceLinkAssessment = Field(..., description="Underlying assessment details.")


class ObservationRelationship(str, Enum):
    """Corroboration relationship between a physical observation and an incident."""

    CORROBORATING = "CORROBORATING"
    CONSISTENT = "CONSISTENT"
    WEAK = "WEAK"
    CONTRADICTORY = "CONTRADICTORY"
    IRRELEVANT = "IRRELEVANT"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


class TrendDirection(str, Enum):
    """Direction of metric trend from sequential observations."""

    RISING = "RISING"
    STEADY = "STEADY"
    FALLING = "FALLING"
    SINGLE_POINT = "SINGLE_POINT"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


class ObservationDataQuality(str, Enum):
    """Data quality classification for an individual observation."""

    VALID = "VALID"
    STALE = "STALE"
    MISSING_METRIC = "MISSING_METRIC"
    MALFORMED = "MALFORMED"
    INSUFFICIENT_HISTORY = "INSUFFICIENT_HISTORY"


class TrendAnalysisResult(BaseModel):
    """Result of same-station-same-metric trend computation."""

    direction: TrendDirection = Field(..., description="Trend direction.")
    delta_value: Optional[float] = Field(
        default=None, description="Total metric change over window."
    )
    rate_per_hour: Optional[float] = Field(default=None, description="Metric change rate per hour.")
    points_count: int = Field(default=0, description="Number of observations in sequence.")
    span_minutes: Optional[float] = Field(
        default=None, description="Temporal span of observation sequence."
    )
    has_data_gaps: bool = Field(
        default=False,
        description="True if time gaps exceed 2× expected interval.",
    )
    metric_key: str = Field(..., description="Metric column name analysed.")
    station_code: str = Field(..., description="Station code for the trend.")


class CorroborationSignalBreakdown(BaseModel):
    """7-dimensional signal decomposition for observation corroboration."""

    spatial_distance_meters: Optional[float] = Field(
        default=None, description="Physical distance between observation and incident."
    )
    spatial_score: Optional[float] = Field(
        default=None, ge=0.0, le=1.0, description="Distance decay score."
    )
    temporal_delta_seconds: Optional[int] = Field(
        default=None, description="Time delta in seconds."
    )
    temporal_score: Optional[float] = Field(
        default=None, ge=0.0, le=1.0, description="Asymmetric temporal decay score."
    )
    metric_relevance_score: float = Field(
        default=0.0, ge=0.0, le=1.0, description="Hazard-metric compatibility."
    )
    station_context_score: float = Field(
        default=0.0, ge=0.0, le=1.0, description="River/basin/district context match."
    )
    trend_score: float = Field(
        default=0.0, ge=0.0, le=1.0, description="Trend direction and magnitude score."
    )
    data_quality_score: float = Field(
        default=0.0, ge=0.0, le=1.0, description="Observation data quality score."
    )
    source_trust_score: float = Field(
        default=0.0, ge=0.0, le=1.0, description="Source institutional trust."
    )


class CorroborationAssessment(BaseModel):
    """Structured assessment of observation-incident corroboration."""

    incident_id: uuid.UUID = Field(..., description="Target WeatherReport ID.")
    observation_id: uuid.UUID = Field(..., description="Source WeatherObservation ID.")
    relationship_type: ObservationRelationship = Field(
        ..., description="Corroboration classification."
    )
    overall_score: float = Field(..., ge=0.0, le=1.0, description="Composite corroboration score.")
    signals: CorroborationSignalBreakdown = Field(
        ..., description="7-dimensional signal decomposition."
    )
    trend: Optional[TrendAnalysisResult] = Field(default=None, description="Trend analysis result.")
    data_quality: ObservationDataQuality = Field(
        default=ObservationDataQuality.VALID, description="Observation data quality."
    )
    explanation: str = Field(..., description="Human-readable explanation.")
    engine_version: str = Field(default="v1", description="Engine version identifier.")
    policy_version: str = Field(default="water_level_v1", description="Metric policy version.")
    metric_type: str = Field(default="water_level_m", description="Primary metric evaluated.")
    assessed_at: datetime = Field(..., description="UTC assessment timestamp.")
    is_human_override: bool = Field(
        default=False, description="True if a human operator set this assessment."
    )


class CorroborationResult(BaseModel):
    """Result of corroboration evaluation including persistence details."""

    corroboration_id: Optional[uuid.UUID] = Field(default=None, description="Persisted row ID.")
    incident_id: uuid.UUID = Field(..., description="Target incident ID.")
    observation_id: uuid.UUID = Field(..., description="Observation ID.")
    relationship_type: ObservationRelationship = Field(..., description="Relationship decision.")
    corroboration_score: float = Field(..., ge=0.0, le=1.0, description="Composite score.")
    is_persisted: bool = Field(default=False, description="True if row was created/updated.")
    assessment: CorroborationAssessment = Field(..., description="Full assessment details.")


class SourceFamily(str, Enum):
    """Coarse categorization of independent institutional source families."""

    CITIZEN = "CITIZEN"
    OFFICIAL = "OFFICIAL"
    NEWS = "NEWS"
    SOCIAL = "SOCIAL"
    SENSOR = "SENSOR"
    OTHER = "OTHER"


class DigitalEvidenceGroupInput(BaseModel):
    """Input payload for a grouped provenance cluster of digital evidence."""

    provenance_key: str = Field(..., description="Canonical domain, wire tag, or hash key.")
    max_confidence: float = Field(..., ge=0.0, le=1.0, description="Max confidence in group.")
    role_weight: float = Field(
        ..., ge=0.0, le=1.0, description="Role weight (1.0 supporting, 0.35 related)."
    )
    article_count: int = Field(default=1, ge=1, description="Items in this provenance group.")
    source_family: SourceFamily = Field(
        default=SourceFamily.NEWS, description="Source family category."
    )
    is_derived_lineage: bool = Field(
        default=False,
        description="True if derived/cross-quoted from another primary source.",
    )
    relationship_type: Optional[str] = Field(
        default=None,
        description="Primary relationship classification (e.g., SUPPORTING, RELATED, CONTEXTUAL).",
    )


class PhysicalStationInput(BaseModel):
    """Input payload for a single physical monitoring station time-series."""

    station_key: str = Field(..., description="(source_id, station_code) identifier.")
    corroboration_score: float = Field(..., ge=0.0, le=1.0, description="Station trend score.")
    relationship_weight: float = Field(
        ..., ge=0.0, le=1.0, description="Weight (1.0 corroborating, 0.50 consistent, 0.20 weak)."
    )
    source_family: SourceFamily = Field(default=SourceFamily.SENSOR, description="Source family.")
    points_count: int = Field(default=1, ge=1, description="Number of readings in sequence.")


class ContradictionInput(BaseModel):
    """Input payload for a diagnostic negative contradictory signal."""

    signal_source_key: str = Field(..., description="Source provenance key of contradiction.")
    contradiction_score: float = Field(
        ..., ge=0.0, le=1.0, description="Contradiction severity score."
    )
    is_diagnostic: bool = Field(default=True, description="True if diagnostic contradiction.")
    is_physical_sensor: bool = Field(default=True, description="True if physical sensor.")


class IncidentCredibilityInputs(BaseModel):
    """Normalized signal inputs collected from database for pure mathematical scoring."""

    incident_id: uuid.UUID = Field(..., description="Target WeatherReport ID.")
    source_code: str = Field(..., description="Source code of originating incident.")
    source_type: str = Field(..., description="Source type of originating incident.")
    source_base_trust: float = Field(..., ge=0.0, le=1.0, description="Source base trust score.")
    origin_family: SourceFamily = Field(
        default=SourceFamily.CITIZEN, description="Originating source family."
    )
    has_coordinates: bool = Field(default=True, description="Valid coordinates present.")
    has_timestamp: bool = Field(default=True, description="Valid occurred_at present.")
    has_location_name: bool = Field(default=True, description="Location name present.")
    has_description: bool = Field(default=True, description="Description present.")
    has_category: bool = Field(default=True, description="Category present.")
    cluster_member_count: int = Field(default=1, ge=1, description="Reports in duplicate cluster.")
    evidence_groups: List[DigitalEvidenceGroupInput] = Field(
        default_factory=list, description="Digital evidence provenance groups."
    )
    observation_stations: List[PhysicalStationInput] = Field(
        default_factory=list, description="Physical monitoring stations."
    )
    negative_contradictions: List[ContradictionInput] = Field(
        default_factory=list, description="Diagnostic contradictory signals."
    )
    # ── Location-mismatch signal inputs (L5) ──────────────────────────────────
    # Optional: if provided and signal flag enabled, the location-mismatch signal
    # applies a weak negative adjustment to the final score.
    report_text: Optional[str] = Field(
        default=None,
        description="Free-text incident description used for location-mismatch detection.",
    )
    declared_state: Optional[str] = Field(
        default=None,
        description="Reporter's declared state (from submission form) for mismatch check.",
    )
    declared_city: Optional[str] = Field(
        default=None,
        description="Reporter's declared city for mismatch check (optional).",
    )


class CredibilitySignalBreakdown(BaseModel):
    """Decomposed signal component values for structured credibility explanation."""

    source_prior: float = Field(
        ..., ge=0.0, le=1.0, description="Base source institutional trust prior."
    )
    report_quality_score: float = Field(
        ..., ge=0.0, le=1.0, description="Internal report metadata completeness."
    )
    incident_baseline: float = Field(
        ..., ge=0.0, le=1.0, description="Base incident anchor score B_incident."
    )
    crowd_cluster_score: float = Field(
        ..., ge=0.0, le=1.0, description="Duplicate cluster crowd signal S_crowd."
    )
    digital_evidence_score: float = Field(
        ..., ge=0.0, le=1.0, description="Grouped digital evidence score S_evidence."
    )
    physical_observation_score: float = Field(
        ..., ge=0.0, le=1.0, description="Physical observation score S_observation."
    )
    synthesized_support: float = Field(
        ..., ge=0.0, le=1.0, description="Synthesized external support S_support."
    )
    diversity_multiplier: float = Field(
        ..., ge=1.0, le=1.5, description="Source family diversity multiplier D_diversity."
    )
    support_delta: float = Field(..., ge=0.0, le=1.0, description="Corroboration lift Delta.")
    positive_score: float = Field(
        ..., ge=0.0, le=1.0, description="Pre-penalty positive score C_positive."
    )
    negative_penalty: float = Field(..., ge=0.0, le=1.0, description="Negative penalty P_negative.")
    penalized_score: float = Field(
        ..., ge=-1.0, le=1.0, description="Post-penalty score C_penalized."
    )
    applied_cap: float = Field(..., ge=0.0, le=1.0, description="Policy upper bound cap.")
    final_credibility_score: float = Field(
        ..., ge=0.0, le=0.98, description="Final clamped machine credibility score."
    )
    # ── Location-mismatch signal (L5) ─────────────────────────────────────────
    # Populated only when the signal flag is enabled AND report_text/declared_state
    # are provided. Defaults preserve backward compatibility with all existing tests.
    location_mismatch_adjustment: float = Field(
        default=0.0,
        ge=-1.0,
        le=0.0,
        description=(
            "Adjustment applied by location-mismatch signal (<= 0.0). "
            "0.0 when signal disabled, NEUTRAL, or CONSISTENT. "
            "ASSUMPTION - unverified: penalty/cap per location_mismatch_config.py."
        ),
    )
    location_mismatch_signal: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Explainable location-mismatch signal breakdown dict (when active).",
    )


class CredibilityProvenanceSummary(BaseModel):
    """Provenance and independence accounting summary."""

    originating_source_family: SourceFamily = Field(..., description="Origin source family.")
    independent_family_count: int = Field(
        ..., ge=1, description="Count of distinct independent source families."
    )
    participating_families: List[SourceFamily] = Field(
        default_factory=list, description="List of distinct participating families."
    )
    cluster_member_count: int = Field(default=1, ge=1, description="Cluster member count.")
    digital_provenance_groups_count: int = Field(
        default=0, ge=0, description="Count of distinct digital evidence groups."
    )
    physical_stations_count: int = Field(
        default=0, ge=0, description="Count of distinct physical stations."
    )
    has_cross_quoted_lineage: bool = Field(
        default=False, description="True if derived/cross-quoted lineage detected."
    )


class CredibilityAssessment(BaseModel):
    """Full structured machine assessment persisted into WeatherReport.credibility_explanation."""

    incident_id: uuid.UUID = Field(..., description="Target WeatherReport ID.")
    credibility_score: float = Field(
        ..., ge=0.0, le=0.98, description="Machine credibility score (0.0000 - 0.9800)."
    )
    signals: CredibilitySignalBreakdown = Field(
        ..., description="Decomposed mathematical signal breakdown."
    )
    provenance: CredibilityProvenanceSummary = Field(
        ..., description="Provenance and independence accounting details."
    )
    positive_drivers: List[str] = Field(
        default_factory=list, description="Primary positive credibility factors."
    )
    negative_drivers: List[str] = Field(
        default_factory=list, description="Mitigating or contradictory factors."
    )
    uncertainty_flags: List[str] = Field(
        default_factory=list, description="Diagnostic data quality or missingness flags."
    )
    explanation: str = Field(..., description="Human-readable explainable summary text.")
    engine_version: str = Field(default="v1", description="Engine version identifier.")
    policy_version: str = Field(default="v1", description="Policy version identifier.")
    assessed_at: datetime = Field(..., description="UTC assessment timestamp.")
    is_stale: bool = Field(default=False, description="True if recomputation was partial.")
    is_failure_fallback: bool = Field(
        default=False, description="True if fallback preserved prior score."
    )


class CredibilityResult(BaseModel):
    """Result of credibility evaluation including persistence status."""

    incident_id: uuid.UUID = Field(..., description="Target incident ID.")
    credibility_score: float = Field(..., ge=0.0, le=0.98, description="Clamped credibility score.")
    is_persisted: bool = Field(default=False, description="True if updated in database.")
    assessment: CredibilityAssessment = Field(
        ..., description="Full structured assessment details."
    )
