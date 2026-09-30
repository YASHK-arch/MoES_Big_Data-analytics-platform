"""Transactional Outbox SQLAlchemy model for reliable real-time event delivery.

Guarantees atomicity between primary database mutations (reports, verifications, intelligence)
and outbound real-time event dispatching.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Dict, Optional

from sqlalchemy import DateTime, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class RealtimeOutbox(Base):
    """Persistent outbox row written atomically with domain transactions."""

    __tablename__ = "realtime_outbox"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        unique=True,
    )
    event_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )
    entity_id: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )
    tracking_id: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
    )
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    payload: Mapped[Dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="PENDING",
    )
    attempts: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    max_attempts: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=5,
    )
    last_error: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    published_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    next_retry_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
    )

    __table_args__ = (
        Index("idx_realtime_outbox_event_id", "event_id", unique=True),
        Index("idx_realtime_outbox_event_type", "event_type"),
        Index("idx_realtime_outbox_entity_id", "entity_id"),
        Index("idx_realtime_outbox_status", "status"),
        Index("idx_realtime_outbox_created_at", "created_at"),
        Index(
            "idx_realtime_outbox_pending_retry",
            "status",
            "next_retry_at",
            "created_at",
        ),
    )
