"""Dashboard Aggregation API Router.

Provides real-time SQL-aggregated situational awareness metrics, severity distributions,
category breakdowns, and diurnal activity summaries.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache import get_or_compute
from app.db.session import get_db
from app.schemas.analytics import DashboardSummaryResponse
from app.services.incident_query_service import incident_query_service

router = APIRouter()


def _parse_bbox(bbox_str: Optional[str]) -> Optional[Tuple[float, float, float, float]]:
    """Validate and parse a geographic bounding box query string."""
    if not bbox_str:
        return None

    parts = bbox_str.split(",")
    if len(parts) != 4:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "VALIDATION_ERROR",
                "message": "Invalid bbox format. Expected 'min_lon,min_lat,max_lon,max_lat'.",
            },
        )

    try:
        min_lon, min_lat, max_lon, max_lat = (float(p.strip()) for p in parts)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "VALIDATION_ERROR",
                "message": "Invalid bbox coordinates. Values must be numeric floats.",
            },
        )

    if not (
        -180.0 <= min_lon <= 180.0
        and -180.0 <= max_lon <= 180.0
        and -90.0 <= min_lat <= 90.0
        and -90.0 <= max_lat <= 90.0
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "VALIDATION_ERROR",
                "message": "Bounding box coordinates out of valid geographic ranges.",
            },
        )

    if min_lon > max_lon or min_lat > max_lat:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "VALIDATION_ERROR",
                "message": "Invalid bbox range: min values must be <= max values.",
            },
        )

    if (max_lon - min_lon) > 10.0 or (max_lat - min_lat) > 10.0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "VALIDATION_ERROR",
                "message": "Bounding box dimensions exceed maximum allowed span of 10 degrees.",
            },
        )

    return (min_lon, min_lat, max_lon, max_lat)


@router.get(
    "/summary",
    response_model=DashboardSummaryResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Dashboard Metric Summary",
    description=(
        "Aggregated situational KPI metrics, severity breakdowns, "
        "category distributions, and diurnal activity."
    ),
)
async def get_dashboard_summary(
    time_range: Optional[str] = Query("24h", description="Time range: 24h, 48h, 7d, 30d, all"),
    category: Optional[str] = Query(None, description="Event category code"),
    severity: Optional[str] = Query(None, description="Severity: LOW, MODERATE, HIGH, SEVERE, ALL"),
    status_filter: Optional[str] = Query(
        None, alias="status", description="Verification status filter"
    ),
    bbox: Optional[str] = Query(
        None, description="Bounding box in min_lon,min_lat,max_lon,max_lat format"
    ),
    hide_demo: bool = Query(default=False, description="Exclude demo/simulated incident records"),
    db: AsyncSession = Depends(get_db),
) -> DashboardSummaryResponse:
    """Retrieve SQL-aggregated summary metrics for dashboard situational awareness."""
    if time_range and time_range.strip().lower() not in ("24h", "48h", "7d", "30d", "all"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "VALIDATION_ERROR",
                "message": (
                    f"Invalid time_range '{time_range}'. Allowed values: 24h, 48h, 7d, 30d, all."
                ),
            },
        )

    if severity and severity.strip().upper() not in (
        "LOW",
        "MODERATE",
        "HIGH",
        "SEVERE",
        "ALL",
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "VALIDATION_ERROR",
                "message": (
                    f"Invalid severity '{severity}'. "
                    "Allowed values: LOW, MODERATE, HIGH, SEVERE, ALL."
                ),
            },
        )

    parsed_bbox = _parse_bbox(bbox)

    params = {
        "time_range": time_range.strip().lower() if time_range else "24h",
        "category": category,
        "severity": severity,
        "status": status_filter,
        "bbox": bbox,
        "hide_demo": hide_demo,
    }

    async def _compute():
        data = await incident_query_service.get_dashboard_summary(
            session=db,
            time_range=time_range.strip().lower() if time_range else "24h",
            category=category,
            severity=severity,
            verification_status=status_filter,
            bbox=parsed_bbox,
            hide_demo=hide_demo,
        )
        return data.model_dump(mode="json")

    summary_data = await get_or_compute(
        endpoint="dashboard:summary",
        query_params=params,
        compute_fn=_compute,
    )

    return DashboardSummaryResponse(
        success=True,
        data=summary_data,
        meta={"timestamp": datetime.now(timezone.utc).isoformat()},
    )
