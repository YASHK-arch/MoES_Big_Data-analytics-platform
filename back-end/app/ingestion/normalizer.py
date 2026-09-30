import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, Union

from app.ingestion.exceptions import NormalizationError
from app.ingestion.schemas import NormalizedIngestionEvent, RawIngestionEvent
from app.intelligence.category_rules import classify_text_category


class EventNormalizer:
    """Normalizes, cleanses, and validates heterogeneous raw ingestion events."""

    VALID_CATEGORIES = {
        "FLOOD_WATERLOGGING",
        "HEAVY_RAINFALL",
        "THUNDERSTORM_LIGHTNING",
        "CYCLONE_STORM",
        "HEATWAVE",
        "HAILSTORM",
        "LANDSLIDE",
        "DROUGHT",
        "URBAN_FLOOD",
        "FOG",
        "DUST_STORM",
        "STRONG_WIND",
        "OTHER",
    }

    CATEGORY_MAP: Dict[str, str] = {
        # Thunderstorm & Lightning (English + Hindi/Hinglish)
        "thunderstorm": "THUNDERSTORM_LIGHTNING",
        "lightning": "THUNDERSTORM_LIGHTNING",
        "thunder": "THUNDERSTORM_LIGHTNING",
        "squall": "THUNDERSTORM_LIGHTNING",
        "bijli": "THUNDERSTORM_LIGHTNING",
        "bijlee": "THUNDERSTORM_LIGHTNING",
        "garaj": "THUNDERSTORM_LIGHTNING",
        # Rainfall & Monsoon
        "cloudburst": "HEAVY_RAINFALL",
        "heavy_rain": "HEAVY_RAINFALL",
        "rainfall": "HEAVY_RAINFALL",
        "downpour": "HEAVY_RAINFALL",
        "deluge": "HEAVY_RAINFALL",
        "rain": "HEAVY_RAINFALL",
        "baarish": "HEAVY_RAINFALL",
        "barish": "HEAVY_RAINFALL",
        "barsat": "HEAVY_RAINFALL",
        "musladhar": "HEAVY_RAINFALL",
        # Flooding & Waterlogging
        "waterlogging": "FLOOD_WATERLOGGING",
        "waterlog": "FLOOD_WATERLOGGING",
        "flooding": "FLOOD_WATERLOGGING",
        "flood": "FLOOD_WATERLOGGING",
        "inundation": "FLOOD_WATERLOGGING",
        "baadh": "FLOOD_WATERLOGGING",
        "badh": "FLOOD_WATERLOGGING",
        "jalbharao": "FLOOD_WATERLOGGING",
        "jalbhorao": "FLOOD_WATERLOGGING",
        # Urban Flood
        "urban_flood": "URBAN_FLOOD",
        "urban_flooding": "URBAN_FLOOD",
        "city_flood": "URBAN_FLOOD",
        "shahri_baadh": "URBAN_FLOOD",
        # Hailstorm
        "hailstorm": "HAILSTORM",
        "hail": "HAILSTORM",
        "olavrishti": "HAILSTORM",
        "ole": "HAILSTORM",
        "ola": "HAILSTORM",
        # Landslide
        "landslide": "LANDSLIDE",
        "mudslide": "LANDSLIDE",
        "rockfall": "LANDSLIDE",
        "bhooskhalan": "LANDSLIDE",
        "bhuskhalan": "LANDSLIDE",
        # Cyclone & Storm
        "cyclone_gale": "CYCLONE_STORM",
        "cyclone_storm": "CYCLONE_STORM",
        "cyclone": "CYCLONE_STORM",
        "gale": "CYCLONE_STORM",
        "storm": "CYCLONE_STORM",
        "chakravat": "CYCLONE_STORM",
        "samudri_toofan": "CYCLONE_STORM",
        # Heatwave
        "heatwave": "HEATWAVE",
        "extreme_heat": "HEATWAVE",
        "heat": "HEATWAVE",
        "loo": "HEATWAVE",
        "garmi": "HEATWAVE",
        "tapman": "HEATWAVE",
        # Drought
        "drought": "DROUGHT",
        "dry_spell": "DROUGHT",
        "water_scarcity": "DROUGHT",
        "sookha": "DROUGHT",
        "sukha": "DROUGHT",
        "akaal": "DROUGHT",
        # Fog
        "dense_fog": "FOG",
        "fog": "FOG",
        "mist": "FOG",
        "smog": "FOG",
        "kohra": "FOG",
        "dhund": "FOG",
        "kuhra": "FOG",
        # Dust Storm
        "dust_storm": "DUST_STORM",
        "sandstorm": "DUST_STORM",
        "dust": "DUST_STORM",
        "dhool_toofan": "DUST_STORM",
        "dhool_aandhi": "DUST_STORM",
        "retila_toofan": "DUST_STORM",
        # Strong Wind
        "strong_wind": "STRONG_WIND",
        "high_wind": "STRONG_WIND",
        "gust": "STRONG_WIND",
        "wind": "STRONG_WIND",
        "tez_hawa": "STRONG_WIND",
        "jhakkad": "STRONG_WIND",
        "aandhi": "STRONG_WIND",
    }

    SEVERITY_MAP: Dict[str, str] = {
        "critical": "SEVERE",
        "extreme": "SEVERE",
        "severe": "SEVERE",
        "danger": "SEVERE",
        "red": "SEVERE",
        "high": "HIGH",
        "orange": "HIGH",
        "warning": "HIGH",
        "moderate": "MODERATE",
        "medium": "MODERATE",
        "yellow": "MODERATE",
        "low": "LOW",
        "minor": "LOW",
        "green": "LOW",
        "advisory": "LOW",
    }

    @classmethod
    def parse_coordinate(cls, value: Any, field_name: str, min_val: float, max_val: float) -> float:
        """Parse and strictly validate latitude or longitude."""
        try:
            coord = float(value)
        except (ValueError, TypeError):
            raise NormalizationError(
                f"Invalid coordinate value '{value}'. Must be a float.",
                field=field_name,
            )

        if not (min_val <= coord <= max_val):
            raise NormalizationError(
                f"Coordinate value {coord} is out of valid bounds [{min_val}, {max_val}].",
                field=field_name,
            )
        return coord

    @classmethod
    def parse_timestamp(cls, value: Union[str, int, float, datetime, None]) -> datetime:
        """Parse and validate timestamp into timezone-aware UTC datetime."""
        if value is None:
            return datetime.now(timezone.utc)

        parsed_dt: Optional[datetime] = None
        if isinstance(value, datetime):
            parsed_dt = value
        elif isinstance(value, (int, float)):
            try:
                parsed_dt = datetime.fromtimestamp(value, tz=timezone.utc)
            except (ValueError, OverflowError, OSError) as e:
                raise NormalizationError(
                    f"Invalid numeric epoch timestamp: {e}", field="occurred_at"
                )
        elif isinstance(value, str):
            clean_str = value.strip()

            # Handle Indian Standard Time (IST) text format: 'Sat Aug 29 12:48:00 IST 2026'
            if "IST" in clean_str:
                try:
                    # Remove multiple spaces after replacing IST
                    stripped_ist = re.sub(r"\s+", " ", clean_str.replace("IST", "")).strip()
                    dt_no_tz = datetime.strptime(stripped_ist, "%a %b %d %H:%M:%S %Y")
                    ist_tz = timezone(timedelta(hours=5, minutes=30))
                    parsed_dt = dt_no_tz.replace(tzinfo=ist_tz)
                except ValueError:
                    pass

            if parsed_dt is None:
                # Try standard ISO-8601 parsing
                try:
                    parsed_dt = datetime.fromisoformat(clean_str.replace("Z", "+00:00"))
                except ValueError:
                    # Try common fallback date formats
                    fallback_formats = [
                        "%Y-%m-%d %H:%M:%S",
                        "%Y-%m-%dT%H:%M:%S",
                        "%Y-%m-%d",
                        "%d-%m-%Y %H:%M:%S",
                        "%d/%m/%Y %H:%M:%S",
                        "%a, %d %b %Y %H:%M:%S %z",
                        "%a, %d %b %Y %H:%M:%S GMT",
                        "%a %b %d %H:%M:%S %Y",
                    ]
                    matched = False
                    for fmt in fallback_formats:
                        try:
                            parsed_dt = datetime.strptime(clean_str, fmt)
                            matched = True
                            break
                        except ValueError:
                            continue
                    if not matched:
                        raise NormalizationError(
                            f"Unrecognized date/time format: '{clean_str}'",
                            field="occurred_at",
                        )
        else:
            raise NormalizationError(
                f"Unsupported timestamp type '{type(value)}'", field="occurred_at"
            )

        assert parsed_dt is not None
        if parsed_dt.tzinfo is None:
            parsed_dt = parsed_dt.replace(tzinfo=timezone.utc)
        else:
            parsed_dt = parsed_dt.astimezone(timezone.utc)

        # Sanity check: Reject dates > 24 hours in the future or > 365 days in past
        now = datetime.now(timezone.utc)
        if parsed_dt > now + timedelta(hours=24):
            raise NormalizationError(
                f"Timestamp '{parsed_dt.isoformat()}' is skewed > 24h into future.",
                field="occurred_at",
            )
        if parsed_dt < now - timedelta(days=365):
            raise NormalizationError(
                f"Timestamp '{parsed_dt.isoformat()}' is older than 365 days.",
                field="occurred_at",
            )

        return parsed_dt

    @classmethod
    def normalize_severity(cls, raw_sev: Optional[str]) -> str:
        """Map heterogeneous severity labels to platform enum."""
        if not raw_sev:
            return "MODERATE"
        clean = str(raw_sev).lower().strip()
        return cls.SEVERITY_MAP.get(clean, "MODERATE")

    @classmethod
    def normalize_category(cls, raw_cat: Optional[str], title: str = "") -> str:
        """Standardize category code."""
        legacy_map = {
            "CYCLONE_GALE": "CYCLONE_STORM",
            "EXTREME_HEAT": "HEATWAVE",
        }
        if raw_cat:
            upper_clean = str(raw_cat).upper().strip()
            if upper_clean in legacy_map:
                return legacy_map[upper_clean]
            if upper_clean in cls.VALID_CATEGORIES:
                return upper_clean

            sorted_items = sorted(cls.CATEGORY_MAP.items(), key=lambda x: len(x[0]), reverse=True)
            clean = re.sub(r"[^a-z0-9_]", "_", str(raw_cat).lower().strip())
            for key, mapped in sorted_items:
                if key in clean:
                    return mapped

        # Fallback inspection on title keywords
        classified = classify_text_category(title)
        if classified != "OTHER":
            return classified

        clean_title = title.lower()
        sorted_items = sorted(cls.CATEGORY_MAP.items(), key=lambda x: len(x[0]), reverse=True)
        for key, mapped in sorted_items:
            if key in clean_title:
                return mapped

        return "OTHER"

    @classmethod
    def normalize(cls, raw: RawIngestionEvent) -> NormalizedIngestionEvent:
        """Normalize a raw ingestion event into a strictly validated NormalizedIngestionEvent."""
        payload = raw.payload or {}

        # 1. Title extraction
        title = (
            payload.get("title")
            or payload.get("headline")
            or payload.get("event_name")
            or payload.get("summary")
            or f"Weather event from {raw.source_code}"
        )
        title_str = str(title).strip()
        if len(title_str) < 3:
            title_str = f"Weather Report ({raw.source_code})"
        if len(title_str) > 255:
            title_str = title_str[:252] + "..."

        # 2. Coordinates
        lat_val = (
            payload.get("latitude")
            or payload.get("lat")
            or payload.get("geo_lat")
            or (
                payload.get("location", {}).get("lat")
                if isinstance(payload.get("location"), dict)
                else None
            )
        )
        lon_val = (
            payload.get("longitude")
            or payload.get("lon")
            or payload.get("long")
            or payload.get("geo_lon")
            or (
                payload.get("location", {}).get("lon")
                if isinstance(payload.get("location"), dict)
                else None
            )
        )

        if lat_val is None or lon_val is None:
            raise NormalizationError(
                "Missing required latitude or longitude coordinates.", field="coordinates"
            )

        latitude = cls.parse_coordinate(lat_val, "latitude", -90.0, 90.0)
        longitude = cls.parse_coordinate(lon_val, "longitude", -180.0, 180.0)

        # 3. Timestamp
        time_val = (
            payload.get("occurred_at")
            or payload.get("timestamp")
            or payload.get("time")
            or payload.get("pubDate")
            or payload.get("published_at")
        )
        occurred_at = cls.parse_timestamp(time_val)

        # 4. Severity & Category
        severity = cls.normalize_severity(payload.get("severity") or payload.get("urgency"))
        category_code = cls.normalize_category(
            payload.get("category_code") or payload.get("category") or payload.get("hazard_type"),
            title=title_str,
        )

        # 5. Description & Location Name
        description = payload.get("description") or payload.get("details") or payload.get("text")
        description_str = str(description).strip() if description else None

        location_name = (
            payload.get("location_name")
            or payload.get("place")
            or payload.get("district")
            or payload.get("city")
            or (
                payload.get("location", {}).get("name")
                if isinstance(payload.get("location"), dict)
                else None
            )
        )
        location_name_str = str(location_name).strip()[:255] if location_name else None

        # 6. External ID
        external_id = (
            raw.external_id
            or payload.get("external_id")
            or payload.get("id")
            or payload.get("guid")
        )
        external_id_str = str(external_id).strip()[:255] if external_id else None

        return NormalizedIngestionEvent(
            source_code=raw.source_code.strip().upper(),
            external_id=external_id_str,
            category_code=category_code,
            severity=severity,
            title=title_str,
            description=description_str,
            latitude=latitude,
            longitude=longitude,
            location_name=location_name_str,
            occurred_at=occurred_at,
            ingested_at=raw.ingested_at,
            raw_payload=payload,
            metadata=payload.get("metadata", {}),
        )
