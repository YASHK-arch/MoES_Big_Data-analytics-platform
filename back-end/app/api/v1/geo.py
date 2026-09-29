"""Geospatial Query API Router for Map Explorer and Clusters.

Exposes GeoJSON vector feature layers and spatial clusters for Leaflet mapping.
"""

from typing import Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.schemas.geo import GeoJSONFeatureCollection
from app.services.incident_query_service import incident_query_service

router = APIRouter()


@router.get(
    "/incidents",
    response_model=GeoJSONFeatureCollection,
    status_code=status.HTTP_200_OK,
    summary="Geospatial Viewport Query (GeoJSON)",
    description="Retrieval of spatial incidents within a map viewport for Leaflet rendering.",
)
@router.get(
    "/reports",
    response_model=GeoJSONFeatureCollection,
    status_code=status.HTTP_200_OK,
    include_in_schema=False,
)
async def get_geo_incidents(
    bbox: Optional[str] = Query(
        None,
        description="Bounding box min_lon,min_lat,max_lon,max_lat (optional for national view)",
    ),
    status_filter: Optional[str] = Query(
        None, alias="status", description="Verification status or comma-separated statuses"
    ),
    category: Optional[str] = Query(None, description="Event category code"),
    hours_ago: Optional[int] = Query(
        default=24, ge=1, le=720, description="Hours window (optional; omit for all-time)"
    ),
    db: AsyncSession = Depends(get_db),
) -> GeoJSONFeatureCollection:
    """Retrieve GeoJSON FeatureCollection bounded by PostGIS viewport or national overview."""
    parsed_bbox: Optional[Tuple[float, float, float, float]] = None
    if bbox is not None:
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

    return await incident_query_service.get_geo_incidents(
        session=db,
        bbox=parsed_bbox,
        status=status_filter,
        category=category,
        hours_ago=hours_ago,
    )


@router.get(
    "/incidents/nearby",
    response_model=GeoJSONFeatureCollection,
    status_code=status.HTTP_200_OK,
    summary="Geospatial Proximity Query for My Area Dashboard",
    description="Retrieval of spatial incidents within a radius around user location.",
)
async def get_nearby_geo_incidents(
    lat: float = Query(..., ge=-90.0, le=90.0, description="Center latitude"),
    lng: float = Query(..., ge=-180.0, le=180.0, description="Center longitude"),
    radius_km: float = Query(default=25.0, ge=1.0, le=500.0, description="Proximity radius in km"),
    status_filter: Optional[str] = Query(None, alias="status", description="Verification status filter"),
    db: AsyncSession = Depends(get_db),
) -> GeoJSONFeatureCollection:
    """Retrieve GeoJSON FeatureCollection bounded by PostGIS distance radius for citizen dashboard."""
    return await incident_query_service.get_nearby_incidents(
        session=db,
        lat=lat,
        lng=lng,
        radius_km=radius_km,
        status=status_filter,
    )


@router.get(
    "/forecasts",
    response_model=GeoJSONFeatureCollection,
    status_code=status.HTTP_200_OK,
    summary="Official IMD & NDMA Forecast Advisories & Cyclone Tracks (GeoJSON)",
    description="Retrieval of active weather forecast advisories, cyclone tracks, and warning zones.",
)
async def get_geo_forecast_advisories(
    hazard_type: Optional[str] = Query(None, description="Hazard category filter"),
    active_only: bool = Query(default=True, description="Filter to currently active advisories"),
    db: AsyncSession = Depends(get_db),
) -> GeoJSONFeatureCollection:
    """Retrieve GeoJSON FeatureCollection of official forecast advisories."""
    return await incident_query_service.get_forecast_advisories(
        session=db,
        active_only=active_only,
        hazard_type=hazard_type,
    )
