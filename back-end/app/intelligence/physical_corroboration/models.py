"""Data models and enums for physical meteorological corroboration."""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field


class PhysicalCorroborationVerdict(str, Enum):
    SUPPORTS = "SUPPORTS"
    CONTRADICTS = "CONTRADICTS"
    NEUTRAL = "NEUTRAL"


class PhysicalSourceType(str, Enum):
    STATION = "STATION"
    MODEL = "MODEL"


class ProviderStatus(str, Enum):
    OK = "OK"
    TIMEOUT = "TIMEOUT"
    PROVIDER_ERROR = "PROVIDER_ERROR"
    PROVIDER_RATE_LIMITED = "PROVIDER_RATE_LIMITED"
    MALFORMED_DATA = "MALFORMED_DATA"
    NO_DATA = "NO_DATA"
    STALE_DATA = "STALE_DATA"
    TOO_FAR = "TOO_FAR"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    DISABLED = "DISABLED"


class PhysicalObservation(BaseModel):
    """Normalized physical observation record for corroboration."""

    source_name: str
    source_type: PhysicalSourceType
    station_or_grid_id: str
    latitude: float
    longitude: float
    observed_at: datetime

    # Atmospheric / Hydrological variables
    rainfall_1h_mm: Optional[float] = None
    rainfall_3h_mm: Optional[float] = None
    rainfall_24h_mm: Optional[float] = None
    rainfall_72h_mm: Optional[float] = None

    temperature_c: Optional[float] = None
    max_temperature_c: Optional[float] = None
    min_temperature_c: Optional[float] = None

    wind_speed_kmh: Optional[float] = None
    wind_gusts_kmh: Optional[float] = None
    wind_direction_deg: Optional[int] = None

    visibility_m: Optional[float] = None
    relative_humidity_pct: Optional[float] = None
    pressure_hpa: Optional[float] = None
    weather_code: Optional[int] = None
    water_level_m: Optional[float] = None

    # Metadata
    is_simulated: bool = False
    raw_payload: Optional[Dict[str, Any]] = None


class PhysicalCorroborationResult(BaseModel):
    """Detailed explainable verdict produced by the evaluation engine."""

    verdict: PhysicalCorroborationVerdict
    observed_value: Optional[float] = None
    unit: str = ""
    variable: str = ""
    source: str = ""
    source_type: PhysicalSourceType = PhysicalSourceType.MODEL
    station_or_grid_id: str = ""
    distance_km: float = 0.0
    time_gap_hours: float = 0.0
    weight: float = 0.0
    contribution: float = 0.0
    provider_status: ProviderStatus = ProviderStatus.OK
    explanation: str = ""
    is_simulated: bool = False
    evaluated_at: datetime = Field(default_factory=datetime.utcnow)
