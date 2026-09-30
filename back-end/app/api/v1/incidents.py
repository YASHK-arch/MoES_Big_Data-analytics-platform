"""Operational Incident Intelligence API Router.

Exposes bounded read resources for weather incidents, machine credibility breakdowns,
orchestration status, linked digital evidence, observation corroborations, and duplicate clusters.
"""

import uuid
from datetime import datetime, timezone
from typing import Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.schemas.credibility import IncidentCredibilityResponse
from app.schemas.duplicate import IncidentClusterDetailResponse
from app.schemas.evidence import IncidentEvidenceListResponse
from app.schemas.incident import (
    IncidentDetailOperator,
    IncidentDetailResponse,
    IncidentListResponse,
    IncidentOperatorDetailResponse,
)
from app.schemas.intelligence import IncidentIntelligenceStatusResponse
from app.schemas.observation import IncidentObservationListResponse
from app.schemas.report import PaginationMeta, SeverityType
from app.services.incident_query_service import ID_PATTERN, incident_query_service

router = APIRouter()


@router.get(
    "",
    response_model=IncidentListResponse,
    status_code=status.HTTP_200_OK,
    summary="List & Filter Operational Incidents",
    description="Paginated list of weather incidents with multi-criteria and geospatial filtering.",
)
async def list_incidents(
    page: int = Query(default=1, ge=1, description="Page number starting at 1"),
    page_size: int = Query(default=20, ge=1, le=100, description="Records per page (max 100)"),
    category: Optional[str] = Query(None, description="Canonical event category code"),
    severity: Optional[SeverityType] = Query(None, description="Severity level"),
    verification_status: Optional[str] = Query(
        None, description="Verification status or comma-separated statuses"
    ),
    min_credibility: Optional[float] = Query(
        None, ge=0.0, le=1.0, description="Minimum machine credibility score"
    ),
    max_credibility: Optional[float] = Query(
        None, ge=0.0, le=1.0, description="Maximum machine credibility score"
    ),
    readiness: Optional[str] = Query(
        None, description="Orchestration readiness (INTELLIGENCE_READY, INTELLIGENCE_PARTIAL, etc.)"
    ),
    from_date: Optional[datetime] = Query(None, description="Start date (ISO8601)"),
    to_date: Optional[datetime] = Query(None, description="End date (ISO8601)"),
    bbox: Optional[str] = Query(
        None,
        description="Bounding box in min_lon,min_lat,max_lon,max_lat format",
    ),
    sort_by: str = Query(
        default="occurred_at",
        pattern="^(occurred_at|credibility_score|created_at)$",
        description="Field to sort by",
    ),
    sort_order: str = Query(
        default="desc",
        pattern="^(asc|desc)$",
        description="Sort direction",
    ),
    hide_demo: bool = Query(
        default=False,
        description="Exclude demo/simulated incident records",
    ),
    db: AsyncSession = Depends(get_db),
) -> IncidentListResponse:
    """List weather incident summaries."""
    if from_date and to_date and from_date > to_date:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "VALIDATION_ERROR",
                "message": "Parameter 'from_date' cannot be later than 'to_date'.",
            },
        )

    parsed_bbox: Optional[Tuple[float, float, float, float]] = None
    if bbox:
        parts = bbox.split(",")
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

        parsed_bbox = (min_lon, min_lat, max_lon, max_lat)

    (
        summaries,
        total_records,
        total_pages,
        has_next,
        has_prev,
    ) = await incident_query_service.list_incidents(
        session=db,
        page=page,
        page_size=page_size,
        category=category,
        severity=severity,
        verification_status=verification_status,
        min_credibility=min_credibility,
        max_credibility=max_credibility,
        readiness=readiness,
        from_date=from_date,
        to_date=to_date,
        bbox=parsed_bbox,
        sort_by=sort_by,
        sort_order=sort_order,
        hide_demo=hide_demo,
    )

    return IncidentListResponse(
        success=True,
        data=summaries,
        pagination=PaginationMeta(
            page=page,
            page_size=page_size,
            total_records=total_records,
            total_pages=total_pages,
            has_next=has_next,
            has_prev=has_prev,
        ),
        meta={
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "request_id": f"req_{uuid.uuid4().hex[:12]}",
        },
    )


@router.get(
    "/{id}",
    response_model=IncidentDetailResponse,
    status_code=status.HTTP_200_OK,
    summary="Retrieve Bounded Incident Detail",
    description="Fetch operational incident details with bounded aggregate summaries.",
)
async def get_incident_detail(
    id: str = Path(..., min_length=3, max_length=64, description="Incident UUID or Tracking ID"),
    db: AsyncSession = Depends(get_db),
) -> IncidentDetailResponse:
    """Retrieve public bounded incident detail."""
    clean_id = id.strip()
    if not ID_PATTERN.match(clean_id):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "VALIDATION_ERROR",
                "message": f"Malformed incident identifier: '{id}'.",
                "details": [],
            },
        )

    detail = await incident_query_service.get_incident_detail(
        session=db,
        identifier=clean_id,
        is_operator=False,
    )

    if detail is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "RESOURCE_NOT_FOUND",
                "message": f"Weather incident with ID {clean_id} does not exist.",
                "details": [],
            },
        )

    return IncidentDetailResponse(
        success=True,
        data=detail,
        meta={
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "request_id": f"req_{uuid.uuid4().hex[:12]}",
        },
    )


@router.get(
    "/{id}/operator-detail",
    response_model=IncidentOperatorDetailResponse,
    status_code=status.HTTP_200_OK,
    summary="Retrieve Operator Incident Detail",
    description="Fetch operational incident details with audit history for authorized operators.",
)
async def get_operator_incident_detail(
    id: str = Path(..., min_length=3, max_length=64, description="Incident UUID or Tracking ID"),
    db: AsyncSession = Depends(get_db),
) -> IncidentOperatorDetailResponse:
    """Retrieve operator detail with verification audit history."""
    clean_id = id.strip()
    if not ID_PATTERN.match(clean_id):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "VALIDATION_ERROR",
                "message": f"Malformed incident identifier: '{id}'.",
                "details": [],
            },
        )

    detail = await incident_query_service.get_incident_detail(
        session=db,
        identifier=clean_id,
        is_operator=True,
    )

    if detail is None or not isinstance(detail, IncidentDetailOperator):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "RESOURCE_NOT_FOUND",
                "message": f"Weather incident with ID {clean_id} does not exist.",
                "details": [],
            },
        )

    return IncidentOperatorDetailResponse(
        success=True,
        data=detail,
        meta={
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "request_id": f"req_{uuid.uuid4().hex[:12]}",
        },
    )


@router.get(
    "/{id}/credibility",
    response_model=IncidentCredibilityResponse,
    status_code=status.HTTP_200_OK,
    summary="Retrieve Machine Credibility Breakdown",
    description="Fetch credibility score, explainable justification, positive/negative drivers.",
)
async def get_incident_credibility(
    id: str = Path(..., min_length=3, max_length=64, description="Incident UUID or Tracking ID"),
    db: AsyncSession = Depends(get_db),
) -> IncidentCredibilityResponse:
    """Retrieve credibility evaluation breakdown."""
    clean_id = id.strip()
    if not ID_PATTERN.match(clean_id):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "VALIDATION_ERROR",
                "message": f"Malformed identifier: {id}",
                "details": [],
            },
        )

    data = await incident_query_service.get_incident_credibility(session=db, identifier=clean_id)
    if data is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "RESOURCE_NOT_FOUND",
                "message": f"Incident not found: {clean_id}",
                "details": [],
            },
        )

    return IncidentCredibilityResponse(
        success=True,
        data=data,
        meta={
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "request_id": f"req_{uuid.uuid4().hex[:12]}",
        },
    )


@router.get(
    "/{id}/intelligence",
    response_model=IncidentIntelligenceStatusResponse,
    status_code=status.HTTP_200_OK,
    summary="Retrieve Intelligence Orchestration Status",
    description="Fetch per-stage pipeline execution statuses, readiness, and retry metadata.",
)
async def get_incident_intelligence_status(
    id: str = Path(..., min_length=3, max_length=64, description="Incident UUID or Tracking ID"),
    db: AsyncSession = Depends(get_db),
) -> IncidentIntelligenceStatusResponse:
    """Retrieve pipeline orchestration readiness."""
    clean_id = id.strip()
    if not ID_PATTERN.match(clean_id):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "VALIDATION_ERROR",
                "message": f"Malformed identifier: {id}",
                "details": [],
            },
        )

    data = await incident_query_service.get_incident_intelligence_status(
        session=db, identifier=clean_id
    )
    if data is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "RESOURCE_NOT_FOUND",
                "message": f"Incident not found: {clean_id}",
                "details": [],
            },
        )

    return IncidentIntelligenceStatusResponse(
        success=True,
        data=data,
        meta={
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "request_id": f"req_{uuid.uuid4().hex[:12]}",
        },
    )


@router.get(
    "/{id}/evidence",
    response_model=IncidentEvidenceListResponse,
    status_code=status.HTTP_200_OK,
    summary="Retrieve Linked Digital Evidence Items",
    description="Paginated digital evidence articles and social posts linked to the incident.",
)
async def get_incident_evidence(
    id: str = Path(..., min_length=3, max_length=64, description="Incident UUID or Tracking ID"),
    page: int = Query(default=1, ge=1, description="Page number starting at 1"),
    page_size: int = Query(default=20, ge=1, le=50, description="Records per page (max 50)"),
    db: AsyncSession = Depends(get_db),
) -> IncidentEvidenceListResponse:
    """Retrieve paginated linked evidence items."""
    clean_id = id.strip()
    if not ID_PATTERN.match(clean_id):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "VALIDATION_ERROR",
                "message": f"Malformed identifier: {id}",
                "details": [],
            },
        )

    (
        items,
        total_records,
        total_pages,
        has_next,
        has_prev,
    ) = await incident_query_service.get_incident_evidence(
        session=db, identifier=clean_id, page=page, page_size=page_size
    )
    if items is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "RESOURCE_NOT_FOUND",
                "message": f"Incident not found: {clean_id}",
                "details": [],
            },
        )

    return IncidentEvidenceListResponse(
        success=True,
        data=items,
        pagination=PaginationMeta(
            page=page,
            page_size=page_size,
            total_records=total_records,
            total_pages=total_pages,
            has_next=has_next,
            has_prev=has_prev,
        ),
        meta={
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "request_id": f"req_{uuid.uuid4().hex[:12]}",
        },
    )


@router.get(
    "/{id}/observations",
    response_model=IncidentObservationListResponse,
    status_code=status.HTTP_200_OK,
    summary="Retrieve Corroborating Physical Observations",
    description="Paginated weather AWS and CWC gauge readings corroborating the incident.",
)
async def get_incident_observations(
    id: str = Path(..., min_length=3, max_length=64, description="Incident UUID or Tracking ID"),
    page: int = Query(default=1, ge=1, description="Page number starting at 1"),
    page_size: int = Query(default=20, ge=1, le=50, description="Records per page (max 50)"),
    db: AsyncSession = Depends(get_db),
) -> IncidentObservationListResponse:
    """Retrieve paginated physical observation corroborations."""
    clean_id = id.strip()
    if not ID_PATTERN.match(clean_id):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "VALIDATION_ERROR",
                "message": f"Malformed identifier: {id}",
                "details": [],
            },
        )

    (
        items,
        total_records,
        total_pages,
        has_next,
        has_prev,
    ) = await incident_query_service.get_incident_observations(
        session=db, identifier=clean_id, page=page, page_size=page_size
    )
    if items is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "RESOURCE_NOT_FOUND",
                "message": f"Incident not found: {clean_id}",
                "details": [],
            },
        )

    return IncidentObservationListResponse(
        success=True,
        data=items,
        pagination=PaginationMeta(
            page=page,
            page_size=page_size,
            total_records=total_records,
            total_pages=total_pages,
            has_next=has_next,
            has_prev=has_prev,
        ),
        meta={
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "request_id": f"req_{uuid.uuid4().hex[:12]}",
        },
    )


@router.get(
    "/{id}/cluster",
    response_model=IncidentClusterDetailResponse,
    status_code=status.HTTP_200_OK,
    summary="Retrieve Duplicate Cluster Details",
    description="Fetch duplicate cluster topology, primary anchor, and member incidents.",
)
async def get_incident_cluster(
    id: str = Path(..., min_length=3, max_length=64, description="Incident UUID or Tracking ID"),
    db: AsyncSession = Depends(get_db),
) -> IncidentClusterDetailResponse:
    """Retrieve duplicate cluster topology."""
    clean_id = id.strip()
    if not ID_PATTERN.match(clean_id):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "VALIDATION_ERROR",
                "message": f"Malformed identifier: {id}",
                "details": [],
            },
        )

    data = await incident_query_service.get_incident_cluster(session=db, identifier=clean_id)
    if data is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "RESOURCE_NOT_FOUND",
                "message": f"Incident not found: {clean_id}",
                "details": [],
            },
        )

    return IncidentClusterDetailResponse(
        success=True,
        data=data,
        meta={
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "request_id": f"req_{uuid.uuid4().hex[:12]}",
        },
    )
