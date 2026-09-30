"""Pydantic schemas for operational incident resource representations."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.orchestration.events import OverallReadiness
from app.schemas.report import (
    CategoryDetail,
    MediaDetail,
    PaginationMeta,
    SeverityType,
    VerificationEventDetail,
)


class IncidentLocationResponse(BaseModel):
    """Geographic location resolution summary."""

    model_config = ConfigDict(from_attributes=True)

    name: Optional[str] = Field(default=None, description="Human-readable place name.")
    latitude: float = Field(..., ge=-90.0, le=90.0)
    longitude: float = Field(..., ge=-180.0, le=180.0)
    resolution_status: str = Field(
        default="STRUCTURED", description="RESOLVED, AMBIGUOUS, UNRESOLVED."
    )
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)


class IncidentCredibilitySummary(BaseModel):
    """Compact machine credibility representation."""

    model_config = ConfigDict(from_attributes=True)

    score: float = Field(..., ge=0.0, le=1.0, description="Machine-assessed credibility score.")
    is_machine_assessed: bool = True
    label: str = Field(default="MODERATE_CREDIBILITY")
    engine_version: str = "v1"
    policy_version: str = "v1"
    explanation: Optional[str] = None
    reason: Optional[str] = Field(
        default=None, description="Concise human-readable credibility reason."
    )
    positive_drivers: List[str] = Field(default_factory=list)
    negative_drivers: List[str] = Field(default_factory=list)
    uncertainty_flags: List[str] = Field(default_factory=list)


class IncidentVerificationSummary(BaseModel):
    """Human verification status representation."""

    model_config = ConfigDict(from_attributes=True)

    status: str = Field(..., description="PENDING, UNDER_REVIEW, VERIFIED, REJECTED, DUPLICATE.")
    is_human_verified: bool = False
    verified_at: Optional[datetime] = None


class IncidentIntelligenceSummary(BaseModel):
    """Compact orchestration intelligence readiness summary."""

    model_config = ConfigDict(from_attributes=True)

    overall_readiness: OverallReadiness
    last_computed_at: Optional[datetime] = None


class IncidentCorroborationCounts(BaseModel):
    """Aggregate counts for linked signals."""

    model_config = ConfigDict(from_attributes=True)

    evidence_count: int = 0
    observation_count: int = 0
    duplicate_cluster_size: int = 1
    is_cluster_representative: bool = True


class IncidentSummaryResponse(BaseModel):
    """Compact incident summary for feed lists, tables, and map overlays."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tracking_id: str
    title: str
    category: CategoryDetail
    severity: SeverityType
    location: IncidentLocationResponse
    occurred_at: datetime
    verification_status: str
    credibility_score: float = Field(..., ge=0.0, le=1.0)
    credibility_reason: Optional[str] = Field(
        default=None, description="Concise human-readable reason for credibility score."
    )
    credibility_explanation: Optional[Dict[str, Any]] = Field(
        default=None, description="Structured credibility assessment breakdown."
    )
    readiness: OverallReadiness
    is_demo: bool = False
    media_count: int = 0
    created_at: datetime


class ImageForensicCheckDetail(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    check_type: str = Field(..., description="EXIF_TIME, EXIF_LOCATION, IMAGE_REUSE, etc.")
    verdict: str = Field(..., description="SUPPORTS, CONTRADICTS, NEUTRAL")
    observed_value: Optional[str] = Field(None, description="Derived privacy-safe observed value")
    expected_value: Optional[str] = Field(None, description="Expected incident declaration value")
    difference: Optional[str] = Field(None, description="Quantified difference between observed and expected")
    reason: str = Field(..., description="Plain-language explanation of check verdict")
    matched_incident_ids: List[str] = Field(
        default_factory=list, description="IDs of matching distant incidents (P5: IDs only)"
    )


class ImageForensicItemDetail(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    media_id: Optional[uuid.UUID] = None
    sha256: str
    phash: str
    has_exif: bool = False
    exif_timestamp_utc: Optional[datetime] = None
    timezone_assumed_ist: bool = False
    time_verdict: str = "NEUTRAL"
    time_difference: Optional[str] = None
    location_verdict: str = "NEUTRAL"
    location_difference: Optional[str] = None
    reuse_verdict: str = "NEUTRAL"
    matched_incident_ids: List[str] = Field(default_factory=list)
    overall_verdict: str = "NEUTRAL"
    credibility_adjustment: float = 0.0
    error_reason: Optional[str] = None
    is_simulated: bool = False
    checks: List[ImageForensicCheckDetail] = Field(default_factory=list)


class IncidentImageForensicsDetail(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    overall_verdict: str = Field(default="NEUTRAL", description="Aggregate verdict: SUPPORTS, CONTRADICTS, NEUTRAL")
    total_credibility_adjustment: float = Field(default=0.0, description="Capped credibility delta applied to incident")
    image_count: int = Field(default=0, description="Number of analyzed images")
    is_simulated: bool = Field(default=False, description="True if generated from demo fixture")
    images: List[ImageForensicItemDetail] = Field(default_factory=list, description="Per-image forensic details")


class IncidentDetailPublic(BaseModel):
    """Public operational incident detail with bounded summaries and PII/audit redacted."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tracking_id: str
    title: str
    description: Optional[str] = None
    category: CategoryDetail
    severity: SeverityType
    location: IncidentLocationResponse
    occurred_at: datetime
    credibility: IncidentCredibilitySummary
    verification: IncidentVerificationSummary
    intelligence_status: IncidentIntelligenceSummary
    summaries: IncidentCorroborationCounts
    is_demo: bool = False
    media: List[MediaDetail] = Field(default_factory=list)
    image_forensics: Optional[IncidentImageForensicsDetail] = Field(
        default=None,
        description="Forensic analysis block for attached images (reused image detection & EXIF consistency).",
    )
    created_at: datetime


class IncidentDetailOperator(IncidentDetailPublic):
    """Full operational incident detail for authorized DEOC/SDRF operators with audit history."""

    verification_history: List[VerificationEventDetail] = Field(default_factory=list)
    orchestration_stages: Dict[str, Any] = Field(default_factory=dict)


class IncidentListResponse(BaseModel):
    """Standard API envelope for paginated incident summaries."""

    success: bool = True
    data: List[IncidentSummaryResponse] = Field(default_factory=list)
    pagination: PaginationMeta
    meta: dict = Field(default_factory=dict)


class IncidentDetailResponse(BaseModel):
    """Standard API envelope for incident detail."""

    success: bool = True
    data: IncidentDetailPublic
    meta: dict = Field(default_factory=dict)


class IncidentOperatorDetailResponse(BaseModel):
    """Standard API envelope for operator incident detail."""

    success: bool = True
    data: IncidentDetailOperator
    meta: dict = Field(default_factory=dict)
