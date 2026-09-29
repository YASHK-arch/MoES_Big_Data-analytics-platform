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
    reason: Optional[str] = Field(default=None, description="Concise human-readable credibility reason.")
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
    credibility_reason: Optional[str] = Field(default=None, description="Concise human-readable reason for credibility score.")
    credibility_explanation: Optional[Dict[str, Any]] = Field(default=None, description="Structured credibility assessment breakdown.")
    readiness: OverallReadiness
    media_count: int = 0
    created_at: datetime


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
    media: List[MediaDetail] = Field(default_factory=list)
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
