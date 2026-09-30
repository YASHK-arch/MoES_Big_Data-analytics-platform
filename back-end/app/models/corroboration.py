import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict, Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.observation import WeatherObservation
    from app.models.report import WeatherReport


class IncidentObservationCorroboration(Base):
    __tablename__ = "incident_observation_corroborations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    report_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("weather_reports.id", ondelete="CASCADE"),
        nullable=False,
    )
    observation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("weather_observations.id", ondelete="CASCADE"),
        nullable=False,
    )
    distance_meters: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
    )
    time_delta_seconds: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
    )
    corroboration_score: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )
    corroboration_notes: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )
    corroboration_assessment: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSONB,
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Relationships
    report: Mapped["WeatherReport"] = relationship(
        "WeatherReport",
        back_populates="corroborations",
    )
    observation: Mapped["WeatherObservation"] = relationship(
        "WeatherObservation",
        back_populates="corroborations",
    )

    __table_args__ = (
        UniqueConstraint(
            "report_id",
            "observation_id",
            name="uq_incident_observation_corroboration",
        ),
        Index("idx_corroboration_report_id", "report_id"),
        Index("idx_corroboration_observation_id", "observation_id"),
    )


class IncidentPhysicalCorroboration(Base):
    __tablename__ = "incident_physical_corroboration"

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
    variable: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )
    observed_value: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
    )
    unit: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )
    source: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )
    source_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )
    station_or_grid_id: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
    )
    distance_km: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
    )
    time_gap_h: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
    )
    verdict: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )
    weight: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=0.0,
    )
    contribution: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=0.0,
    )
    provider_status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="OK",
    )
    observation_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    explanation: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )
    is_simulated: Mapped[bool] = mapped_column(
        Boolean,
        server_default=text("false"),
        nullable=False,
        default=False,
    )

    # Relationships
    report: Mapped["WeatherReport"] = relationship(
        "WeatherReport",
        back_populates="physical_corroborations",
    )

    __table_args__ = (
        UniqueConstraint(
            "incident_id",
            "variable",
            "source",
            "observation_time",
            name="uq_physical_corrob_incident_var_source_time",
        ),
        Index("idx_physical_corrob_incident_id", "incident_id"),
        Index("idx_physical_corrob_verdict", "verdict"),
        Index("idx_physical_corrob_source_time", "source", "observation_time"),
    )
