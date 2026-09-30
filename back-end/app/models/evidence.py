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
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.report import WeatherReport
    from app.models.source import Source


class EvidenceItem(Base):
    __tablename__ = "evidence_items"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    source_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sources.id"),
        nullable=False,
    )
    external_id: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
    )
    evidence_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="NEWS_ARTICLE",
    )
    title: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
    )
    url: Mapped[Optional[str]] = mapped_column(
        String(1000),
        nullable=True,
    )
    publisher_domain: Mapped[Optional[str]] = mapped_column(
        String(150),
        nullable=True,
        index=True,
    )
    is_test_fixture: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        index=True,
    )
    language: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
        default="English",
    )
    published_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
    )
    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    text_snippet: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )
    sha256_hash: Mapped[Optional[str]] = mapped_column(
        String(64),
        nullable=True,
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

    # Relationships
    source: Mapped["Source"] = relationship(
        "Source",
        back_populates="evidence_items",
    )
    incident_links: Mapped[List["IncidentEvidenceLink"]] = relationship(
        "IncidentEvidenceLink",
        back_populates="evidence",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index(
            "idx_evidence_items_source_external",
            "source_id",
            "external_id",
            unique=True,
        ),
        Index("idx_evidence_items_published_at", published_at.desc()),
        Index("idx_evidence_items_domain", "publisher_domain"),
    )


class IncidentEvidenceLink(Base):
    __tablename__ = "incident_evidence_links"

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
    evidence_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("evidence_items.id", ondelete="CASCADE"),
        nullable=False,
    )
    link_role: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="SUPPORTING_EVIDENCE",
    )
    confidence_score: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=0.5,
    )
    match_explanation: Mapped[Optional[Dict[str, Any]]] = mapped_column(
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
        onupdate=func.now(),
        nullable=False,
    )

    # Relationships
    report: Mapped["WeatherReport"] = relationship(
        "WeatherReport",
        back_populates="evidence_links",
    )
    evidence: Mapped["EvidenceItem"] = relationship(
        "EvidenceItem",
        back_populates="incident_links",
    )

    __table_args__ = (
        UniqueConstraint(
            "report_id",
            "evidence_id",
            name="uq_incident_evidence_link",
        ),
        Index("idx_incident_evidence_report_id", "report_id"),
        Index("idx_incident_evidence_evidence_id", "evidence_id"),
    )
