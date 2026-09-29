import uuid
from datetime import datetime
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import Boolean, DateTime, Float, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.audit import AuditLog
    from app.models.verification import VerificationEvent


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    email: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        nullable=False,
        index=True,
    )
    full_name: Mapped[str] = mapped_column(
        String(150),
        nullable=False,
    )
    hashed_password: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    role: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="CITIZEN",
    )
    jurisdiction_code: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
    )
    home_location_lat: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
    )
    home_location_lng: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
    )
    home_location_name: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
    )
    alert_radius_km: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
        default=25.0,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
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
    verification_events: Mapped[List["VerificationEvent"]] = relationship(
        "VerificationEvent",
        back_populates="user",
    )
    audit_logs: Mapped[List["AuditLog"]] = relationship(
        "AuditLog",
        back_populates="user",
    )
