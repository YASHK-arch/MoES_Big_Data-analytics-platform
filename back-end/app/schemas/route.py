"""Pydantic schemas for destination route-blockage check resources."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class RoutePointInput(BaseModel):
    """Geographic point coordinates for route check."""

    latitude: float = Field(..., ge=-90.0, le=90.0, description="Latitude in decimal degrees")
    longitude: float = Field(..., ge=-180.0, le=180.0, description="Longitude in decimal degrees")
    name: Optional[str] = Field(default=None, description="Optional place name or address label")


class RouteCheckRequest(BaseModel):
    """Payload for path corridor hazard check."""

    origin: RoutePointInput
    destination: RoutePointInput
    corridor_km: float = Field(
        default=2.0,
        ge=0.1,
        le=50.0,
        description="Buffer corridor width in kilometers around path",
    )


class IntersectingHazardDetail(BaseModel):
    """Hazard item intersecting the route buffer corridor."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tracking_id: str
    title: str
    category_code: str
    severity: str
    verification_status: str
    credibility_score: float
    credibility_reason: Optional[str] = None
    latitude: float
    longitude: float
    location_name: Optional[str] = None
    distance_to_corridor_center_m: float
    occurred_at: datetime


class RouteCheckResponseData(BaseModel):
    """Data payload for route blockage check result."""

    is_blocked: bool = Field(..., description="True if any verified hazard intersects the path corridor")
    hazard_count: int = Field(..., description="Total count of hazards within the corridor")
    corridor_km: float = Field(..., description="Corridor buffer width used in check")
    highest_severity: Optional[str] = Field(default=None, description="Highest severity level found along path")
    intersecting_incidents: List[IntersectingHazardDetail] = Field(default_factory=list)
    path_geojson: Dict[str, Any] = Field(..., description="GeoJSON Feature representation of route line and corridor buffer")


class RouteCheckResponse(BaseModel):
    """Standard API envelope for route blockage check."""

    success: bool = True
    data: RouteCheckResponseData
    meta: Dict[str, Any] = Field(default_factory=dict)
