"""Open-Meteo Hourly Weather Observations Ingestion Adapter.

Polls the free Open-Meteo API (https://open-meteo.com) for recent hourly
meteorological observations across a configured list of major Indian cities.
Produces NormalizedObservationEvent records routed to stream:weather:observations.

API Contract:
  GET https://api.open-meteo.com/v1/forecast
      ?latitude={lat}&longitude={lon}
      &hourly=precipitation,temperature_2m,relative_humidity_2m,
              wind_speed_10m,wind_direction_10m,surface_pressure
      &past_days=1&forecast_days=0
      &timezone=Asia%2FKolkata

No authentication required. Compliant usage requires setting a descriptive User-Agent.
Rate limiting: max 1 request per city every OPEN_METEO_MIN_REQUEST_INTERVAL_SECONDS.
"""

import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import httpx

from app.core.config import settings
from app.ingestion.exceptions import AdapterFetchError
from app.ingestion.schemas import NormalizedObservationEvent

logger = logging.getLogger(__name__)

# Default set of major Indian city coordinates (name, lat, lon, station_code)
DEFAULT_INDIAN_CITIES: List[Tuple[str, float, float, str]] = [
    ("Mumbai", 19.0760, 72.8777, "OM-MUM"),
    ("Delhi", 28.6139, 77.2090, "OM-DEL"),
    ("Bengaluru", 12.9716, 77.5946, "OM-BLR"),
    ("Chennai", 13.0827, 80.2707, "OM-MAA"),
    ("Kolkata", 22.5726, 88.3639, "OM-CCU"),
    ("Hyderabad", 17.3850, 78.4867, "OM-HYD"),
    ("Pune", 18.5204, 73.8567, "OM-PNQ"),
    ("Ahmedabad", 23.0225, 72.5714, "OM-AMD"),
    ("Patna", 25.5941, 85.1376, "OM-PAT"),
    ("Guwahati", 26.1445, 91.7362, "OM-GAU"),
]


class OpenMeteoAdapter:
    """Ingestion adapter for Open-Meteo free meteorological observation API.

    Fetches the most recent completed hourly observation hour for each configured
    Indian city and emits NormalizedObservationEvent records.
    """

    OPEN_METEO_ENDPOINT = "https://api.open-meteo.com/v1/forecast"
    USER_AGENT = "NationalWeatherPlatform-SIH26069/1.0 (sih26069@weather-platform.gov.in)"

    HOURLY_VARIABLES = [
        "precipitation",
        "temperature_2m",
        "relative_humidity_2m",
        "wind_speed_10m",
        "wind_direction_10m",
        "surface_pressure",
    ]

    def __init__(
        self,
        cities: Optional[List[Tuple[str, float, float, str]]] = None,
        endpoint: Optional[str] = None,
        timeout_seconds: Optional[float] = None,
        min_interval_seconds: Optional[float] = None,
        http_client: Optional[httpx.AsyncClient] = None,
    ) -> None:
        self.source_code = "OPEN_METEO"
        self.source_name = "Open-Meteo Hourly Weather Observations"
        self.source_type = "METEOROLOGICAL_SERVICE"
        self.base_trust_score = 0.80

        self.cities = cities or DEFAULT_INDIAN_CITIES
        self.endpoint = endpoint or getattr(settings, "OPEN_METEO_ENDPOINT", self.OPEN_METEO_ENDPOINT)
        self.timeout_seconds = timeout_seconds or getattr(settings, "OPEN_METEO_TIMEOUT_SECONDS", 15.0)
        self.min_interval_seconds = min_interval_seconds if min_interval_seconds is not None else getattr(
            settings, "OPEN_METEO_MIN_REQUEST_INTERVAL_SECONDS", 1.0
        )
        self._http_client = http_client
        self._last_request_time: float = 0.0

    async def _get_client(self) -> httpx.AsyncClient:
        if self._http_client and not self._http_client.is_closed:
            return self._http_client
        return httpx.AsyncClient(
            timeout=httpx.Timeout(self.timeout_seconds),
            headers={"User-Agent": self.USER_AGENT},
            follow_redirects=True,
        )

    async def _apply_rate_limit(self) -> None:
        """Enforce minimum inter-request interval to respect Open-Meteo fair use policy."""
        elapsed = time.monotonic() - self._last_request_time
        if elapsed < self.min_interval_seconds:
            await asyncio.sleep(self.min_interval_seconds - elapsed)
        self._last_request_time = time.monotonic()

    def _build_params(self, lat: float, lon: float) -> Dict[str, Any]:
        return {
            "latitude": lat,
            "longitude": lon,
            "hourly": ",".join(self.HOURLY_VARIABLES),
            "past_days": 1,
            "forecast_days": 0,
            "timezone": "Asia/Kolkata",
        }

    def _extract_latest_hour(
        self,
        hourly: Dict[str, Any],
    ) -> Tuple[Optional[datetime], Dict[str, Optional[float]]]:
        """Extract the most recently completed hourly observation from the API response."""
        times: List[str] = hourly.get("time", [])
        if not times:
            return None, {}

        # Find the latest timestamp that is <= now
        now_utc = datetime.now(timezone.utc)
        best_idx = 0
        best_dt: Optional[datetime] = None

        for i, t in enumerate(times):
            try:
                # Open-Meteo returns ISO 8601 local time strings; parse and treat as IST (UTC+5:30)
                dt_naive = datetime.fromisoformat(t)
                # Open-Meteo returns times in the requested timezone — assume UTC+5:30 for IST
                from datetime import timedelta
                dt_utc = dt_naive.replace(tzinfo=timezone.utc) - timedelta(hours=5, minutes=30)
                if dt_utc <= now_utc:
                    best_idx = i
                    best_dt = dt_utc
            except (ValueError, TypeError):
                continue

        def _safe_float(lst: Optional[List], idx: int) -> Optional[float]:
            if not lst or idx >= len(lst):
                return None
            val = lst[idx]
            if val is None:
                return None
            try:
                return float(val)
            except (TypeError, ValueError):
                return None

        metrics = {
            "precipitation_mm": _safe_float(hourly.get("precipitation"), best_idx),
            "temperature_c": _safe_float(hourly.get("temperature_2m"), best_idx),
            "humidity_pct": _safe_float(hourly.get("relative_humidity_2m"), best_idx),
            "wind_speed_kmh": _safe_float(hourly.get("wind_speed_10m"), best_idx),
            "wind_direction_deg": _safe_float(hourly.get("wind_direction_10m"), best_idx),
            "pressure_hpa": _safe_float(hourly.get("surface_pressure"), best_idx),
        }
        return best_dt, metrics

    def _parse_city_response(
        self,
        city_name: str,
        station_code: str,
        lat: float,
        lon: float,
        data: Dict[str, Any],
    ) -> Optional[NormalizedObservationEvent]:
        """Parse the Open-Meteo JSON response for a single city into a NormalizedObservationEvent."""
        hourly = data.get("hourly")
        if not isinstance(hourly, dict):
            logger.warning("Open-Meteo response for %s missing 'hourly' block.", city_name)
            return None

        observed_at, metrics = self._extract_latest_hour(hourly)
        if observed_at is None:
            logger.warning("Could not extract latest observation hour for %s.", city_name)
            return None

        # Build deterministic external_id: station_code + observed hour (ISO minute-truncated)
        hour_str = observed_at.strftime("%Y%m%dT%H00Z")
        external_id = f"OPEN_METEO-{station_code}-{hour_str}"

        wind_dir = metrics.get("wind_direction_deg")
        wind_dir_int: Optional[int] = int(round(wind_dir)) if wind_dir is not None else None

        return NormalizedObservationEvent(
            source_code=self.source_code,
            external_id=external_id,
            station_code=station_code,
            station_name=f"Open-Meteo Virtual Station — {city_name}",
            latitude=lat,
            longitude=lon,
            observed_at=observed_at,
            rainfall_mm=metrics.get("precipitation_mm"),
            temperature_c=metrics.get("temperature_c"),
            humidity_pct=metrics.get("humidity_pct"),
            wind_speed_kmh=metrics.get("wind_speed_kmh"),
            wind_direction_deg=wind_dir_int,
            pressure_hpa=metrics.get("pressure_hpa"),
            raw_metrics={
                "source": "open_meteo_hourly_v1",
                "city": city_name,
                "utc_hour": hour_str,
                **{k: v for k, v in metrics.items() if v is not None},
            },
        )

    async def _fetch_city(
        self,
        client: httpx.AsyncClient,
        city_name: str,
        station_code: str,
        lat: float,
        lon: float,
    ) -> Optional[NormalizedObservationEvent]:
        """Fetch and parse observations for a single city."""
        await self._apply_rate_limit()
        params = self._build_params(lat, lon)

        try:
            response = await client.get(self.endpoint, params=params)
            if response.status_code != 200:
                logger.warning(
                    "Open-Meteo returned HTTP %d for city %s.",
                    response.status_code, city_name,
                )
                return None
            data = response.json()
            return self._parse_city_response(city_name, station_code, lat, lon, data)

        except httpx.TimeoutException:
            logger.warning("Open-Meteo request timed out for city %s.", city_name)
            return None
        except httpx.ConnectError as e:
            logger.warning("Open-Meteo connection error for city %s: %s", city_name, e)
            return None
        except Exception as e:
            logger.error(
                "Unexpected error fetching Open-Meteo data for city %s: %s",
                city_name, e, exc_info=True,
            )
            return None

    async def fetch_raw_events(self) -> List[NormalizedObservationEvent]:
        """Fetch latest hourly observations for all configured Indian cities."""
        client = await self._get_client()
        should_close = client != self._http_client

        observations: List[NormalizedObservationEvent] = []
        try:
            for city_name, lat, lon, station_code in self.cities:
                obs = await self._fetch_city(client, city_name, station_code, lat, lon)
                if obs is not None:
                    observations.append(obs)
        finally:
            if should_close:
                await client.aclose()

        logger.info(
            "Open-Meteo ingestion complete: %d/%d city observations fetched.",
            len(observations), len(self.cities),
        )
        return observations

    async def ingest(self) -> List[NormalizedObservationEvent]:
        """Execute full fetch cycle and return normalized observation events."""
        try:
            return await self.fetch_raw_events()
        except Exception as e:
            raise AdapterFetchError(
                f"Open-Meteo adapter fetch failed: {e}",
                source_code=self.source_code,
            ) from e
