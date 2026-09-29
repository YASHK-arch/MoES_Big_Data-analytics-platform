"""Community Feedback Loop API Router."""

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Path, Request, status
from sqlalchemy import String, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_optional_user
from app.db.session import get_db
from app.models.feedback import IncidentFeedback
from app.models.report import WeatherReport
from app.models.user import User
from app.schemas.feedback import (
    FeedbackSummaryData,
    FeedbackVoteRequest,
    FeedbackVoteResponse,
)
from app.services.incident_query_service import ID_PATTERN

router = APIRouter()


@router.post(
    "/{id}/feedback",
    response_model=FeedbackVoteResponse,
    status_code=status.HTTP_200_OK,
    summary="Submit Community 'Still Accurate?' Vote",
    description="Records a citizen confirm/dispute vote on an active incident report.",
)
async def submit_incident_feedback(
    request: Request,
    id: str = Path(..., min_length=3, max_length=64, description="Incident UUID or Tracking ID"),
    payload: FeedbackVoteRequest = ...,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_user),
) -> FeedbackVoteResponse:
    """Submit confirm or dispute vote for incident."""
    clean_id = id.strip()
    if not ID_PATTERN.match(clean_id):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "VALIDATION_ERROR", "message": f"Malformed identifier: {id}"},
        )

    vote_kind = payload.vote_type.upper()
    if vote_kind not in ("CONFIRM", "DISPUTE"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "VALIDATION_ERROR", "message": "vote_type must be CONFIRM or DISPUTE"},
        )

    # Resolve report
    stmt = select(WeatherReport).where(
        (WeatherReport.id.cast(String) == clean_id) | (WeatherReport.tracking_id == clean_id)
    )
    res = await db.execute(stmt)
    report = res.scalar_one_or_none()

    if not report:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "RESOURCE_NOT_FOUND", "message": f"Incident not found: {clean_id}"},
        )

    client_ip = request.client.host if request.client else "127.0.0.1"
    user_agent = request.headers.get("user-agent", "")[:255]

    # Check for existing vote by this user or client IP for this report
    if current_user:
        existing_stmt = (
            select(IncidentFeedback)
            .where(
                IncidentFeedback.report_id == report.id,
                (IncidentFeedback.user_id == current_user.id) | (IncidentFeedback.client_ip == client_ip),
            )
            .order_by(IncidentFeedback.created_at.desc())
            .limit(1)
        )
    else:
        existing_stmt = (
            select(IncidentFeedback)
            .where(
                IncidentFeedback.report_id == report.id,
                IncidentFeedback.client_ip == client_ip,
            )
            .order_by(IncidentFeedback.created_at.desc())
            .limit(1)
        )

    existing_res = await db.execute(existing_stmt)
    existing_vote = existing_res.scalars().first()

    if existing_vote:
        # Update existing vote if changed
        existing_vote.vote_type = vote_kind
        if current_user:
            existing_vote.user_id = current_user.id
        existing_vote.user_agent = user_agent
        existing_vote.created_at = datetime.now(timezone.utc)
    else:
        vote = IncidentFeedback(
            report_id=report.id,
            user_id=current_user.id if current_user else None,
            vote_type=vote_kind,
            client_ip=client_ip,
            user_agent=user_agent,
        )
        db.add(vote)

    await db.commit()

    # Aggregate counts
    confirm_stmt = select(func.count(IncidentFeedback.id)).where(
        IncidentFeedback.report_id == report.id,
        IncidentFeedback.vote_type == "CONFIRM",
    )
    dispute_stmt = select(func.count(IncidentFeedback.id)).where(
        IncidentFeedback.report_id == report.id,
        IncidentFeedback.vote_type == "DISPUTE",
    )

    conf_res = await db.execute(confirm_stmt)
    disp_res = await db.execute(dispute_stmt)

    conf_cnt = conf_res.scalar() or 0
    disp_cnt = disp_res.scalar() or 0

    return FeedbackVoteResponse(
        success=True,
        data=FeedbackSummaryData(
            report_id=report.id,
            confirm_count=conf_cnt,
            dispute_count=disp_cnt,
            user_voted=True,
            voted_type=vote_kind,
            last_voted_at=datetime.now(timezone.utc),
        ),
        meta={"timestamp": datetime.now(timezone.utc).isoformat()},
    )


@router.get(
    "/{id}/feedback",
    response_model=FeedbackVoteResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Community Feedback Summary",
    description="Returns aggregate confirm/dispute vote counts and client vote status for an incident.",
)
async def get_incident_feedback_summary(
    request: Request,
    id: str = Path(..., min_length=3, max_length=64, description="Incident UUID or Tracking ID"),
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_user),
) -> FeedbackVoteResponse:
    """Get feedback summary counts for incident."""
    clean_id = id.strip()
    if not ID_PATTERN.match(clean_id):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "VALIDATION_ERROR", "message": f"Malformed identifier: {id}"},
        )

    stmt = select(WeatherReport).where(
        (WeatherReport.id.cast(String) == clean_id) | (WeatherReport.tracking_id == clean_id)
    )
    res = await db.execute(stmt)
    report = res.scalar_one_or_none()

    if not report:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "RESOURCE_NOT_FOUND", "message": f"Incident not found: {clean_id}"},
        )

    client_ip = request.client.host if request.client else "127.0.0.1"

    # Check if user or client has already voted
    if current_user:
        client_vote_stmt = (
            select(IncidentFeedback)
            .where(
                IncidentFeedback.report_id == report.id,
                (IncidentFeedback.user_id == current_user.id) | (IncidentFeedback.client_ip == client_ip),
            )
            .order_by(IncidentFeedback.created_at.desc())
            .limit(1)
        )
    else:
        client_vote_stmt = (
            select(IncidentFeedback)
            .where(
                IncidentFeedback.report_id == report.id,
                IncidentFeedback.client_ip == client_ip,
            )
            .order_by(IncidentFeedback.created_at.desc())
            .limit(1)
        )
    client_vote_res = await db.execute(client_vote_stmt)
    client_vote = client_vote_res.scalars().first()

    confirm_stmt = select(func.count(IncidentFeedback.id)).where(
        IncidentFeedback.report_id == report.id,
        IncidentFeedback.vote_type == "CONFIRM",
    )
    dispute_stmt = select(func.count(IncidentFeedback.id)).where(
        IncidentFeedback.report_id == report.id,
        IncidentFeedback.vote_type == "DISPUTE",
    )

    conf_res = await db.execute(confirm_stmt)
    disp_res = await db.execute(dispute_stmt)

    conf_cnt = conf_res.scalar() or 0
    disp_cnt = disp_res.scalar() or 0

    return FeedbackVoteResponse(
        success=True,
        data=FeedbackSummaryData(
            report_id=report.id,
            confirm_count=conf_cnt,
            dispute_count=disp_cnt,
            user_voted=client_vote is not None,
            voted_type=client_vote.vote_type if client_vote else "",
            last_voted_at=client_vote.created_at if client_vote else datetime.now(timezone.utc),
        ),
        meta={"timestamp": datetime.now(timezone.utc).isoformat()},
    )
