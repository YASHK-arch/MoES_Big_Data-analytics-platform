"""IncidentFeedback model for citizen 'Still Accurate?' community crowd signals."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.base import Base


class IncidentFeedback(Base):
    """Crowd validation vote (confirm / dispute) for active weather incident reports."""

    __tablename__ = "incident_feedback"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    report_id = Column(UUID(as_uuid=True), ForeignKey("weather_reports.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    vote_type = Column(String(20), nullable=False)  # CONFIRM, DISPUTE
    client_ip = Column(String(45), nullable=True)
    user_agent = Column(String(255), nullable=True)

    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    # Relationships
    report = relationship("WeatherReport", backref="feedback_votes")

    __table_args__ = (
        Index("idx_feedback_report_id", "report_id"),
        Index("idx_feedback_user_id", "user_id"),
    )
