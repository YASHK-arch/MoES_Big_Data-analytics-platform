"""Open-Meteo numerical weather prediction model provider."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import httpx

from app.intelligence.physical_corroboration.models import (
    PhysicalObservation,
    PhysicalSourceType,
    ProviderStatus,
)
from app.intelligence.physical_corroboration.providers.base import BaseWeatherProvider

logger = logging.getLogger(__name__)


class OpenMeteoProvider(BaseWeatherProvider):
    """Open-Meteo numerical model weather provider (Product Rule P4: MODEL source)."""

    FORECAST_ENDPOINT = "https://api.open-meteo.com/v1/forecast"
    ARCHIVE_ENDPOINT = "https://archive-api.open-meteo.com/v1/archive"
    USER_AGENT = "NationalWeatherPlatform-SIH26069/1.0 (sih26069@weather-platform.gov.in)"

    HOURLY_VARIABLES = [
        "precipitation",
        "temperature_2m",
        "relative_humidity_2m",
        "wind_speed_10m",
        "wind_gusts_10m",
        "visibility",
        "surface_pressure",
    ]

    def __init__(
        self,
        is_enabled: bool = True,
        timeout_seconds: float = 6.0,
        max_retries: int = 2,
        initial_backoff_seconds: float = 0.2,
        http_client: Optional[httpx.AsyncClient] = None,
    ) -> None:
        super().__init__(
            name="OPEN_METEO",
            source_type=PhysicalSourceType.MODEL,
            is_enabled=is_enabled,
            timeout_seconds=timeout_seconds,
            max_retries=max_retries,
            initial_backoff_seconds=initial_backoff_seconds,
        )
        self._http_client = http_client

    async def _get_client(self) -> httpx.AsyncClient:
        if self._http_client is not None:
            return self._http_client
        return httpx.AsyncClient(
            timeout=httpx.Timeout(self.timeout_seconds),
            headers={"User-Agent": self.USER_AGENT},
        )

    async def _execute_fetch(
        self,
        lat: float,
        lon: float,
        target_time: datetime,
        category: str,
    ) -> Tuple[Optional[PhysicalObservation], ProviderStatus, Optional[str]]:
        now = datetime.now(timezone.utc)
        if target_time.tzinfo is None:
            time_utc = target_time.replace(tzinfo=timezone.utc)
        else:
            time_utc = target_time.astimezone(timezone.utc)

        days_ago = (now - time_utc).total_seconds() / 86400.0
        date_str = time_utc.strftime("%Y-%m-%d")

        if days_ago > 5.0:
            endpoint = self.ARCHIVE_ENDPOINT
            params = {
                "latitude": round(lat, 4),
                "longitude": round(lon, 4),
                "start_date": date_str,
                "end_date": date_str,
                "hourly": ",".join(self.HOURLY_VARIABLES),
                "timezone": "UTC",
            }
        else:
            endpoint = self.FORECAST_ENDPOINT
            params = {
                "latitude": round(lat, 4),
                "longitude": round(lon, 4),
                "hourly": ",".join(self.HOURLY_VARIABLES),
                "past_days": min(7, max(1, int(days_ago) + 1)),
                "forecast_days": 1,
                "timezone": "UTC",
            }

        client = await self._get_client()
        try:
            response = await client.get(endpoint, params=params)
        except httpx.TimeoutException:
            raise
        except httpx.RequestError as exc:
            return None, ProviderStatus.PROVIDER_ERROR, f"HTTP connection error: {exc}"

        if response.status_code == 429:
            retry_after = response.headers.get("Retry-After", "unknown")
            return (
                None,
                ProviderStatus.PROVIDER_RATE_LIMITED,
                f"Open-Meteo 429 rate limit exceeded. Retry-After: {retry_after}",
            )

        if response.status_code >= 400:
            return (
                None,
                ProviderStatus.PROVIDER_ERROR,
                f"Open-Meteo HTTP error {response.status_code}: {response.text[:200]}",
            )

        try:
            payload = response.json()
        except Exception as exc:
            return (
                None,
                ProviderStatus.MALFORMED_DATA,
                f"Failed to parse JSON response: {exc}",
            )

        if not isinstance(payload, dict) or "hourly" not in payload:
            return (
                None,
                ProviderStatus.NO_DATA,
                "Response JSON missing 'hourly' field",
            )

        hourly = payload["hourly"]
        times = hourly.get("time")
        if not times or not isinstance(times, list):
            return (
                None,
                ProviderStatus.NO_DATA,
                "Hourly series contains no timestamps",
            )

        best_idx = -1
        best_diff = float("inf")
        target_iso = time_utc.strftime("%Y-%m-%dT%H:00")

        for idx, t_str in enumerate(times):
            try:
                slot_time = datetime.fromisoformat(t_str).replace(tzinfo=timezone.utc)
                diff = abs((slot_time - time_utc).total_seconds())
                if diff < best_diff:
                    best_diff = diff
                    best_idx = idx
            except Exception:
                continue

        if best_idx == -1:
            return (
                None,
                ProviderStatus.NO_DATA,
                f"No matching hourly time slot found for {target_iso}",
            )

        slot_iso = times[best_idx]
        slot_dt = datetime.fromisoformat(slot_iso).replace(tzinfo=timezone.utc)

        def _val(var_name: str) -> Optional[float]:
            series = hourly.get(var_name)
            if series and best_idx < len(series):
                v = series[best_idx]
                if v is not None:
                    try:
                        return float(v)
                    except (ValueError, TypeError):
                        return None
            return None

        grid_id = f"OM_GRID_{round(lat, 2)}_{round(lon, 2)}"
        observation = PhysicalObservation(
            source_name="OPEN_METEO",
            source_type=PhysicalSourceType.MODEL,
            station_or_grid_id=grid_id,
            latitude=float(payload.get("latitude", lat)),
            longitude=float(payload.get("longitude", lon)),
            observed_at=slot_dt,
            rainfall_1h_mm=_val("precipitation"),
            temperature_c=_val("temperature_2m"),
            max_temperature_c=_val("temperature_2m"),
            wind_speed_kmh=_val("wind_speed_10m"),
            wind_gusts_kmh=_val("wind_gusts_10m"),
            visibility_m=_val("visibility"),
            pressure_hpa=_val("surface_pressure"),
            relative_humidity_pct=_val("relative_humidity_2m"),
            is_simulated=False,
        )

        return observation, ProviderStatus.OK, None
