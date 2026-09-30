"""Canonical schema and contract for outbound real-time events.

Used by RealtimeService and downstream SSE transport to deliver structured,
privacy-safe, and deterministic real-time updates to connected clients.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from pydantic import BaseModel, ConfigDict, Field


class RealtimeEventType(str, enum.Enum):
    """Enumeration of domain real-time event types broadcast to clients."""

    REPORT_CREATED = "report.created"
    REPORT_VERIFICATION_CHANGED = "report.verification_changed"
    REPORT_INTELLIGENCE_READY = "report.intelligence_ready"
    CLUSTER_UPDATED = "cluster.updated"
    SYSTEM_HEARTBEAT = "system.heartbeat"
    SYSTEM_RESYNC_REQUIRED = "system.resync_required"
    INCIDENT_PHYSICAL_CORROBORATION_COMPLETED = "incident.physical_corroboration_completed"
    INCIDENT_IMAGE_FORENSICS_COMPLETED = "incident.image_forensics_completed"


class SystemResyncRequiredPayload(BaseModel):
    """Payload emitted when client's Last-Event-ID falls outside retained stream history."""

    model_config = ConfigDict(extra="forbid")

    reason: str = Field(default="RESYNC_REQUIRED")
    message: str = Field(
        default="Stream history pruned. Client must refresh authoritative state via REST API."
    )
    requested_last_event_id: str = Field(..., description="The Last-Event-ID requested by client.")
    oldest_available_id: str = Field(..., description="The oldest available message ID in Redis.")


class ReportCreatedPayload(BaseModel):
    """Safe public metadata for a newly submitted and persisted citizen report."""

    model_config = ConfigDict(extra="forbid")

    tracking_id: str = Field(..., description="Human-readable tracking ID.")
    category_code: str = Field(..., description="Canonical category code.")
    severity: str = Field(..., description="Reported severity level.")
    verification_status: str = Field(default="PENDING", description="Initial verification status.")
    location_name: Optional[str] = Field(default=None, description="Location landmark or locality.")
    latitude: float = Field(..., description="Geographic latitude coordinate.")
    longitude: float = Field(..., description="Geographic longitude coordinate.")
    occurred_at: datetime = Field(..., description="UTC timestamp of occurrence.")
    has_media: bool = Field(default=False, description="Whether media attachments are present.")


class ReportVerificationChangedPayload(BaseModel):
    """Payload for report verification state transitions."""

    model_config = ConfigDict(extra="forbid")

    tracking_id: str = Field(..., description="Human-readable tracking ID.")
    previous_status: str = Field(..., description="Previous verification status.")
    new_status: str = Field(..., description="New verification status.")
    category_code: Optional[str] = Field(default=None, description="Category code.")
    severity: Optional[str] = Field(default=None, description="Severity level.")
    location_name: Optional[str] = Field(default=None, description="Location landmark.")
    occurred_at: Optional[datetime] = Field(default=None, description="UTC occurrence timestamp.")


class ReportIntelligenceReadyPayload(BaseModel):
    """Payload for completed machine credibility & intelligence processing."""

    model_config = ConfigDict(extra="forbid")

    tracking_id: str = Field(..., description="Human-readable tracking ID.")
    credibility_score: float = Field(..., description="Machine-assessed credibility score.")
    readiness: str = Field(..., description="Overall intelligence readiness state.")
    assessed_at: datetime = Field(..., description="UTC assessment timestamp.")


class ClusterUpdatedPayload(BaseModel):
    """Payload for duplicate cluster updates."""

    model_config = ConfigDict(extra="forbid")

    cluster_id: str = Field(..., description="Duplicate cluster ID.")
    primary_report_id: str = Field(..., description="Primary representative report ID.")
    member_count: int = Field(..., ge=1, description="Total members in cluster.")
    updated_at: datetime = Field(..., description="UTC update timestamp.")


class RealtimeEvent(BaseModel):
    """Canonical outbound real-time event envelope."""

    model_config = ConfigDict(extra="forbid")

    event_id: uuid.UUID = Field(
        default_factory=uuid.uuid4, description="Unique UUID for this event."
    )
    event_type: RealtimeEventType = Field(..., description="Type of real-time event.")
    occurred_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC creation timestamp.",
    )
    entity_id: str = Field(
        ..., description="Primary identifier of entity (Report ID or Cluster ID)."
    )
    tracking_id: Optional[str] = Field(default=None, description="Tracking ID if applicable.")
    payload: Dict[str, Any] = Field(
        default_factory=dict, description="Safe client-facing payload dictionary."
    )
