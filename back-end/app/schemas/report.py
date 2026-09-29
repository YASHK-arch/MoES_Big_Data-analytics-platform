import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

SeverityType = Literal["LOW", "MODERATE", "HIGH", "SEVERE"]


class CitizenReportCreate(BaseModel):
    """Schema for validating citizen incident report submission."""

    latitude: float = Field(
        ...,
        ge=-90.0,
        le=90.0,
        description="Latitude in decimal degrees",
    )
    longitude: float = Field(
        ...,
        ge=-180.0,
        le=180.0,
        description="Longitude in decimal degrees",
    )
    category_code: str = Field(
        ...,
        min_length=2,
        max_length=50,
        description="Standard event category code",
    )
    severity: SeverityType = Field(
        default="MODERATE",
        description="Observed incident severity level",
    )
    title: str = Field(
        ...,
        min_length=3,
        max_length=255,
        description="Brief descriptive summary",
    )
    description: Optional[str] = Field(
        None,
        max_length=5000,
        description="Detailed incident observations",
    )
    location_name: Optional[str] = Field(
        None,
        max_length=255,
        description="Human-readable landmark or address",
    )
    occurred_at: Optional[datetime] = Field(
        default=None,
        description="Time when weather event occurred",
    )

    @field_validator("category_code")
    @classmethod
    def normalize_category_code(cls, v: str) -> str:
        return v.strip().upper()

    @field_validator("title")
    @classmethod
    def sanitize_title(cls, v: str) -> str:
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("Title cannot be blank or whitespace only")
        return cleaned

    @field_validator("occurred_at")
    @classmethod
    def validate_occurred_at(cls, v: Optional[datetime]) -> Optional[datetime]:
        if v is not None:
            # Ensure timezone-aware UTC
            if v.tzinfo is None:
                v = v.replace(tzinfo=timezone.utc)
            now = datetime.now(timezone.utc)
            if v > now:
                # Slight allowance for clock skew (1 minute)
                delta = (v - now).total_seconds()
                if delta > 60:
                    raise ValueError("Report occurred_at cannot be in the future")
        return v


class ReportSubmitData(BaseModel):
    """Data payload for report creation success response."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tracking_id: str
    processing_status: str
    verification_status: str
    submitted_at: datetime
    media_count: int = 0


class ReportSubmitResponse(BaseModel):
    """Standard API envelope for successful report submission."""

    success: bool = True
    data: ReportSubmitData
    meta: Dict[str, Any]


class CategoryDetail(BaseModel):
    """Category representation in report lookup."""

    code: str
    title: str


class LocationDetail(BaseModel):
    """Location coordinates and locality in report lookup."""

    name: Optional[str] = None
    latitude: float
    longitude: float


class MediaDetail(BaseModel):
    """Public media metadata item in report lookup."""

    id: uuid.UUID
    media_type: str
    url: str
    sha256_hash: str


class VerificationEventDetail(BaseModel):
    """Audit detail of a verification action on a report."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    previous_status: str
    new_status: str
    notes: Optional[str] = None
    action_metadata: Optional[Dict[str, Any]] = None
    created_at: datetime
    reviewer_name: str = "Authorized Reviewer"


class ReportVerifyRequest(BaseModel):
    """Payload for verifying a report."""

    notes: Optional[str] = None
    broadcast_alert: Optional[bool] = False


class ReportRejectRequest(BaseModel):
    """Payload for rejecting a report."""

    rejection_reason: Optional[str] = None
    notes: Optional[str] = None


class ReportDuplicateRequest(BaseModel):
    """Payload for marking a report as duplicate."""

    primary_report_id: Optional[str] = None
    notes: Optional[str] = None


class ReportReviewRequest(BaseModel):
    """Payload for placing a report under review."""

    notes: Optional[str] = None


class ReportDetailData(BaseModel):
    """Public report tracking data payload."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tracking_id: str
    title: str
    description: Optional[str] = None
    category: CategoryDetail
    severity: str
    location: LocationDetail
    occurred_at: datetime
    processing_status: str
    verification_status: str
    credibility_score: float = 0.0
    credibility_reason: Optional[str] = None
    media: List[MediaDetail] = []
    verification_history: List[VerificationEventDetail] = []
    created_at: datetime


class ReportDetailResponse(BaseModel):
    """Standard API envelope for report tracking lookup."""

    success: bool = True
    data: ReportDetailData
    meta: Dict[str, Any]


class PaginationMeta(BaseModel):
    """Pagination metadata model conforming to API contract."""

    page: int
    page_size: int
    total_records: int
    total_pages: int
    has_next: bool
    has_prev: bool


class ReportListResponse(BaseModel):
    """Standard API envelope for paginated report listings."""

    success: bool = True
    data: List[ReportDetailData]
    pagination: PaginationMeta
    meta: Dict[str, Any]
