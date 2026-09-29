import json
import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple, Union

try:
    import defusedxml.ElementTree as ET  # noqa: N817
except ImportError:
    import xml.etree.ElementTree as ET  # type: ignore[no-redef]  # noqa: N817

import httpx

from app.core.config import settings
from app.ingestion.base import BaseIngestionAdapter
from app.ingestion.exceptions import AdapterFetchError
from app.ingestion.schemas import RawIngestionEvent

logger = logging.getLogger(__name__)


class NDMASachetAdapter(BaseIngestionAdapter):
    """National Disaster Management Authority (NDMA) SACHET India CAP RSS / Feed Adapter.

    Ingests official multi-hazard disaster early warnings, Common Alerting Protocol (CAP)
    feeds, and geo-targeted alerts from the official NDMA SACHET portal (https://sachet.ndma.gov.in/).
    """

    NDMA_SEVERITY_MAP: Dict[str, str] = {
        # CAP Standard Severity Levels & Alert Colors
        "extreme": "SEVERE",
        "red": "SEVERE",
        "critical": "SEVERE",
        "severe": "HIGH",
        "orange": "HIGH",
        "amber": "HIGH",
        "warning": "HIGH",
        "moderate": "MODERATE",
        "yellow": "MODERATE",
        "watch": "MODERATE",
        "minor": "LOW",
        "green": "LOW",
        "white": "LOW",
        "advisory": "LOW",
        "unknown": "LOW",
        "nil": "LOW",
    }

    NDMA_CATEGORY_MAP: Dict[str, str] = {
        "thunderstorm": "THUNDERSTORM_LIGHTNING",
        "lightning": "THUNDERSTORM_LIGHTNING",
        "thunder": "THUNDERSTORM_LIGHTNING",
        "squall": "THUNDERSTORM_LIGHTNING",
        "cloudburst": "HEAVY_RAINFALL",
        "heavy rain": "HEAVY_RAINFALL",
        "rainfall": "HEAVY_RAINFALL",
        "downpour": "HEAVY_RAINFALL",
        "flash flood": "FLOOD_WATERLOGGING",
        "waterlogging": "FLOOD_WATERLOGGING",
        "inundation": "FLOOD_WATERLOGGING",
        "flood": "FLOOD_WATERLOGGING",
        "hailstorm": "HAILSTORM",
        "hail": "HAILSTORM",
        "landslide": "LANDSLIDE",
        "mudslide": "LANDSLIDE",
        "debris flow": "LANDSLIDE",
        "cyclone": "CYCLONE_GALE",
        "gale": "CYCLONE_GALE",
        "depression": "CYCLONE_GALE",
        "heatwave": "HEATWAVE",
        "heat": "HEATWAVE",
        "storm": "CYCLONE_GALE",
        "wind": "CYCLONE_GALE",
        "rain": "HEAVY_RAINFALL",
    }

    def __init__(
        self,
        source_code: str = "NDMA_SACHET",
        source_name: str = "NDMA SACHET India CAP",
        feed_url: Optional[str] = None,
        timeout_seconds: Optional[float] = None,
        custom_client: Optional[httpx.AsyncClient] = None,
    ) -> None:
        super().__init__(
            source_code=source_code,
            source_name=source_name,
            source_type="GOVERNMENT_PORTAL",
            base_trust_score=0.95,  # Official national disaster management authority
        )
        self.feed_url = feed_url or settings.NDMA_SACHET_RSS_URL
        self.timeout_seconds = (
            timeout_seconds
            if timeout_seconds is not None
            else settings.NDMA_REQUEST_TIMEOUT_SECONDS
        )
        self._custom_client = custom_client

    def _build_headers(self) -> Dict[str, str]:
        """Construct request headers for NDMA feed retrieval."""
        accept_types = (
            "application/json, application/rss+xml, application/xml, "
            "text/xml, application/atom+xml, text/plain, */*"
        )
        return {
            "Accept": accept_types,
            "User-Agent": "NationalWeatherPlatform-SIH26069/1.0",
        }

    @classmethod
    def map_ndma_severity(cls, raw_severity: Optional[str]) -> str:
        """Deterministically map NDMA / CAP severity levels and color codes to 4-tier domain."""
        if not raw_severity:
            return "MODERATE"
        clean = str(raw_severity).lower().strip()
        if clean in cls.NDMA_SEVERITY_MAP:
            return cls.NDMA_SEVERITY_MAP[clean]
        for key in sorted(cls.NDMA_SEVERITY_MAP.keys(), key=len, reverse=True):
            if key in clean:
                return cls.NDMA_SEVERITY_MAP[key]
        return "MODERATE"

    @classmethod
    def map_ndma_category(cls, raw_hazard: Optional[str], description: str = "") -> str:
        """Deterministically map NDMA disaster types to standard platform multi-hazard taxonomy."""
        combined = f"{raw_hazard or ''} {description}".lower()
        for key in sorted(cls.NDMA_CATEGORY_MAP.keys(), key=len, reverse=True):
            if key in combined:
                return cls.NDMA_CATEGORY_MAP[key]
        return "OTHER"

    @classmethod
    def parse_polygon_centroid(cls, polygon_str: str) -> Tuple[Optional[float], Optional[float]]:
        """Calculate arithmetic centroid from a CAP polygon coordinate string."""
        try:
            points: List[Tuple[float, float]] = []
            tokens = polygon_str.strip().split()
            for token in tokens:
                if "," in token:
                    parts = token.split(",")
                    points.append((float(parts[0]), float(parts[1])))
                elif " " in token:
                    parts = token.split()
                    points.append((float(parts[0]), float(parts[1])))

            if points:
                avg_lat = sum(p[0] for p in points) / len(points)
                avg_lon = sum(p[1] for p in points) / len(points)
                return round(avg_lat, 6), round(avg_lon, 6)
        except Exception as e:
            logger.debug(f"Failed to parse polygon coordinates '{polygon_str[:50]}': {e}")
        return None, None

    @classmethod
    def generate_external_id(cls, record: Dict[str, Any]) -> str:
        """Generate a stable, deterministic external identifier for an NDMA alert."""
        explicit_id = (
            record.get("identifier")
            or record.get("guid")
            or record.get("id")
            or record.get("alert_id")
            or record.get("link")
        )
        if explicit_id:
            clean_id = re.sub(r"[^a-zA-Z0-9_\-\.]", "_", str(explicit_id)).strip("_")
            return f"NDMA-{clean_id}"[:255]

        # Composite fallback: area + timestamp + event
        area_part = (
            record.get("area_description")
            or record.get("areaDesc")
            or record.get("area")
            or "NATIONAL"
        )
        time_part = (
            record.get("effective_start_time")
            or record.get("sent")
            or record.get("effective")
            or record.get("pubDate")
            or record.get("published")
            or datetime.now(timezone.utc).strftime("%Y%m%d%H")
        )
        event_part = (
            record.get("disaster_type") or record.get("event") or record.get("headline") or "ALERT"
        )

        clean_area = re.sub(r"[^a-zA-Z0-9]", "_", str(area_part).upper()).strip("_")
        clean_time = re.sub(r"[^a-zA-Z0-9]", "_", str(time_part)).strip("_")
        clean_event = re.sub(r"[^a-zA-Z0-9]", "_", str(event_part).upper()).strip("_")

        return f"NDMA-{clean_area}-{clean_time}-{clean_event}"[:255]

    def _strip_ns(self, tag: str) -> str:
        """Remove XML namespace URI prefix from element tag."""
        if "}" in tag:
            return tag.split("}", 1)[1]
        return tag

    def _element_to_dict(self, elem: ET.Element) -> Dict[str, Any]:
        """Convert an XML element and its immediate children into a flattened dictionary."""
        data: Dict[str, Any] = {}
        for child in elem:
            tag = self._strip_ns(child.tag)
            text = child.text.strip() if child.text else ""

            # Check nested structure (e.g., <info> or <area> inside CAP <alert>)
            if len(child) > 0:
                nested = self._element_to_dict(child)
                for k, v in nested.items():
                    if k not in data:
                        data[k] = v
                    else:
                        data[f"{tag}_{k}"] = v
            else:
                data[tag] = text

        return data

    def parse_alert_record(self, record: Dict[str, Any]) -> RawIngestionEvent:
        """Transform a parsed alert dictionary into a platform RawIngestionEvent."""
        external_id = self.generate_external_id(record)

        # Hazard / Disaster Type
        hazard_name = (
            record.get("disaster_type")
            or record.get("event")
            or record.get("category")
            or record.get("hazard")
            or "Disaster Alert"
        )

        # Location extraction
        location_name = (
            record.get("area_description")
            or record.get("areaDesc")
            or record.get("area")
            or record.get("district")
            or record.get("location")
        )

        # Title / Headline
        title = (
            record.get("headline")
            or record.get("title")
            or f"NDMA SACHET: {hazard_name} in {location_name or 'Affected Area'}"
        )
        title_str = str(title).strip()
        if len(title_str) > 255:
            title_str = title_str[:252] + "..."

        # Coordinate resolution
        latitude: Optional[float] = None
        longitude: Optional[float] = None

        # 1. Check centroid field (common in live NDMA JSON as "lon,lat" or "lat,lon")
        if "centroid" in record and record["centroid"]:
            centroid_val = record["centroid"]
            if isinstance(centroid_val, str) and "," in centroid_val:
                parts = [float(p.strip()) for p in centroid_val.split(",") if p.strip()]
                if len(parts) == 2:
                    if parts[0] > 40.0:  # Longitude first (Indian longitudes are ~68-98 E)
                        longitude, latitude = parts[0], parts[1]
                    else:
                        latitude, longitude = parts[0], parts[1]
            elif isinstance(centroid_val, (list, tuple)) and len(centroid_val) == 2:
                c1, c2 = float(centroid_val[0]), float(centroid_val[1])
                if c1 > 40.0:
                    longitude, latitude = c1, c2
                else:
                    latitude, longitude = c1, c2

        # 2. GeoJSON location dict (e.g. {"coordinates": [lon, lat], "type": "Point"})
        if latitude is None and isinstance(record.get("location"), dict):
            loc = record["location"]
            coords = loc.get("coordinates")
            if isinstance(coords, list) and len(coords) >= 2:
                longitude = float(coords[0])
                latitude = float(coords[1])

        # 3. Point / GeoRSS / WGS84
        if latitude is None and "point" in record and record["point"]:
            parts = record["point"].replace(",", " ").split()
            if len(parts) >= 2:
                try:
                    latitude = float(parts[0])
                    longitude = float(parts[1])
                except ValueError:
                    pass
        elif latitude is None and "lat" in record and "long" in record:
            try:
                latitude = float(record["lat"])
                longitude = float(record["long"])
            except ValueError:
                pass
        elif latitude is None and "latitude" in record and "longitude" in record:
            try:
                latitude = float(record["latitude"])
                longitude = float(record["longitude"])
            except ValueError:
                pass

        # 4. Polygon centroid
        if latitude is None and "polygon" in record and record["polygon"]:
            latitude, longitude = self.parse_polygon_centroid(record["polygon"])

        # 5. Circle center
        if latitude is None and "circle" in record and record["circle"]:
            circle_parts = record["circle"].split()
            if circle_parts and "," in circle_parts[0]:
                lat_str, lon_str = circle_parts[0].split(",")
                try:
                    latitude = float(lat_str)
                    longitude = float(lon_str)
                except ValueError:
                    pass

        # Severity
        raw_sev = (
            record.get("severity_color")
            or record.get("severity")
            or record.get("severity_level")
            or record.get("urgency")
            or record.get("color_code")
            or record.get("alert_level")
        )
        severity = self.map_ndma_severity(raw_sev)

        # Description & Instructions
        description = (
            record.get("warning_message")
            or record.get("description")
            or record.get("summary")
            or record.get("instruction")
            or f"NDMA SACHET alert for {location_name or 'affected area'}"
        )
        instruction = record.get("instruction")
        if instruction and instruction not in description:
            description = f"{description}\n\nInstructions: {instruction}"

        category_code = self.map_ndma_category(hazard_name, str(description))

        time_val = (
            record.get("effective_start_time")
            or record.get("sent")
            or record.get("effective")
            or record.get("onset")
            or record.get("pubDate")
            or record.get("published")
            or record.get("updated")
        )

        payload: Dict[str, Any] = {
            "title": title_str,
            "description": description,
            "latitude": latitude,
            "longitude": longitude,
            "location_name": location_name,
            "severity": severity,
            "category_code": category_code,
            "occurred_at": time_val,
            "external_id": external_id,
            "ndma_raw_record": record,
        }

        return RawIngestionEvent(
            source_code=self.source_code,
            external_id=external_id,
            payload=payload,
            ingested_at=datetime.now(timezone.utc),
        )

    def parse_feed_content(self, content: Union[str, bytes]) -> List[RawIngestionEvent]:
        """Parse XML RSS/Atom/CAP or JSON payload into platform RawIngestionEvent items."""
        if isinstance(content, bytes):
            content_str = content.decode("utf-8", errors="replace").strip()
        else:
            content_str = content.strip()

        if not content_str:
            return []

        # 1. JSON Feed Dispatch (e.g. FetchAllAlertDetails endpoint)
        if content_str.startswith("[") or content_str.startswith("{"):
            try:
                json_data = json.loads(content_str)
                raw_items: List[Dict[str, Any]] = []
                if isinstance(json_data, list):
                    raw_items = [it for it in json_data if isinstance(it, dict)]
                elif isinstance(json_data, dict):
                    if "alerts" in json_data and isinstance(json_data["alerts"], list):
                        raw_items = [it for it in json_data["alerts"] if isinstance(it, dict)]
                    elif "nowcastDetails" in json_data and isinstance(
                        json_data["nowcastDetails"], list
                    ):
                        raw_items = [
                            it for it in json_data["nowcastDetails"] if isinstance(it, dict)
                        ]
                    elif "data" in json_data and isinstance(json_data["data"], list):
                        raw_items = [it for it in json_data["data"] if isinstance(it, dict)]
                    elif "records" in json_data and isinstance(json_data["records"], list):
                        raw_items = [it for it in json_data["records"] if isinstance(it, dict)]
                    else:
                        raw_items = [json_data]

                events: List[RawIngestionEvent] = []
                for item in raw_items:
                    try:
                        event = self.parse_alert_record(item)
                        events.append(event)
                    except Exception as e:
                        logger.warning(f"Skipping unparseable NDMA JSON alert item: {e}")
                return events
            except json.JSONDecodeError:
                pass  # Fallback to XML parser

        # 2. XML / RSS / CAP Dispatch
        try:
            root = ET.fromstring(content_str.encode("utf-8"))
        except ET.ParseError as e:
            logger.warning(f"Failed to parse NDMA SACHET feed XML: {e}")
            raise AdapterFetchError(
                f"Malformed XML feed from '{self.source_code}': {e}", source_code=self.source_code
            )

        root_tag = self._strip_ns(root.tag).lower()
        items: List[ET.Element] = []

        # RSS 2.0 (<rss><channel><item>...)
        if root_tag == "rss":
            channel = root.find("channel")
            if channel is None:
                channel = root.find(".//{*}channel")
            if channel is not None:
                found_items = channel.findall("item")
                if not found_items:
                    found_items = channel.findall(".//{*}item")
                items = found_items
            else:
                items = root.findall(".//{*}item")

        # Atom 1.0 (<feed><entry>...)
        elif root_tag == "feed":
            found_entries = root.findall("entry")
            if not found_entries:
                found_entries = root.findall(".//{*}entry")
            items = found_entries

        # Standalone CAP Alert (<alert>...)
        elif root_tag == "alert":
            items = [root]

        # Fallback search
        else:
            fallback = root.findall(".//{*}item")
            if not fallback:
                fallback = root.findall(".//{*}entry")
            if not fallback:
                fallback = root.findall(".//{*}alert")
            items = fallback

        events_xml: List[RawIngestionEvent] = []
        for item_elem in items:
            try:
                record = self._element_to_dict(item_elem)
                if record:
                    event = self.parse_alert_record(record)
                    events_xml.append(event)
            except Exception as e:
                logger.warning(
                    f"Skipping unparseable NDMA XML alert item: {e}",
                    extra={"source": self.source_code},
                )

        return events_xml

    async def fetch_raw_events(self) -> List[RawIngestionEvent]:
        """Fetch raw disaster alert feed from the official NDMA SACHET endpoint."""
        headers = self._build_headers()
        client = self._custom_client or httpx.AsyncClient(timeout=self.timeout_seconds)
        should_close_client = self._custom_client is None

        try:
            response = await client.post(
                self.feed_url, json={}, headers=headers, follow_redirects=True
            )
            # If endpoint does not accept POST, fallback to GET
            if response.status_code == 405:
                response = await client.get(self.feed_url, headers=headers, follow_redirects=True)

            if response.status_code in (401, 403):
                logger.warning(
                    f"NDMA SACHET feed access requires authorization. "
                    f"Endpoint: {self.feed_url}, Status: {response.status_code}"
                )
                raise AdapterFetchError(
                    f"Authentication required for NDMA feed (HTTP {response.status_code}).",
                    source_code=self.source_code,
                )

            if response.status_code == 429:
                logger.warning(f"NDMA SACHET rate limit encountered (HTTP 429): {self.feed_url}")
                raise AdapterFetchError(
                    "NDMA SACHET rate limit exceeded (HTTP 429).", source_code=self.source_code
                )

            if response.status_code >= 500:
                logger.error(
                    f"NDMA SACHET server error (HTTP {response.status_code}): {self.feed_url}"
                )
                raise AdapterFetchError(
                    f"NDMA SACHET server error (HTTP {response.status_code}).",
                    source_code=self.source_code,
                )

            response.raise_for_status()
            return self.parse_feed_content(response.content)

        except httpx.TimeoutException as e:
            logger.warning(f"NDMA SACHET feed request timed out after {self.timeout_seconds}s: {e}")
            raise AdapterFetchError(
                f"NDMA SACHET request timeout: {e}", source_code=self.source_code
            )
        except httpx.ConnectError as e:
            logger.warning(f"NDMA SACHET connection failure: {e}")
            raise AdapterFetchError(
                f"NDMA SACHET connection failed: {e}", source_code=self.source_code
            )
        except Exception as e:
            if isinstance(e, AdapterFetchError):
                raise
            logger.error(f"Unexpected error during NDMA SACHET fetch: {e}", exc_info=True)
            raise AdapterFetchError(
                f"Unexpected NDMA fetch error: {e}", source_code=self.source_code
            )
        finally:
            if should_close_client:
                await client.aclose()
