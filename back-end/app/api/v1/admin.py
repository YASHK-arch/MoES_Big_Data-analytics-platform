import csv
import io
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import AsyncGenerator, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_operator
from app.db.session import get_db
from app.models.audit import AuditLog
from app.models.outbox import RealtimeOutbox
from app.models.report import WeatherReport
from app.models.user import User
from app.schemas.admin import (
    AuditLogItem,
    AuditLogListResponse,
    BulkVerificationRequest,
    BulkVerificationResponse,
    BulkVerificationResponseData,
)
from app.schemas.report import PaginationMeta
from app.services.report_service import (
    ALLOWED_VERIFICATION_TRANSITIONS,
    InvalidStateTransitionError,
    report_service,
)

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get(
    "/export/csv",
    summary="Export Incidents as CSV (Operator Only, Streamed)",
    description="Stream up to 50,000 incident rows as a downloadable CSV file.",
)
async def export_incidents_csv(
    limit: int = Query(default=1000, ge=1, le=50000, description="Max export rows (up to 50,000)"),
    category: Optional[str] = Query(None, description="Filter by event category"),
    status_filter: Optional[str] = Query(None, alias="status", description="Filter by verification status"),
    severity: Optional[str] = Query(None, description="Filter by severity level"),
    hide_demo: bool = Query(default=False, description="Exclude simulated demo records"),
    db: AsyncSession = Depends(get_db),
    current_operator: User = Depends(get_current_operator),
) -> StreamingResponse:
    """Streamed CSV export restricted to authorized operators."""
    stmt = select(WeatherReport).order_by(WeatherReport.occurred_at.desc())

    if hide_demo:
        stmt = stmt.where(WeatherReport.is_demo.is_(False))
    if category:
        stmt = stmt.where(WeatherReport.reported_category == category.upper())
    if status_filter:
        statuses = [s.strip().upper() for s in status_filter.split(",")]
        stmt = stmt.where(WeatherReport.verification_status.in_(statuses))
    if severity:
        stmt = stmt.where(WeatherReport.severity == severity.upper())

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    filename = f"incidents_export_{timestamp}.csv"

    async def csv_generator() -> AsyncGenerator[str, None]:
        output = io.StringIO()
        writer = csv.writer(output)

        # Header row
        writer.writerow([
            "id",
            "tracking_id",
            "title",
            "category",
            "severity",
            "status",
            "credibility_score",
            "latitude",
            "longitude",
            "location_name",
            "occurred_at",
            "is_demo",
        ])
        yield output.getvalue()
        output.seek(0)
        output.truncate(0)

        offset = 0
        batch_size = 1000
        while offset < limit:
            chunk_size = min(batch_size, limit - offset)
            chunk_stmt = stmt.limit(chunk_size).offset(offset)
            res = await db.execute(chunk_stmt)
            reports = list(res.scalars().all())

            if not reports:
                break

            for r in reports:
                writer.writerow([
                    str(r.id),
                    r.tracking_id,
                    r.title,
                    r.reported_category,
                    r.severity,
                    r.verification_status,
                    f"{r.credibility_score:.2f}" if r.credibility_score is not None else "",
                    f"{r.latitude:.6f}" if r.latitude is not None else "",
                    f"{r.longitude:.6f}" if r.longitude is not None else "",
                    r.location_name or "",
                    r.occurred_at.isoformat() if r.occurred_at else "",
                    str(r.is_demo),
                ])
                yield output.getvalue()
                output.seek(0)
                output.truncate(0)

            offset += len(reports)
            if len(reports) < chunk_size:
                break

    return StreamingResponse(
        csv_generator(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get(
    "/export/geojson",
    summary="Export Incidents as GeoJSON (Operator Only, Streamed)",
    description="Stream up to 50,000 incident features as a valid GeoJSON FeatureCollection.",
)
async def export_incidents_geojson(
    limit: int = Query(default=1000, ge=1, le=50000, description="Max export rows (up to 50,000)"),
    category: Optional[str] = Query(None, description="Filter by event category"),
    status_filter: Optional[str] = Query(None, alias="status", description="Filter by verification status"),
    severity: Optional[str] = Query(None, description="Filter by severity level"),
    hide_demo: bool = Query(default=False, description="Exclude simulated demo records"),
    db: AsyncSession = Depends(get_db),
    current_operator: User = Depends(get_current_operator),
) -> StreamingResponse:
    """Streamed GeoJSON export restricted to authorized operators."""
    stmt = select(WeatherReport).order_by(WeatherReport.occurred_at.desc())

    if hide_demo:
        stmt = stmt.where(WeatherReport.is_demo.is_(False))
    if category:
        stmt = stmt.where(WeatherReport.reported_category == category.upper())
    if status_filter:
        statuses = [s.strip().upper() for s in status_filter.split(",")]
        stmt = stmt.where(WeatherReport.verification_status.in_(statuses))
    if severity:
        stmt = stmt.where(WeatherReport.severity == severity.upper())

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    filename = f"incidents_export_{timestamp}.geojson"

    async def geojson_generator() -> AsyncGenerator[str, None]:
        yield '{"type": "FeatureCollection", "features": [\n'

        offset = 0
        batch_size = 1000
        first_feature = True

        while offset < limit:
            chunk_size = min(batch_size, limit - offset)
            chunk_stmt = stmt.limit(chunk_size).offset(offset)
            res = await db.execute(chunk_stmt)
            reports = list(res.scalars().all())

            if not reports:
                break

            for r in reports:
                geometry = None
                if r.latitude is not None and r.longitude is not None:
                    geometry = {
                        "type": "Point",
                        "coordinates": [float(r.longitude), float(r.latitude)],
                    }

                feature = {
                    "type": "Feature",
                    "geometry": geometry,
                    "properties": {
                        "id": str(r.id),
                        "tracking_id": r.tracking_id,
                        "title": r.title,
                        "category": r.reported_category,
                        "severity": r.severity,
                        "status": r.verification_status,
                        "credibility_score": r.credibility_score,
                        "location_name": r.location_name,
                        "occurred_at": r.occurred_at.isoformat() if r.occurred_at else None,
                        "is_demo": r.is_demo,
                    },
                }

                feat_json = json.dumps(feature)
                if not first_feature:
                    yield ",\n" + feat_json
                else:
                    yield feat_json
                    first_feature = False

            offset += len(reports)
            if len(reports) < chunk_size:
                break

        yield "\n]}"

    return StreamingResponse(
        geojson_generator(),
        media_type="application/geo+json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post(
    "/verification/bulk",
    response_model=BulkVerificationResponse,
    status_code=status.HTTP_200_OK,
    summary="Bulk Verify or Reject Incidents (Operator Only)",
    description="Batch process up to 100 incidents in a single transaction with audit row creation.",
)
async def bulk_verification_action(
    payload: BulkVerificationRequest,
    db: AsyncSession = Depends(get_db),
    current_operator: User = Depends(get_current_operator),
) -> BulkVerificationResponse:
    """Execute bulk verification or rejection in an atomic transaction.

    Uses a two-pass strategy to guarantee true atomicity:
    - Pass 1: Resolve all report objects and validate transitions with NO writes.
              If any ID is missing or the transition is invalid the entire batch
              is rejected immediately and no data is modified.
    - Pass 2: Apply all mutations in a single session and commit once.
    """
    action_clean = payload.action.strip().upper()
    if action_clean not in ("VERIFY", "REJECT"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "INVALID_ACTION",
                "message": f"Action '{payload.action}' invalid. Allowed: 'VERIFY', 'REJECT'.",
            },
        )

    target_status = "VERIFIED" if action_clean == "VERIFY" else "REJECTED"

    # ── Pass 1: Resolve & validate all reports (read-only, no commits) ──────────
    resolved: list[WeatherReport] = []
    try:
        for ident in payload.incident_ids:
            clean_ident = ident.strip()
            report = await report_service.get_report_by_id_or_tracking(db, clean_ident)
            if report is None:
                raise ValueError(f"Report not found: {clean_ident}")
            previous_status = (report.verification_status or "PENDING").upper()
            allowed_targets = ALLOWED_VERIFICATION_TRANSITIONS.get(previous_status, set())
            if target_status not in allowed_targets:
                raise InvalidStateTransitionError(
                    current_status=previous_status,
                    target_status=target_status,
                    message=(
                        f"Cannot transition report '{clean_ident}' "
                        f"from '{previous_status}' to '{target_status}'."
                    ),
                )
            resolved.append(report)
    except (ValueError, InvalidStateTransitionError) as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "BULK_ACTION_FAILED",
                "message": f"Bulk {action_clean} aborted: {e}",
            },
        )

    # ── Pass 2: Apply mutations and commit once ──────────────────────────────────
    affected_ids: list[str] = []
    try:
        for report in resolved:
            await report_service.update_verification_status(
                session=db,
                report_id_or_tracking=str(report.id),
                new_status=target_status,
                notes=payload.notes,
                action_metadata={
                    "bulk": True,
                    "rejection_reason": payload.rejection_reason,
                    "operator_email": current_operator.email,
                },
                commit=False,
            )

            audit_log = AuditLog(
                user_id=current_operator.id,
                action=f"BULK_{action_clean}",
                entity_type="WEATHER_REPORT",
                entity_id=report.id,
                payload={
                    "tracking_id": report.tracking_id,
                    "action": action_clean,
                    "target_status": target_status,
                    "notes": payload.notes,
                    "rejection_reason": payload.rejection_reason,
                },
            )
            db.add(audit_log)
            affected_ids.append(str(report.id))

        await db.flush()
        outbox_result = await db.execute(
            select(RealtimeOutbox).where(
                RealtimeOutbox.entity_id.in_(affected_ids),
                RealtimeOutbox.event_type == "report.verification_changed",
                RealtimeOutbox.status == "PENDING",
            )
        )
        staged_outbox_rows = list(outbox_result.scalars().all())
        await db.commit()

        for outbox_row in staged_outbox_rows:
            await report_service.realtime_svc.publish_staged_outbox(outbox_row)
    except Exception as e:
        await db.rollback()
        logger.error(f"Bulk action failed unexpectedly: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"code": "INTERNAL_SERVER_ERROR", "message": "Bulk action processing failed."},
        )

    return BulkVerificationResponse(
        success=True,
        data=BulkVerificationResponseData(
            processed_count=len(affected_ids),
            action=action_clean,
            affected_ids=affected_ids,
        ),
        meta={
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "operator_id": str(current_operator.id),
        },
    )


@router.get(
    "/audit-logs",
    response_model=AuditLogListResponse,
    status_code=status.HTTP_200_OK,
    summary="Retrieve Operator Audit Logs (Operator Only)",
    description="Paginated list of system and operator triage audit log records.",
)
async def get_audit_logs(
    page: int = Query(default=1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(default=20, ge=1, le=100, description="Records per page (max 100)"),
    action: Optional[str] = Query(None, description="Filter by action code"),
    entity_type: Optional[str] = Query(None, description="Filter by entity type"),
    user_id: Optional[uuid.UUID] = Query(None, description="Filter by operator/user UUID"),
    db: AsyncSession = Depends(get_db),
    current_operator: User = Depends(get_current_operator),
) -> AuditLogListResponse:
    """Retrieve paginated audit logs for operator and admin dashboard."""
    base_stmt = select(AuditLog).options(selectinload(AuditLog.user))

    if action:
        base_stmt = base_stmt.where(AuditLog.action.ilike(f"%{action.strip()}%"))
    if entity_type:
        base_stmt = base_stmt.where(AuditLog.entity_type == entity_type.strip().upper())
    if user_id:
        base_stmt = base_stmt.where(AuditLog.user_id == user_id)

    # Count total
    count_stmt = select(func.count()).select_from(base_stmt.subquery())
    count_res = await db.execute(count_stmt)
    total_records = count_res.scalar_one()

    # Pagination calculation
    offset = (page - 1) * page_size
    paged_stmt = base_stmt.order_by(AuditLog.created_at.desc()).offset(offset).limit(page_size)
    paged_res = await db.execute(paged_stmt)
    records = list(paged_res.scalars().all())

    items = [
        AuditLogItem(
            id=r.id,
            user_id=r.user_id,
            user_email=r.user.email if r.user else None,
            action=r.action,
            entity_type=r.entity_type,
            entity_id=r.entity_id,
            ip_address=r.ip_address,
            payload=r.payload,
            created_at=r.created_at,
        )
        for r in records
    ]

    total_pages = (total_records + page_size - 1) // page_size if total_records > 0 else 1

    return AuditLogListResponse(
        success=True,
        data=items,
        pagination=PaginationMeta(
            page=page,
            page_size=page_size,
            total_records=total_records,
            total_pages=total_pages,
            has_next=page < total_pages,
            has_prev=page > 1,
        ),
        meta={"timestamp": datetime.now(timezone.utc).isoformat()},
    )
