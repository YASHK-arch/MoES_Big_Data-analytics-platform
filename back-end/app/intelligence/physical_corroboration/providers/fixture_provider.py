"""Deterministic demo fixture provider for physical weather corroboration.

Generates reproducible atmospheric observations for demonstration drills:
1. SUPPORTS scenario (e.g. Heavy rainfall / cyclone support)
2. CONTRADICTS scenario (Station-type observation disproving citizen report)
3. NEUTRAL / provider-down scenario (Timeout / outage fallback)

All observations are explicitly flagged with is_simulated=True.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional, Tuple

from app.core.config import settings
from app.intelligence.physical_corroboration.models import (
    PhysicalObservation,
    PhysicalSourceType,
    ProviderStatus,
)
from app.intelligence.physical_corroboration.providers.base import BaseWeatherProvider

logger = logging.getLogger(__name__)


class FixtureWeatherProvider(BaseWeatherProvider):
    """Deterministic simulated weather provider for testing and live demonstrations."""

    def __init__(
        self,
        name: str = "DEMO_FIXTURE_AWS",
        source_type: PhysicalSourceType = PhysicalSourceType.STATION,
        scenario: str = "AUTO",
        is_enabled: bool = True,
        timeout_seconds: float = 2.0,
    ) -> None:
        super().__init__(
            name=name,
            source_type=source_type,
            is_enabled=is_enabled,
            timeout_seconds=timeout_seconds,
            max_retries=0,
        )
        self.scenario = scenario

    async def _execute_fetch(
        self,
        lat: float,
        lon: float,
        target_time: datetime,
        category: str,
    ) -> Tuple[Optional[PhysicalObservation], ProviderStatus, Optional[str]]:
        """Return deterministic simulated observation based on configured scenario or hazard category."""
        effective_scenario = self.scenario.upper()

        if effective_scenario == "AUTO":
            cat = (category or "OTHER").upper()
            if cat in ("HEAVY_RAINFALL", "CYCLONE_STORM", "URBAN_FLOOD", "FLOOD_WATERLOGGING"):
                effective_scenario = "SUPPORTS"
            elif cat in ("STRONG_WIND", "HEATWAVE", "HAILSTORM"):
                effective_scenario = "CONTRADICTS"
            else:
                effective_scenario = "NEUTRAL"

        # Observation timestamp matched to incident time
        obs_time = target_time if target_time.tzinfo else target_time.replace(tzinfo=timezone.utc)

        # 1. SUPPORTS Scenario
        if effective_scenario == "SUPPORTS":
            obs = PhysicalObservation(
                source_name="DEMO_FIXTURE_STATION",
                source_type=PhysicalSourceType.STATION,
                station_or_grid_id="AWS_DEMO_SUPPORT_01",
                latitude=round(lat + 0.01, 4),
                longitude=round(lon + 0.01, 4),
                observed_at=obs_time,
                rainfall_1h_mm=78.5,
                rainfall_24h_mm=142.0,
                wind_speed_kmh=82.0,
                temperature_c=27.5,
                is_simulated=True,
                raw_payload={"demo_scenario": "SUPPORTS", "fixture_version": "1.0"},
            )
            return obs, ProviderStatus.OK, None

        # 2. CONTRADICTS Scenario (STATION type disproving report per P4)
        if effective_scenario == "CONTRADICTS":
            obs = PhysicalObservation(
                source_name="DEMO_FIXTURE_STATION",
                source_type=PhysicalSourceType.STATION,
                station_or_grid_id="AWS_DEMO_CONTRADICT_02",
                latitude=round(lat + 0.01, 4),
                longitude=round(lon + 0.01, 4),
                observed_at=obs_time,
                rainfall_1h_mm=0.0,
                rainfall_24h_mm=0.0,
                wind_speed_kmh=5.0,
                wind_gusts_kmh=8.0,
                temperature_c=21.0,
                max_temperature_c=23.0,
                is_simulated=True,
                raw_payload={"demo_scenario": "CONTRADICTS", "fixture_version": "1.0"},
            )
            return obs, ProviderStatus.OK, None

        # 3. NEUTRAL / Provider-down Scenario
        return (
            None,
            ProviderStatus.TIMEOUT,
            "Simulated demo provider timeout (live outage drill scenario)",
        )
