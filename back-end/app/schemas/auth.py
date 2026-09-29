"""Pydantic schemas for authentication and operator profiles."""

from __future__ import annotations

import uuid
from typing import Any, Dict, Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class SignupRequest(BaseModel):
    """Payload for citizen self-registration."""

    email: EmailStr = Field(..., description="Valid citizen email address")
    password: str = Field(..., min_length=8, max_length=128, description="Password with minimum 8 characters")
    full_name: str = Field(..., min_length=2, max_length=150, description="Full name of citizen")


class LoginRequest(BaseModel):
    """Payload for user/operator login authentication."""

    username: str = Field(..., description="Email address or username")
    password: str = Field(..., description="Plain text password")


class UserProfile(BaseModel):
    """Authenticated user profile summary."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: EmailStr
    full_name: str
    role: str
    jurisdiction_code: Optional[str] = None
    home_location_lat: Optional[float] = None
    home_location_lng: Optional[float] = None
    home_location_name: Optional[str] = None
    alert_radius_km: Optional[float] = 25.0


class OperatorProfile(UserProfile):
    """Authenticated operator profile summary (backward compatible)."""

    pass


class UpdateLocationRequest(BaseModel):
    """Payload for saving citizen home location and risk radius."""

    latitude: float = Field(..., ge=-90.0, le=90.0)
    longitude: float = Field(..., ge=-180.0, le=180.0)
    location_name: Optional[str] = None
    alert_radius_km: Optional[float] = Field(default=25.0, ge=1.0, le=100.0)


class TokenResponseData(BaseModel):
    """Token payload returning JWT access token and user profile details."""

    access_token: str
    token_type: str = "bearer"
    expires_in_seconds: int = 86400
    user: UserProfile
    operator: Optional[UserProfile] = None


class TokenResponse(BaseModel):
    """Standard API envelope for successful authentication."""

    success: bool = True
    data: TokenResponseData
    meta: Dict[str, Any] = Field(default_factory=dict)
