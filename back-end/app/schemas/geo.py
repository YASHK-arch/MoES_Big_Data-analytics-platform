"""Pydantic schemas for GeoJSON incident representations and spatial clusters."""

from __future__ import annotations

import uuid
from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field


class GeoJSONGeometryPoint(BaseModel):
    """GeoJSON Point geometry."""

    type: Literal["Point"] = "Point"
    coordinates: List[float] = Field(
        ...,
        min_length=2,
        max_length=3,
        description="[longitude, latitude] coordinates.",
    )


class GeoJSONIncidentProperties(BaseModel):
    """Feature properties for map layer rendering."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tracking_id: str
    title: str
    category_code: str
    severity: str
    credibility_score: float
    credibility_reason: Optional[str] = None
    verification_status: str
    readiness: str
    occurred_at: str
    location_name: Optional[str] = None


class GeoJSONIncidentFeature(BaseModel):
    """GeoJSON Feature for Leaflet vector layer (supports Point, LineString, Polygon, MultiPolygon)."""

    type: Literal["Feature"] = "Feature"
    geometry: Union[GeoJSONGeometryPoint, Dict[str, Any]]
    properties: GeoJSONIncidentProperties


class GeoJSONFeatureCollection(BaseModel):
    """Standard GeoJSON FeatureCollection envelope."""

    type: Literal["FeatureCollection"] = "FeatureCollection"
    features: List[GeoJSONIncidentFeature] = Field(default_factory=list)


class SpatialClusterSummary(BaseModel):
    """Aggregated cluster centroid and intensity for heatmap layer."""

    cluster_id: str
    latitude: float
    longitude: float
    point_count: int
    dominant_category: str
    max_severity: str
    average_credibility: float


class SpatialClusterListResponse(BaseModel):
    """Standard API envelope for spatial cluster centroids."""

    success: bool = True
    data: List[SpatialClusterSummary] = Field(default_factory=list)
    meta: dict = Field(default_factory=dict)
