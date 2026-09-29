"""Relief Center & Emergency Shelter API Router."""

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from geoalchemy2.elements import WKTElement
from sqlalchemy import cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_operator
from app.db.session import get_db
from app.models.relief_center import ReliefCenter
from app.models.user import User
from app.schemas.relief_center import (
    ReliefCenterCreateRequest,
    ReliefCenterItem,
    ReliefCenterListResponse,
    ReliefCenterUpdateRequest,
)

router = APIRouter()


@router.get(
    "",
    response_model=ReliefCenterListResponse,
    status_code=status.HTTP_200_OK,
    summary="Query Nearby Emergency Relief Centers & Shelters",
    description="Returns active disaster relief centers, hospitals, and shelters within spatial radius of citizen location.",
)
async def get_nearby_relief_centers(
    lat: float = Query(..., ge=-90.0, le=90.0, description="Latitude"),
    lng: float = Query(..., ge=-180.0, le=180.0, description="Longitude"),
    radius_km: float = Query(default=50.0, ge=1.0, le=500.0, description="Search radius in kilometers"),
    center_type: str = Query(default="ALL", description="Filter by SHELTER, HOSPITAL, RELIEF_CAMP, or ALL"),
    db: AsyncSession = Depends(get_db),
) -> ReliefCenterListResponse:
    """Fetch nearby active relief centers ordered by proximity."""
    user_point = func.ST_SetSRID(func.ST_MakePoint(lng, lat), 4326)
    radius_meters = radius_km * 1000.0

    from geoalchemy2 import Geography
    user_geog = cast(user_point, Geography)
    center_geog = cast(ReliefCenter.geom, Geography)

    dist_expr = func.ST_Distance(center_geog, user_geog)

    stmt = select(
        ReliefCenter,
        (dist_expr / 1000.0).label("dist_km"),
    ).where(
        ReliefCenter.is_active.is_(True),
        func.ST_DWithin(center_geog, user_geog, radius_meters),
    )

    if center_type and center_type.upper() != "ALL":
        stmt = stmt.where(ReliefCenter.center_type == center_type.upper())

    stmt = stmt.order_by("dist_km").limit(50)

    res = await db.execute(stmt)
    rows = res.all()

    items = []
    for center, dist_km in rows:
        avail = max(0, center.capacity - center.occupied_count)
        item = ReliefCenterItem(
            id=center.id,
            name=center.name,
            center_type=center.center_type,
            address=center.address,
            district_name=center.district_name,
            state_name=center.state_name,
            capacity=center.capacity,
            occupied_count=center.occupied_count,
            available_capacity=avail,
            contact_phone=center.contact_phone,
            latitude=center.latitude,
            longitude=center.longitude,
            distance_km=round(float(dist_km), 2),
            is_active=center.is_active,
            created_at=center.created_at,
        )
        items.append(item)

    return ReliefCenterListResponse(
        success=True,
        data=items,
        meta={
            "total_found": len(items),
            "radius_km": radius_km,
            "center_lat": lat,
            "center_lng": lng,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    )


@router.post(
    "",
    response_model=ReliefCenterItem,
    status_code=status.HTTP_201_CREATED,
    summary="Register New Emergency Relief Center (Operator Only)",
    description="Registers an official shelter, hospital, or evacuation facility in system database.",
)
async def create_relief_center(
    payload: ReliefCenterCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_operator: User = Depends(get_current_operator),
) -> ReliefCenterItem:
    """Create relief center (requires operator JWT auth)."""
    geom_wkt = WKTElement(f"POINT({payload.longitude} {payload.latitude})", srid=4326)

    center = ReliefCenter(
        name=payload.name.strip(),
        center_type=payload.center_type.upper(),
        address=payload.address,
        district_name=payload.district_name,
        state_name=payload.state_name,
        capacity=payload.capacity,
        occupied_count=payload.occupied_count,
        contact_phone=payload.contact_phone,
        latitude=payload.latitude,
        longitude=payload.longitude,
        geom=geom_wkt,
        is_active=True,
    )
    db.add(center)
    await db.commit()
    await db.refresh(center)


@router.patch(
    "/{id}",
    response_model=ReliefCenterItem,
    status_code=status.HTTP_200_OK,
    summary="Update Relief Center Occupancy & Status (Operator Only)",
    description="Updates capacity, occupied count, or active status of a relief center.",
)
async def update_relief_center(
    id: uuid.UUID,
    payload: ReliefCenterUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_operator: User = Depends(get_current_operator),
) -> ReliefCenterItem:
    """Update relief center occupancy (requires operator JWT auth)."""
    stmt = select(ReliefCenter).where(ReliefCenter.id == id)
    res = await db.execute(stmt)
    center = res.scalar_one_or_none()

    if not center:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "RESOURCE_NOT_FOUND", "message": f"Relief center {id} not found"},
        )

    if payload.capacity is not None:
        center.capacity = payload.capacity
    if payload.occupied_count is not None:
        center.occupied_count = payload.occupied_count
    if payload.contact_phone is not None:
        center.contact_phone = payload.contact_phone
    if payload.is_active is not None:
        center.is_active = payload.is_active

    await db.commit()
    await db.refresh(center)

    avail = max(0, center.capacity - center.occupied_count)
    return ReliefCenterItem(
        id=center.id,
        name=center.name,
        center_type=center.center_type,
        address=center.address,
        district_name=center.district_name,
        state_name=center.state_name,
        capacity=center.capacity,
        occupied_count=center.occupied_count,
        available_capacity=avail,
        contact_phone=center.contact_phone,
        latitude=center.latitude,
        longitude=center.longitude,
        distance_km=0.0,
        is_active=center.is_active,
        created_at=center.created_at,
    )
