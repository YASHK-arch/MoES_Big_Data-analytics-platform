import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from geoalchemy2 import Geometry
from sqlalchemy import (
    ARRAY,
    DateTime,
    Float,
    Index,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class WeatherReportArchive(Base):
    __tablename__ = "weather_reports_archive"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
    )
    tracking_id: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        index=True,
    )
    source_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
    )
    external_id: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        index=True,
    )
    category_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
    )
    reported_category: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
    )
    severity: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="MODERATE",
    )
    title: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    description: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )
    location_name: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
    )
    geom: Mapped[Any] = mapped_column(
        Geometry(geometry_type="POINT", srid=4326, spatial_index=True),
        nullable=False,
    )
    latitude: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )
    longitude: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )
    processing_status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="PROCESSED",
    )
    verification_status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="VERIFIED",
        index=True,
    )
    credibility_score: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=0.0,
        index=True,
    )
    credibility_explanation: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSONB,
        nullable=True,
    )
    text_embedding: Mapped[Optional[List[float]]] = mapped_column(
        ARRAY(Float),
        nullable=True,
    )
    raw_payload: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSONB,
        nullable=True,
    )
    original_created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    archived_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )

    __table_args__ = (
        Index("idx_weather_reports_archive_status_time", "verification_status", occurred_at.desc()),
        Index("idx_weather_reports_archive_credibility", credibility_score.desc()),
        Index("idx_weather_reports_archive_source_external", "source_id", "external_id"),
    )
