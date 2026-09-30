"""Pydantic schemas for physical weather corroboration responses."""

import uuid
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class PhysicalCorroborationItem(BaseModel):
    """Explainable physical observation corroboration record (Product Rule P7)."""

    id: Optional[uuid.UUID] = None
    variable: str = Field(
        ...,
        description="Observed physical atmospheric variable (e.g. rainfall_1h, max_temperature)",
    )
    observed_value: Optional[float] = Field(None, description="Measured or modeled numeric value")
    unit: str = Field(..., description="Measurement unit (e.g. mm/1h, mm/24h, degC, km/h, m)")
    source: str = Field(..., description="Source name (e.g. OPEN_METEO, IMD_AWS, CWC_NWDP)")
    source_type: str = Field(..., description="Source category ('STATION' or 'MODEL')")
    station_or_grid_id: Optional[str] = Field(
        None, description="Station identifier or 0.25 deg grid cell id"
    )
    distance_km: Optional[float] = Field(
        None, description="Haversine distance from incident location in km"
    )
    time_gap_hours: Optional[float] = Field(
        None, description="Absolute time difference from incident in hours"
    )
    verdict: str = Field(
        ...,
        description="Corroboration verdict ('SUPPORTS', 'CONTRADICTS', 'NEUTRAL')",
    )
    weight: float = Field(0.0, description="Source type weight applied (STATION=1.00, MODEL=0.60)")
    contribution: float = Field(0.0, description="Net credibility contribution score")
    provider_status: str = Field(
        "OK", description="Provider status ('OK', 'TIMEOUT', 'NO_DATA', etc.)"
    )
    observation_time: Optional[datetime] = Field(
        None, description="Timestamp of the weather observation"
    )
    explanation: Optional[str] = Field(None, description="Plain language explanation of verdict")
    is_simulated: bool = Field(False, description="True if generated from demo fixture")

    model_config = ConfigDict(from_attributes=True)


class PhysicalCorroborationBlock(BaseModel):
    """Comprehensive physical weather corroboration block for incident detail."""

    overall_verdict: str = Field(
        "NEUTRAL",
        description="Aggregate verdict across all physical observations",
    )
    overall_provider_status: str = Field("OK", description="Provider status summary")
    total_contribution: float = Field(
        0.0, description="Total credibility lift or penalty from physical data"
    )
    items: List[PhysicalCorroborationItem] = Field(
        default_factory=list,
        description="List of physical observation evaluations",
    )
    is_simulated: bool = Field(
        False, description="True if any observation is a simulated demo fixture"
    )

    model_config = ConfigDict(from_attributes=True)
