"""Production service for path corridor hazard checks using PostGIS spatial geography buffering."""

import json
import logging
from typing import Any, Dict, List, Optional

import httpx
from geoalchemy2 import Geography, Geometry
from geoalchemy2.functions import (
    ST_AsGeoJSON,
    ST_Buffer,
    ST_Distance,
    ST_GeomFromGeoJSON,
    ST_Intersects,
    ST_MakeLine,
    ST_MakePoint,
    ST_SetSRID,
)
from sqlalchemy import cast, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.report import WeatherReport
from app.schemas.route import (
    IntersectingHazardDetail,
    RouteCheckRequest,
    RouteCheckResponseData,
)

logger = logging.getLogger(__name__)


async def fetch_osrm_road_geometry(
    orig_lat: float, orig_lon: float, dest_lat: float, dest_lon: float
) -> Optional[Dict[str, Any]]:
    """Fetch real driving road geometry (LineString GeoJSON) from OSRM routing engine."""
    osrm_url = f"https://router.project-osrm.org/route/v1/driving/{orig_lon},{orig_lat};{dest_lon},{dest_lat}?overview=full&geometries=geojson"
    try:
        async with httpx.AsyncClient(timeout=4.0) as client:
            resp = await client.get(osrm_url)
            if resp.status_code == 200:
                data = resp.json()
                routes = data.get("routes", [])
                if routes and "geometry" in routes[0]:
                    return routes[0]["geometry"]
    except Exception as e:
        logger.warning("OSRM routing service unavailable (%s). Falling back to great-circle corridor.", e)
    return None


class RouteCheckService:
    """Service providing spatial path blockage and hazard corridor checks."""

    async def check_route_corridor(
        self,
        session: AsyncSession,
        payload: RouteCheckRequest,
    ) -> RouteCheckResponseData:
        """Perform PostGIS geography buffer intersection check on real road geometry."""
        orig = payload.origin
        dest = payload.destination
        corridor_km = payload.corridor_km
        corridor_meters = corridor_km * 1000.0

        orig_point = ST_SetSRID(ST_MakePoint(orig.longitude, orig.latitude), 4326)
        dest_point = ST_SetSRID(ST_MakePoint(dest.longitude, dest.latitude), 4326)

        # 1. Fetch real road driving LineString from OSRM
        road_geom_dict = await fetch_osrm_road_geometry(
            orig.latitude, orig.longitude, dest.latitude, dest.longitude
        )

        if road_geom_dict and road_geom_dict.get("type") == "LineString":
            # Real road driving corridor
            road_geojson_str = json.dumps(road_geom_dict)
            path_line = ST_SetSRID(ST_GeomFromGeoJSON(road_geojson_str), 4326)
            is_real_road = True
        else:
            # Fallback to direct geometric line
            path_line = ST_MakeLine(orig_point, dest_point)
            is_real_road = False

        # Buffer path line by corridor_meters using PostGIS geography conversion
        path_geography = cast(path_line, Geography)
        buffer_geography = ST_Buffer(path_geography, corridor_meters)
        buffer_geometry = cast(buffer_geography, Geometry)

        # Query active verified / high-credibility incidents intersecting the buffered corridor
        stmt = (
            select(
                WeatherReport,
                ST_Distance(cast(WeatherReport.geom, Geography), path_geography).label("dist_m"),
            )
            .options(selectinload(WeatherReport.category))
            .where(
                WeatherReport.geom.isnot(None),
                WeatherReport.verification_status.in_(["VERIFIED", "UNDER_REVIEW"]),
                WeatherReport.credibility_score >= 0.50,
                ST_Intersects(WeatherReport.geom, buffer_geometry),
            )
            .order_by("dist_m", WeatherReport.occurred_at.desc())
            .limit(50)
        )

        res = await session.execute(stmt)
        rows = res.all()

        intersecting_hazards: List[IntersectingHazardDetail] = []
        severity_hierarchy = {"SEVERE": 4, "HIGH": 3, "MODERATE": 2, "LOW": 1}
        max_sev_rank = 0
        highest_severity: Optional[str] = None

        for report, dist_m in rows:
            cat_code = (
                report.category.category_code
                if report.category
                else (report.reported_category or "OTHER")
            )
            rank = severity_hierarchy.get(report.severity, 1)
            if rank > max_sev_rank:
                max_sev_rank = rank
                highest_severity = report.severity

            intersecting_hazards.append(
                IntersectingHazardDetail(
                    id=report.id,
                    tracking_id=report.tracking_id,
                    title=report.title,
                    category_code=cat_code,
                    severity=report.severity,
                    verification_status=report.verification_status,
                    credibility_score=report.credibility_score,
                    credibility_reason=report.credibility_reason,
                    latitude=report.latitude,
                    longitude=report.longitude,
                    location_name=report.location_name,
                    distance_to_corridor_center_m=round(float(dist_m or 0.0), 1),
                    occurred_at=report.occurred_at,
                )
            )

        # Fetch GeoJSON string representation of path and corridor buffer
        geojson_stmt = select(
            ST_AsGeoJSON(path_line).label("line_geojson"),
            ST_AsGeoJSON(buffer_geometry).label("buffer_geojson"),
        )
        g_res = await session.execute(geojson_stmt)
        g_row = g_res.one()

        line_dict = json.loads(g_row.line_geojson) if g_row.line_geojson else {}
        buffer_dict = json.loads(g_row.buffer_geojson) if g_row.buffer_geojson else {}

        path_geojson_feature = {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "geometry": line_dict,
                    "properties": {
                        "type": "PATH_LINE",
                        "is_real_road": is_real_road,
                        "origin_name": orig.name or "Origin",
                        "destination_name": dest.name or "Destination",
                    },
                },
                {
                    "type": "Feature",
                    "geometry": buffer_dict,
                    "properties": {
                        "type": "CORRIDOR_BUFFER",
                        "corridor_km": corridor_km,
                    },
                },
            ],
        }

        is_blocked = len(intersecting_hazards) > 0

        return RouteCheckResponseData(
            is_blocked=is_blocked,
            hazard_count=len(intersecting_hazards),
            corridor_km=corridor_km,
            highest_severity=highest_severity,
            intersecting_incidents=intersecting_hazards,
            path_geojson=path_geojson_feature,
        )


route_check_service = RouteCheckService()
