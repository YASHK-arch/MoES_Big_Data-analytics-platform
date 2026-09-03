"""GDACS (Global Disaster Alert and Coordination System) Ingestion Adapter.

Polls the GDACS event list API for active flood, cyclone, and other hydro-meteorological
disaster alerts affecting India. Produces NormalizedIngestionEvent records routed to
stream:weather:events.

GDACS API Contract:
    GET https://www.gdacs.org/gdacsapi/api/events/geteventlist/SEARCH
    ?eventlist=FL,TC,DR,WF
    &fromdate=YYYY-MM-DD
    &todate=YYYY-MM-DD

Alert levels: 1 = Green, 2 = Orange, 3 = Red.
Event types: FL (Flood), TC (Tropical Cyclone), DR (Drought), WF (Wildfire), EQ (Earthquake).

No authentication required for the public feed.
Rate limiting: Honour GDACS_MIN_REQUEST_INTERVAL_SECONDS (default 5.0s).
"""

import asyncio
import hashlib
import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

import httpx

from app.core.config import settings
from app.ingestion.exceptions import AdapterFetchError
from app.ingestion.schemas import NormalizedIngestionEvent

logger = logging.getLogger(__name__)


class GDACSAlertAdapter:
    """Ingestion adapter for GDACS public disaster event feed (India-scoped).

    GDACS coordinates are ground-truth centroids published by the UN OCHA
    humanitarian system. They are used directly as incident coordinates.
    """

    GDACS_ENDPOINT = "https://www.gdacs.org/gdacsapi/api/events/geteventlist/SEARCH"
    USER_AGENT = "NationalWeatherPlatform-SIH26069/1.0 (sih26069@weather-platform.gov.in)"

    # GDACS alert level → domain severity mapping
    ALERT_SEVERITY_MAP: Dict[int, str] = {
        1: "LOW",       # Green — minor impact expected
        2: "HIGH",      # Orange — moderate to serious impact expected
        3: "SEVERE",    # Red — serious impact expected / mass casualty risk
    }
    # Textual fallback for alert_level strings published in some responses
    ALERT_TEXT_MAP: Dict[str, str] = {
        "green": "LOW",
        "orange": "HIGH",
        "red": "SEVERE",
    }

    # GDACS event type → domain category mapping
    EVENT_CATEGORY_MAP: Dict[str, str] = {
        "FL": "FLOOD_WATERLOGGING",
        "TC": "CYCLONE_GALE",
        "DR": "HEATWAVE",           # Drought — closest thermal extreme proxy
        "WF": "OTHER",              # Wildfire — not in primary taxonomy, use OTHER
        "EQ": "OTHER",              # Earthquake — not a hydro-met event
        "TS": "CYCLONE_GALE",       # Tsunami — coastal wave, closest proxy
        "VO": "OTHER",              # Volcano
    }

    # Event types to request from GDACS (hydro-meteorological only)
    HYDRO_EVENT_TYPES = ["FL", "TC", "DR", "WF"]

    def __init__(
        self,
        endpoint: Optional[str] = None,
        event_types: Optional[List[str]] = None,
        country_code: Optional[str] = None,
        lookback_days: Optional[int] = None,
        min_interval_seconds: Optional[float] = None,
        timeout_seconds: Optional[float] = None,
        http_client: Optional[httpx.AsyncClient] = None,
    ) -> None:
        self.source_code = "GDACS_FEED"
        self.source_name = "GDACS Global Disaster Alert and Coordination System"
        self.source_type = "INTERNATIONAL_ALERT"
        self.base_trust_score = 0.88  # UN-coordinated authoritative international alert system

        self.endpoint = endpoint or getattr(settings, "GDACS_ENDPOINT", self.GDACS_ENDPOINT)
        self.event_types = event_types or getattr(
            settings, "GDACS_EVENT_TYPES", self.HYDRO_EVENT_TYPES
        )
        self.country_code = country_code or getattr(settings, "GDACS_COUNTRY_CODE", "IND")
        self.lookback_days = lookback_days if lookback_days is not None else getattr(
            settings, "GDACS_LOOKBACK_DAYS", 7
        )
        self.min_interval_seconds = min_interval_seconds if min_interval_seconds is not None else getattr(
            settings, "GDACS_MIN_REQUEST_INTERVAL_SECONDS", 5.0
        )
        self.timeout_seconds = timeout_seconds or getattr(settings, "GDACS_REQUEST_TIMEOUT_SECONDS", 15.0)
        self._http_client = http_client
        self._last_request_time: float = 0.0

    async def _get_client(self) -> httpx.AsyncClient:
        if self._http_client and not self._http_client.is_closed:
            return self._http_client
        return httpx.AsyncClient(
            timeout=httpx.Timeout(self.timeout_seconds),
            headers={
                "User-Agent": self.USER_AGENT,
                "Accept": "application/json",
            },
            follow_redirects=True,
        )

    async def _apply_rate_limit(self) -> None:
        """Enforce minimum inter-request interval to respect GDACS usage policy."""
        elapsed = time.monotonic() - self._last_request_time
        if elapsed < self.min_interval_seconds:
            await asyncio.sleep(self.min_interval_seconds - elapsed)
        self._last_request_time = time.monotonic()

    def _build_params(self) -> Dict[str, Any]:
        now = datetime.now(timezone.utc)
        from_date = (now - timedelta(days=self.lookback_days)).strftime("%Y-%m-%d")
        to_date = now.strftime("%Y-%m-%d")
        return {
            "eventlist": ",".join(self.event_types),
            "fromdate": from_date,
            "todate": to_date,
        }

    @classmethod
    def _map_severity(cls, alert_level: Any) -> str:
        """Deterministically map GDACS alert level to domain severity."""
        if isinstance(alert_level, int):
            return cls.ALERT_SEVERITY_MAP.get(alert_level, "MODERATE")
        if isinstance(alert_level, str):
            clean = alert_level.lower().strip()
            if clean in cls.ALERT_TEXT_MAP:
                return cls.ALERT_TEXT_MAP[clean]
            try:
                return cls.ALERT_SEVERITY_MAP.get(int(clean), "MODERATE")
            except (ValueError, TypeError):
                pass
        return "MODERATE"

    @classmethod
    def _map_category(cls, event_type: Optional[str]) -> str:
        """Map GDACS event type code to domain hazard category."""
        if not event_type:
            return "OTHER"
        return cls.EVENT_CATEGORY_MAP.get(event_type.upper().strip(), "OTHER")

    @classmethod
    def _generate_external_id(cls, event: Dict[str, Any]) -> str:
        """Generate a deterministic, stable external identifier for a GDACS event."""
        event_id = event.get("eventid") or event.get("id") or event.get("eventID")
        event_type = event.get("eventtype") or event.get("type") or "UNKNOWN"

        if event_id:
            return f"GDACS-{str(event_type).upper()}-{str(event_id)}"[:255]

        # Fallback: hash of title + from_date
        title = str(event.get("name") or event.get("title") or "")
        from_date = str(event.get("fromdate") or event.get("startdate") or "")
        content = f"{event_type}:{title}:{from_date}"
        sha = hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]
        return f"GDACS-{str(event_type).upper()}-{sha}"[:255]

    @classmethod
    def _extract_coordinates(cls, event: Dict[str, Any]) -> Tuple[Optional[float], Optional[float]]:
        """Extract validated WGS84 lat/lon from a GDACS event record."""
        # GDACS API response shapes vary — check multiple field names
        lat = (
            event.get("latitude")
            or event.get("lat")
            or event.get("centroid_latitude")
        )
        lon = (
            event.get("longitude")
            or event.get("lon")
            or event.get("lng")
            or event.get("centroid_longitude")
        )

        # Try nested bbox centroid
        if lat is None or lon is None:
            bbox = event.get("bbox")
            if isinstance(bbox, dict):
                lat = lat or bbox.get("centroid", {}).get("lat")
                lon = lon or bbox.get("centroid", {}).get("lon")

        # Try coordinates array [lon, lat] as per GeoJSON convention
        if lat is None or lon is None:
            coords = event.get("coordinates")
            if isinstance(coords, list) and len(coords) >= 2:
                lon = coords[0]
                lat = coords[1]

        try:
            flat = float(lat)  # type: ignore[arg-type]
            flon = float(lon)  # type: ignore[arg-type]
            if -90 <= flat <= 90 and -180 <= flon <= 180:
                return flat, flon
        except (TypeError, ValueError):
            pass
        return None, None

    @classmethod
    def _parse_gdacs_timestamp(cls, raw: Optional[Any]) -> Optional[datetime]:
        """Parse a GDACS date string into a UTC datetime."""
        if not raw:
            return None
        raw_str = str(raw).strip()
        for fmt in (
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%dT%H:%M:%SZ",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d",
            "%d %b %Y %H:%M:%S",
            "%d %b %Y",
        ):
            try:
                dt = datetime.strptime(raw_str[:len(fmt)], fmt)
                return dt.replace(tzinfo=timezone.utc)
            except (ValueError, TypeError):
                continue
        return None

    def _parse_event(self, event: Dict[str, Any]) -> Optional[NormalizedIngestionEvent]:
        """Transform a single GDACS event dict into a NormalizedIngestionEvent."""
        external_id = self._generate_external_id(event)
        event_type = (event.get("eventtype") or event.get("type") or "").upper().strip()

        lat, lon = self._extract_coordinates(event)
        if lat is None or lon is None:
            logger.debug(
                "Skipping GDACS event %s: no valid coordinates.", external_id
            )
            return None

        # Title / name
        name = (
            event.get("name")
            or event.get("title")
            or event.get("eventname")
            or f"GDACS {event_type} Alert"
        )
        title = f"GDACS {event_type}: {name}"
        if len(title) > 255:
            title = title[:252] + "..."

        # Description
        description = (
            event.get("description")
            or event.get("alertlevel_detail")
            or event.get("summary")
            or f"GDACS {event_type} alert for {self.country_code}. Alert level: {event.get('alertlevel', 'unknown')}."
        )

        # Severity
        alert_level = event.get("alertlevel") or event.get("alert_level") or event.get("severity")
        severity = self._map_severity(alert_level)

        # Category
        category_code = self._map_category(event_type)

        # Occurred at
        raw_from = (
            event.get("fromdate")
            or event.get("startdate")
            or event.get("date")
            or event.get("eventdate")
        )
        occurred_at = self._parse_gdacs_timestamp(raw_from) or datetime.now(timezone.utc)

        # Location name
        country_name = event.get("country") or event.get("countryname") or self.country_code
        location_name = f"{name}, {country_name}" if name else country_name
        if location_name and len(location_name) > 255:
            location_name = location_name[:252] + "..."

        return NormalizedIngestionEvent(
            source_code=self.source_code,
            external_id=external_id,
            category_code=category_code,
            severity=severity,
            title=title,
            description=description,
            latitude=lat,
            longitude=lon,
            location_name=location_name,
            occurred_at=occurred_at,
            raw_payload=event,
            metadata={
                "gdacs_event_type": event_type,
                "gdacs_alert_level": alert_level,
                "gdacs_country": self.country_code,
                "gdacs_source": "gdacsapi_v2",
            },
        )

    def _matches_country(self, event: Dict[str, Any]) -> bool:
        """Keep only events whose GDACS country metadata matches the configured country."""
        target = self.country_code.strip().upper()
        target_name = {"IND": "INDIA"}.get(target, target)
        iso3 = str(event.get("iso3") or event.get("countrycode") or "").strip().upper()
        if iso3:
            return iso3 == target

        country_value = event.get("country") or event.get("countryname")
        countries = {
            part.strip().upper()
            for part in str(country_value or "").split(",")
            if part.strip()
        }
        return target in countries or target_name in countries

    def _parse_response(self, data: Any) -> List[NormalizedIngestionEvent]:
        """Extract and parse the event list from the GDACS API response envelope."""
        raw_events: List[Dict[str, Any]] = []

        if isinstance(data, list):
            raw_events = [e for e in data if isinstance(e, dict)]
        elif isinstance(data, dict):
            # GDACS wraps results under different keys depending on endpoint version
            for key in ("features", "events", "items", "results", "data"):
                val = data.get(key)
                if isinstance(val, list):
                    # GeoJSON FeatureCollection: each feature has a 'properties' dict
                    for item in val:
                        if isinstance(item, dict):
                            if "properties" in item and isinstance(item["properties"], dict):
                                # GeoJSON Feature — merge geometry coords into properties
                                props = dict(item["properties"])
                                geom = item.get("geometry") or {}
                                coords = geom.get("coordinates")
                                if isinstance(coords, list) and len(coords) >= 2:
                                    props.setdefault("longitude", coords[0])
                                    props.setdefault("latitude", coords[1])
                                raw_events.append(props)
                            else:
                                raw_events.append(item)
                    break

        if not raw_events:
            logger.info(
                "GDACS API returned 0 raw events for country=%s, types=%s.",
                self.country_code, self.event_types,
            )

        normalized: List[NormalizedIngestionEvent] = []
        for evt in raw_events:
            if not self._matches_country(evt):
                continue
            try:
                result = self._parse_event(evt)
                if result is not None:
                    normalized.append(result)
            except Exception as e:
                logger.warning("Failed to parse GDACS event: %s — %s", evt.get("eventid"), e)

        return normalized

    async def fetch_raw_events(self) -> List[NormalizedIngestionEvent]:
        """Fetch active disaster alerts from GDACS for the configured country and event types."""
        await self._apply_rate_limit()

        params = self._build_params()
        client = await self._get_client()
        should_close = client != self._http_client

        try:
            response = await client.get(self.endpoint, params=params)

            if response.status_code == 429:
                logger.warning("GDACS API rate limit encountered (HTTP 429).")
                raise AdapterFetchError("GDACS rate limit exceeded (HTTP 429).", source_code=self.source_code)

            if response.status_code >= 500:
                logger.error("GDACS API server error (HTTP %d).", response.status_code)
                raise AdapterFetchError(
                    f"GDACS API server error (HTTP {response.status_code}).",
                    source_code=self.source_code,
                )

            if response.status_code not in (200, 201, 206):
                logger.warning(
                    "GDACS API unexpected status %d: %s",
                    response.status_code, response.text[:200],
                )
                return []

            try:
                data = response.json()
            except Exception as e:
                logger.warning("Failed to decode GDACS JSON response: %s", e)
                return []

            events = self._parse_response(data)
            logger.info(
                "GDACS ingestion complete: %d events parsed for country=%s.",
                len(events), self.country_code,
            )
            return events

        except httpx.TimeoutException:
            logger.warning("GDACS API request timed out after %ss.", self.timeout_seconds)
            raise AdapterFetchError("GDACS API timeout.", source_code=self.source_code)
        except httpx.ConnectError as e:
            logger.warning("GDACS API connection error: %s", e)
            raise AdapterFetchError(f"GDACS connection failed: {e}", source_code=self.source_code)
        except AdapterFetchError:
            raise
        except Exception as e:
            logger.error("Unexpected error in GDACS adapter: %s", e, exc_info=True)
            raise AdapterFetchError(f"Unexpected GDACS fetch error: {e}", source_code=self.source_code) from e
        finally:
            if should_close:
                await client.aclose()

    async def ingest(self) -> List[NormalizedIngestionEvent]:
        """Execute full fetch cycle and return normalized incident events."""
        return await self.fetch_raw_events()
