"""Operational Route Hazard Check API Router."""

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.schemas.route import RouteCheckRequest, RouteCheckResponse
from app.services.route_service import route_check_service

router = APIRouter()


@router.post(
    "/check",
    response_model=RouteCheckResponse,
    status_code=status.HTTP_200_OK,
    summary="Path Corridor Hazard & Blockage Check",
    description="Spatial buffer intersection check between origin and destination against active verified hazards.",
)
async def check_route_blockage(
    payload: RouteCheckRequest,
    db: AsyncSession = Depends(get_db),
) -> RouteCheckResponse:
    """Perform PostGIS corridor check along route path."""
    data = await route_check_service.check_route_corridor(session=db, payload=payload)
    return RouteCheckResponse(success=True, data=data)
