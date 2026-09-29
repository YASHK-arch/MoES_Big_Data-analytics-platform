"""Operator Triage & Incident Verification API Router.

Exposes the ranked verification queue and authorized operator triage actions.
"""

import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_operator
from app.db.session import get_db
from app.models.user import User
from app.schemas.incident import IncidentListResponse, IncidentOperatorDetailResponse
from app.schemas.report import (
    PaginationMeta,
    ReportDuplicateRequest,
    ReportRejectRequest,
    ReportReviewRequest,
    ReportVerifyRequest,
)
from app.services.incident_query_service import ID_PATTERN, incident_query_service
from app.services.report_service import InvalidStateTransitionError, report_service

router = APIRouter()


@router.get(
    "/queue",
    response_model=IncidentListResponse,
    status_code=status.HTTP_200_OK,
    summary="Retrieve Operator Verification Queue",
    description="Priority-ranked queue of unverified reports ordered by severity and credibility.",
)
async def get_verification_queue(
    page: int = Query(default=1, ge=1, description="Page number starting at 1"),
    page_size: int = Query(default=20, ge=1, le=100, description="Records per page (max 100)"),
    priority: Optional[str] = Query(None, description="Priority filter (HIGH, NORMAL)"),
    category: Optional[str] = Query(None, description="Category code"),
    jurisdiction: Optional[str] = Query(None, description="Administrative jurisdiction name"),
    db: AsyncSession = Depends(get_db),
    current_operator: User = Depends(get_current_operator),
) -> IncidentListResponse:
    """Retrieve prioritized triage queue for authorized operators."""
    (
        summaries,
        total_records,
        total_pages,
        has_next,
        has_prev,
    ) = await incident_query_service.get_verification_queue(
        session=db,
        page=page,
        page_size=page_size,
        priority=priority,
        category=category,
        jurisdiction=jurisdiction,
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


@router.post(
    "/{id}/verify",
    response_model=IncidentOperatorDetailResponse,
    status_code=status.HTTP_200_OK,
    summary="Authorize and Verify Incident",
    description="Updates verification status to VERIFIED and records an immutable audit event.",
)
async def verify_incident(
    id: str = Path(..., min_length=3, max_length=64, description="Incident UUID or Tracking ID"),
    payload: Optional[ReportVerifyRequest] = None,
    db: AsyncSession = Depends(get_db),
    current_operator: User = Depends(get_current_operator),
) -> IncidentOperatorDetailResponse:
    """Authorize an incident as confirmed ground truth."""
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

    try:
        updated = await report_service.update_verification_status(
            session=db,
            report_id_or_tracking=clean_id,
            new_status="VERIFIED",
            notes=payload.notes if payload else None,
            action_metadata={"broadcast_alert": payload.broadcast_alert} if payload else None,
        )
    except InvalidStateTransitionError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "INVALID_STATE_TRANSITION",
                "message": e.message,
                "details": [
                    {
                        "current_status": e.current_status,
                        "target_status": e.target_status,
                    }
                ],
            },
        )
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "RESOURCE_NOT_FOUND",
                "message": f"Incident not found: {clean_id}",
                "details": [],
            },
        )

    detail = await incident_query_service.get_incident_detail(
        session=db, identifier=str(updated.id), is_operator=True
    )
    if detail is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Incident detail not found"
        )

    return IncidentOperatorDetailResponse(
        success=True,
        data=detail,  # type: ignore[arg-type]
        meta={
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "request_id": f"req_{uuid.uuid4().hex[:12]}",
        },
    )


@router.post(
    "/{id}/reject",
    response_model=IncidentOperatorDetailResponse,
    status_code=status.HTTP_200_OK,
    summary="Reject Incident as False / Hoax / Inaccurate",
    description="Updates verification status to REJECTED with reason code and records audit event.",
)
async def reject_incident(
    id: str = Path(..., min_length=3, max_length=64, description="Incident UUID or Tracking ID"),
    payload: Optional[ReportRejectRequest] = None,
    db: AsyncSession = Depends(get_db),
    current_operator: User = Depends(get_current_operator),
) -> IncidentOperatorDetailResponse:
    """Reject a false alarm or spam report."""
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

    try:
        updated = await report_service.update_verification_status(
            session=db,
            report_id_or_tracking=clean_id,
            new_status="REJECTED",
            notes=payload.notes if payload else None,
            action_metadata={"rejection_reason": payload.rejection_reason} if payload else None,
        )
    except InvalidStateTransitionError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "INVALID_STATE_TRANSITION",
                "message": e.message,
                "details": [
                    {
                        "current_status": e.current_status,
                        "target_status": e.target_status,
                    }
                ],
            },
        )
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "RESOURCE_NOT_FOUND",
                "message": f"Incident not found: {clean_id}",
                "details": [],
            },
        )

    detail = await incident_query_service.get_incident_detail(
        session=db, identifier=str(updated.id), is_operator=True
    )
    if detail is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Incident detail not found"
        )

    return IncidentOperatorDetailResponse(
        success=True,
        data=detail,  # type: ignore[arg-type]
        meta={
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "request_id": f"req_{uuid.uuid4().hex[:12]}",
        },
    )


@router.post(
    "/{id}/mark-duplicate",
    response_model=IncidentOperatorDetailResponse,
    status_code=status.HTTP_200_OK,
    summary="Mark Incident as Duplicate",
    description="Updates verification status to DUPLICATE with reference to primary incident.",
)
async def mark_duplicate_incident(
    id: str = Path(..., min_length=3, max_length=64, description="Incident UUID or Tracking ID"),
    payload: Optional[ReportDuplicateRequest] = None,
    db: AsyncSession = Depends(get_db),
    current_operator: User = Depends(get_current_operator),
) -> IncidentOperatorDetailResponse:
    """Mark an incident as a duplicate."""
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

    try:
        updated = await report_service.update_verification_status(
            session=db,
            report_id_or_tracking=clean_id,
            new_status="DUPLICATE",
            notes=payload.notes if payload else None,
            action_metadata={"primary_report_id": payload.primary_report_id} if payload else None,
        )
    except InvalidStateTransitionError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "INVALID_STATE_TRANSITION",
                "message": e.message,
                "details": [
                    {
                        "current_status": e.current_status,
                        "target_status": e.target_status,
                    }
                ],
            },
        )
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "RESOURCE_NOT_FOUND",
                "message": f"Incident not found: {clean_id}",
                "details": [],
            },
        )

    detail = await incident_query_service.get_incident_detail(
        session=db, identifier=str(updated.id), is_operator=True
    )
    if detail is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Incident detail not found"
        )

    return IncidentOperatorDetailResponse(
        success=True,
        data=detail,  # type: ignore[arg-type]
        meta={
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "request_id": f"req_{uuid.uuid4().hex[:12]}",
        },
    )


@router.post(
    "/{id}/review",
    response_model=IncidentOperatorDetailResponse,
    status_code=status.HTTP_200_OK,
    summary="Mark Incident Under Active Review",
    description="Updates verification status to UNDER_REVIEW.",
)
async def review_incident(
    id: str = Path(..., min_length=3, max_length=64, description="Incident UUID or Tracking ID"),
    payload: Optional[ReportReviewRequest] = None,
    db: AsyncSession = Depends(get_db),
    current_operator: User = Depends(get_current_operator),
) -> IncidentOperatorDetailResponse:
    """Mark an incident as actively being triaged."""
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

    try:
        updated = await report_service.update_verification_status(
            session=db,
            report_id_or_tracking=clean_id,
            new_status="UNDER_REVIEW",
            notes=payload.notes if payload else None,
        )
    except InvalidStateTransitionError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "INVALID_STATE_TRANSITION",
                "message": e.message,
                "details": [
                    {
                        "current_status": e.current_status,
                        "target_status": e.target_status,
                    }
                ],
            },
        )
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "RESOURCE_NOT_FOUND",
                "message": f"Incident not found: {clean_id}",
                "details": [],
            },
        )

    detail = await incident_query_service.get_incident_detail(
        session=db, identifier=str(updated.id), is_operator=True
    )
    if detail is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Incident detail not found"
        )

    return IncidentOperatorDetailResponse(
        success=True,
        data=detail,  # type: ignore[arg-type]
        meta={
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "request_id": f"req_{uuid.uuid4().hex[:12]}",
        },
    )
