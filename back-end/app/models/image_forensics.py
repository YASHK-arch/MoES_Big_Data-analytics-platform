import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.media import ReportMedia
    from app.models.report import WeatherReport


class ImageHash(Base):
    __tablename__ = "image_hashes"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    media_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("report_media.id", ondelete="CASCADE"),
        nullable=True,
    )
    incident_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("weather_reports.id", ondelete="CASCADE"),
        nullable=True,
    )
    sha256: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )
    phash: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
    )
    dhash: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (
        Index("idx_image_hashes_phash", "phash"),
        Index("idx_image_hashes_sha256", "sha256"),
        Index("idx_image_hashes_incident_id", "incident_id"),
        Index("idx_image_hashes_media_id", "media_id"),
    )


class IncidentImageFinding(Base):
    __tablename__ = "incident_image_findings"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    incident_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("weather_reports.id", ondelete="CASCADE"),
        nullable=False,
    )
    media_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("report_media.id", ondelete="CASCADE"),
        nullable=True,
    )
    sha256: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )
    phash: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
    )
    dhash: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
    )
    has_exif: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )
    exif_timestamp_utc: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    timezone_assumed_ist: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )
    time_verdict: Mapped[str] = mapped_column(
        String(20),
        default="NEUTRAL",
        nullable=False,
    )
    time_difference: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
    )
    location_verdict: Mapped[str] = mapped_column(
        String(20),
        default="NEUTRAL",
        nullable=False,
    )
    location_difference: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
    )
    reuse_verdict: Mapped[str] = mapped_column(
        String(20),
        default="NEUTRAL",
        nullable=False,
    )
    matched_incident_ids: Mapped[Optional[List[str]]] = mapped_column(
        JSONB,
        default=list,
        nullable=True,
    )
    overall_verdict: Mapped[str] = mapped_column(
        String(20),
        default="NEUTRAL",
        nullable=False,
    )
    credibility_adjustment: Mapped[float] = mapped_column(
        Float,
        default=0.0,
        nullable=False,
    )
    checks: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSONB,
        nullable=True,
    )
    error_reason: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
    )
    is_simulated: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    report: Mapped["WeatherReport"] = relationship(
        "WeatherReport",
        back_populates="image_findings",
    )
    media: Mapped[Optional["ReportMedia"]] = relationship(
        "ReportMedia",
        lazy="selectin",
    )

    __table_args__ = (
        Index("idx_incident_image_findings_incident", "incident_id"),
        Index("idx_incident_image_findings_media", "media_id"),
        Index("idx_incident_image_findings_phash", "phash"),
    )
