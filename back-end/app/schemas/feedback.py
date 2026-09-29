"""Pydantic schemas for Community Feedback Loop."""

import uuid
from datetime import datetime
from typing import Any, Dict

from pydantic import BaseModel, Field


class FeedbackVoteRequest(BaseModel):
    """Payload for submitting community confirmation or dispute vote."""

    vote_type: str = Field(..., description="CONFIRM or DISPUTE")


class FeedbackSummaryData(BaseModel):
    """Aggregated feedback count summary for an incident."""

    report_id: uuid.UUID
    confirm_count: int
    dispute_count: int
    user_voted: bool = False
    voted_type: str = ""
    last_voted_at: datetime


class FeedbackVoteResponse(BaseModel):
    """API envelope for feedback vote submission."""

    success: bool = True
    data: FeedbackSummaryData
    meta: Dict[str, Any] = Field(default_factory=dict)
