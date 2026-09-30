import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.report import PaginationMeta


class BulkVerificationRequest(BaseModel):
    """Schema for operator bulk triage action."""

    incident_ids: List[str] = Field(
        ...,
        min_length=1,
        max_length=100,
        description="List of report UUIDs or tracking IDs (max 100).",
    )
    action: str = Field(
        ...,
        description="Action to execute: 'VERIFY' or 'REJECT'.",
    )
    notes: Optional[str] = Field(
        default=None,
        max_length=1000,
        description="Operator explanation or operational notes.",
    )
    rejection_reason: Optional[str] = Field(
        default=None,
        max_length=100,
        description="Reason code if action is REJECT (e.g. 'HOAX', 'DUPLICATE', 'OUT_OF_BOUNDS').",
    )


class BulkVerificationResponseData(BaseModel):
    processed_count: int
    action: str
    affected_ids: List[str]


class BulkVerificationResponse(BaseModel):
    success: bool = True
    data: BulkVerificationResponseData
    meta: Dict[str, Any] = Field(default_factory=dict)


class AuditLogItem(BaseModel):
    """Structured audit log record."""

    id: uuid.UUID
    user_id: Optional[uuid.UUID] = None
    user_email: Optional[str] = None
    action: str
    entity_type: str
    entity_id: Optional[uuid.UUID] = None
    ip_address: Optional[str] = None
    payload: Optional[Dict[str, Any]] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AuditLogListResponse(BaseModel):
    success: bool = True
    data: List[AuditLogItem]
    pagination: PaginationMeta
    meta: Dict[str, Any] = Field(default_factory=dict)
