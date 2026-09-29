"""Pydantic schemas for Relief Center locator."""

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class ReliefCenterCreateRequest(BaseModel):
    """Payload for registering a new emergency relief center."""

    name: str = Field(..., min_length=3, max_length=255, description="Name of relief center or hospital")
    center_type: str = Field(default="SHELTER", description="SHELTER, HOSPITAL, RELIEF_CAMP")
    address: Optional[str] = None
    district_name: Optional[str] = None
    state_name: Optional[str] = None
    capacity: int = Field(default=100, ge=1)
    occupied_count: int = Field(default=0, ge=0)
    contact_phone: Optional[str] = None
    latitude: float = Field(..., ge=-90.0, le=90.0)
    longitude: float = Field(..., ge=-180.0, le=180.0)


class ReliefCenterUpdateRequest(BaseModel):
    """Payload for updating an emergency relief center's occupancy or status."""

    capacity: Optional[int] = Field(default=None, ge=1)
    occupied_count: Optional[int] = Field(default=None, ge=0)
    contact_phone: Optional[str] = None
    is_active: Optional[bool] = None


class ReliefCenterItem(BaseModel):
    """Relief Center detail response model."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    center_type: str
    address: Optional[str] = None
    district_name: Optional[str] = None
    state_name: Optional[str] = None
    capacity: int
    occupied_count: int
    available_capacity: int
    contact_phone: Optional[str] = None
    latitude: float
    longitude: float
    distance_km: Optional[float] = None
    is_active: bool
    created_at: datetime


class ReliefCenterListResponse(BaseModel):
    """API envelope for relief center query results."""

    success: bool = True
    data: List[ReliefCenterItem]
    meta: Dict[str, Any] = Field(default_factory=dict)
