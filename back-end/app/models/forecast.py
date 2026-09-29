import uuid
from datetime import datetime
from typing import Any, Dict, Optional

from geoalchemy2 import Geometry
from sqlalchemy import DateTime, Index, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ForecastAdvisory(Base):
    """Official weather forecast advisories, cyclone tracks, and warning polygons."""

    __tablename__ = "forecast_advisories"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    source_code: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
    )
    hazard_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
    )
    severity: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="MODERATE",
    )
    advisory_title: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    advisory_text: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )
    geom: Mapped[Any] = mapped_column(
        Geometry(geometry_type="GEOMETRY", srid=4326, spatial_index=True),
        nullable=False,
    )
    valid_from: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )
    valid_until: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )
    issued_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    raw_payload: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSONB,
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (
        Index("idx_forecast_advisories_validity", "valid_until", "hazard_type"),
    )
