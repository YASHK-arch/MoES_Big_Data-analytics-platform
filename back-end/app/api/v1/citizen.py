"""Citizen Personal Profile, Saved Location, and Reports History API Router."""

from datetime import datetime, timezone
from typing import Any, Dict

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_citizen
from app.db.session import get_db
from app.models.feedback import IncidentFeedback
from app.models.report import WeatherReport
from app.models.user import User
from app.schemas.auth import UpdateLocationRequest, UserProfile

router = APIRouter()


@router.get(
    "/me",
    response_model=UserProfile,
    status_code=status.HTTP_200_OK,
    summary="Get Citizen Profile",
    description="Retrieves the authenticated citizen's profile and persisted location preferences.",
)
async def get_citizen_profile(
    citizen: User = Depends(get_current_citizen),
) -> UserProfile:
    """Retrieve citizen profile."""
    return UserProfile(
        id=citizen.id,
        email=citizen.email,
        full_name=citizen.full_name,
        role=citizen.role,
        jurisdiction_code=citizen.jurisdiction_code,
        home_location_lat=citizen.home_location_lat,
        home_location_lng=citizen.home_location_lng,
        home_location_name=citizen.home_location_name,
        alert_radius_km=citizen.alert_radius_km or 25.0,
    )


@router.put(
    "/me/location",
    response_model=UserProfile,
    status_code=status.HTTP_200_OK,
    summary="Save Citizen Home Location Preferences",
    description="Persists citizen's home latitude, longitude, and custom proximity alert radius to database so settings follow their account across devices.",
)
async def update_citizen_location(
    payload: UpdateLocationRequest,
    citizen: User = Depends(get_current_citizen),
    db: AsyncSession = Depends(get_db),
) -> UserProfile:
    """Persist citizen location and risk radius preferences."""
    citizen.home_location_lat = payload.latitude
    citizen.home_location_lng = payload.longitude
    citizen.home_location_name = payload.location_name
    if payload.alert_radius_km is not None:
        citizen.alert_radius_km = payload.alert_radius_km

    await db.commit()
    await db.refresh(citizen)

    return UserProfile(
        id=citizen.id,
        email=citizen.email,
        full_name=citizen.full_name,
        role=citizen.role,
        jurisdiction_code=citizen.jurisdiction_code,
        home_location_lat=citizen.home_location_lat,
        home_location_lng=citizen.home_location_lng,
        home_location_name=citizen.home_location_name,
        alert_radius_km=citizen.alert_radius_km or 25.0,
    )


@router.get(
    "/my-reports",
    status_code=status.HTTP_200_OK,
    summary="List Citizen's Submitted Weather Reports",
    description="Returns all eyewitness reports submitted by this authenticated citizen account with real-time verification and credibility status.",
)
async def list_my_reports(
    citizen: User = Depends(get_current_citizen),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Retrieve all reports submitted by this citizen."""
    stmt = (
        select(WeatherReport)
        .options(selectinload(WeatherReport.category))
        .where(WeatherReport.user_id == citizen.id)
        .order_by(WeatherReport.occurred_at.desc())
    )
    res = await db.execute(stmt)
    reports = res.scalars().all()

    items = []
    for r in reports:
        cat = r.category.category_code if r.category else (r.reported_category or "WEATHER_EVENT")
        items.append(
            {
                "id": str(r.id),
                "tracking_id": r.tracking_id,
                "title": r.title,
                "category": cat,
                "severity": r.severity,
                "verification_status": r.verification_status,
                "credibility_score": r.credibility_score,
                "credibility_reason": r.credibility_reason,
                "location_name": r.location_name,
                "latitude": r.latitude,
                "longitude": r.longitude,
                "occurred_at": r.occurred_at.isoformat() if r.occurred_at else None,
            }
        )

    return {
        "success": True,
        "data": items,
        "meta": {
            "total_reports": len(items),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    }


@router.get(
    "/my-feedback",
    status_code=status.HTTP_200_OK,
    summary="List Citizen's Community 'Still Accurate?' Votes",
    description="Returns all incidents where this citizen has cast a community verification vote.",
)
async def list_my_feedback(
    citizen: User = Depends(get_current_citizen),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Retrieve community feedback votes cast by this citizen."""
    stmt = (
        select(IncidentFeedback, WeatherReport)
        .join(WeatherReport, IncidentFeedback.report_id == WeatherReport.id)
        .where(IncidentFeedback.user_id == citizen.id)
        .order_by(IncidentFeedback.created_at.desc())
    )
    res = await db.execute(stmt)
    rows = res.all()

    items = []
    for vote, report in rows:
        items.append(
            {
                "feedback_id": str(vote.id),
                "vote_type": vote.vote_type,
                "voted_at": vote.created_at.isoformat(),
                "incident": {
                    "id": str(report.id),
                    "tracking_id": report.tracking_id,
                    "title": report.title,
                    "severity": report.severity,
                    "verification_status": report.verification_status,
                },
            }
        )

    return {
        "success": True,
        "data": items,
        "meta": {
            "total_votes": len(items),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    }
