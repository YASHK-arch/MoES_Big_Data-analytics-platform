"""Pure evaluation logic for physical meteorological corroboration (No DB, No Network)."""

import math
from datetime import datetime, timezone
from typing import Optional, Tuple

from app.intelligence.physical_corroboration.config import (
    PhysicalCorroborationConfig,
    default_physical_config,
)
from app.intelligence.physical_corroboration.models import (
    PhysicalCorroborationResult,
    PhysicalCorroborationVerdict,
    PhysicalObservation,
    PhysicalSourceType,
    ProviderStatus,
)


def compute_grid_hour_cache_key(
    latitude: float,
    longitude: float,
    observed_time: datetime,
    grid_size: float = 0.25,
) -> str:
    """Compute spatial ~0.25 degree grid and hourly discretized cache key.

    Example: cache:weather:physical:28.50:77.25:2026-10-01T12
    """
    lat_grid = round(latitude / grid_size) * grid_size
    lon_grid = round(longitude / grid_size) * grid_size

    # Ensure UTC
    if observed_time.tzinfo is None:
        dt_utc = observed_time.replace(tzinfo=timezone.utc)
    else:
        dt_utc = observed_time.astimezone(timezone.utc)

    date_hour = dt_utc.strftime("%Y-%m-%dT%H")
    return f"cache:weather:physical:{lat_grid:.2f}:{lon_grid:.2f}:{date_hour}"


def haversine_distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate the great circle distance between two points on Earth in kilometers."""
    radius_earth_km = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2.0) ** 2
        + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2.0) ** 2
    )
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return radius_earth_km * c


def evaluate(
    category: str,
    observation: PhysicalObservation,
    incident_time: datetime,
    incident_coords: Tuple[float, float],
    config: Optional[PhysicalCorroborationConfig] = None,
) -> PhysicalCorroborationResult:
    """Evaluate whether physical observation SUPPORTS, CONTRADICTS, or is NEUTRAL to an incident.

    Pure mathematical logic: Deterministic, no network, no database calls.
    """
    cfg = config or default_physical_config
    inc_lat, inc_lon = incident_coords

    # 1. Geodesic distance calculation
    distance_km = haversine_distance_km(
        inc_lat, inc_lon, observation.latitude, observation.longitude
    )
    max_distance = (
        cfg.max_distance_station_km
        if observation.source_type == PhysicalSourceType.STATION
        else cfg.max_distance_model_km
    )

    # 2. Time gap calculation (normalized to UTC)
    inc_dt = incident_time if incident_time.tzinfo else incident_time.replace(tzinfo=timezone.utc)
    obs_dt = (
        observation.observed_at
        if observation.observed_at.tzinfo
        else observation.observed_at.replace(tzinfo=timezone.utc)
    )
    time_gap_seconds = abs((inc_dt - obs_dt).total_seconds())
    time_gap_hours = time_gap_seconds / 3600.0

    # Distance check
    if distance_km > max_distance:
        return PhysicalCorroborationResult(
            verdict=PhysicalCorroborationVerdict.NEUTRAL,
            observed_value=None,
            source=observation.source_name,
            source_type=observation.source_type,
            station_or_grid_id=observation.station_or_grid_id,
            distance_km=round(distance_km, 2),
            time_gap_hours=round(time_gap_hours, 2),
            provider_status=ProviderStatus.TOO_FAR,
            explanation=f"Observation station is {distance_km:.1f} km away (limit: {max_distance:.1f} km)",
            is_simulated=observation.is_simulated,
        )

    # Category normalization
    cat = (category or "OTHER").upper()

    # Determine allowable time window per hazard family
    if cat in ("HEAVY_RAINFALL", "FLOOD_WATERLOGGING", "URBAN_FLOOD", "LANDSLIDE"):
        max_time_window = cfg.max_time_gap_precipitation_hours
    elif cat == "HEATWAVE":
        max_time_window = cfg.max_time_gap_heatwave_hours
    else:
        max_time_window = cfg.max_time_gap_transient_hours

    if time_gap_hours > max_time_window:
        return PhysicalCorroborationResult(
            verdict=PhysicalCorroborationVerdict.NEUTRAL,
            observed_value=None,
            source=observation.source_name,
            source_type=observation.source_type,
            station_or_grid_id=observation.station_or_grid_id,
            distance_km=round(distance_km, 2),
            time_gap_hours=round(time_gap_hours, 2),
            provider_status=ProviderStatus.STALE_DATA,
            explanation=f"Observation time gap {time_gap_hours:.1f}h exceeds limit ({max_time_window:.1f}h)",
            is_simulated=observation.is_simulated,
        )

    # 3. Rule Evaluation per Category
    verdict = PhysicalCorroborationVerdict.NEUTRAL
    observed_val: Optional[float] = None
    unit = ""
    variable = ""
    explanation = ""

    # HEAVY RAINFALL
    if cat == "HEAVY_RAINFALL":
        rain_24h = observation.rainfall_24h_mm
        rain_1h = observation.rainfall_1h_mm
        if rain_24h is not None and rain_24h >= cfg.heavy_rain_24h_mm:
            verdict = PhysicalCorroborationVerdict.SUPPORTS
            observed_val = rain_24h
            unit = "mm/24h"
            variable = "rainfall_24h"
            explanation = f"Measured 24h rainfall of {rain_24h:.1f} mm exceeds IMD heavy rain threshold ({cfg.heavy_rain_24h_mm} mm)"
        elif rain_1h is not None and rain_1h >= cfg.intense_rain_1h_mm:
            verdict = PhysicalCorroborationVerdict.SUPPORTS
            observed_val = rain_1h
            unit = "mm/1h"
            variable = "rainfall_1h"
            explanation = f"Measured 1h rainfall of {rain_1h:.1f} mm indicates intense downpour/cloudburst ({cfg.intense_rain_1h_mm} mm)"
        elif rain_24h is not None and rain_24h <= cfg.contradict_rain_24h_mm:
            verdict = PhysicalCorroborationVerdict.CONTRADICTS
            observed_val = rain_24h
            unit = "mm/24h"
            variable = "rainfall_24h"
            explanation = f"Station recorded {rain_24h:.1f} mm rainfall (dry conditions, threshold <= {cfg.contradict_rain_24h_mm} mm)"
        elif rain_24h is not None:
            verdict = PhysicalCorroborationVerdict.NEUTRAL
            observed_val = rain_24h
            unit = "mm/24h"
            variable = "rainfall_24h"
            explanation = f"Rainfall of {rain_24h:.1f} mm/24h is within normal moderate range"
        else:
            explanation = "No rainfall metrics available in observation"

    # FLOOD & WATERLOGGING (P3: NEVER CONTRADICTS)
    elif cat == "FLOOD_WATERLOGGING":
        rain_24h = observation.rainfall_24h_mm
        water_level = observation.water_level_m
        if rain_24h is not None and rain_24h >= cfg.heavy_rain_24h_mm:
            verdict = PhysicalCorroborationVerdict.SUPPORTS
            observed_val = rain_24h
            unit = "mm/24h"
            variable = "rainfall_24h"
            explanation = (
                f"Heavy rainfall ({rain_24h:.1f} mm) physically supports regional flooding"
            )
        elif water_level is not None and water_level > 0:
            verdict = PhysicalCorroborationVerdict.SUPPORTS
            observed_val = water_level
            unit = "m"
            variable = "water_level"
            explanation = f"River telemetry water level {water_level:.2f} m supports flooding"
        else:
            verdict = PhysicalCorroborationVerdict.NEUTRAL
            observed_val = rain_24h
            unit = "mm/24h"
            variable = "rainfall_24h"
            explanation = (
                "Rainfall below heavy threshold; under P3, low rain does NOT contradict flood"
            )

    # URBAN FLOOD (P3: NEVER CONTRADICTS)
    elif cat == "URBAN_FLOOD":
        rain_1h = observation.rainfall_1h_mm
        rain_3h = observation.rainfall_3h_mm
        if rain_1h is not None and rain_1h >= cfg.urban_flood_rain_1h_mm:
            verdict = PhysicalCorroborationVerdict.SUPPORTS
            observed_val = rain_1h
            unit = "mm/1h"
            variable = "rainfall_1h"
            explanation = (
                f"Intense short-duration burst ({rain_1h:.1f} mm/1h) overwhelms urban storm drains"
            )
        elif rain_3h is not None and rain_3h >= cfg.urban_flood_rain_3h_mm:
            verdict = PhysicalCorroborationVerdict.SUPPORTS
            observed_val = rain_3h
            unit = "mm/3h"
            variable = "rainfall_3h"
            explanation = f"Cumulative 3h rainfall ({rain_3h:.1f} mm) supports urban waterlogging"
        else:
            verdict = PhysicalCorroborationVerdict.NEUTRAL
            observed_val = rain_1h
            unit = "mm/1h"
            variable = "rainfall_1h"
            explanation = (
                "Rainfall below urban flood burst threshold; under P3, low rain does NOT contradict"
            )

    # CYCLONE & STORM
    elif cat == "CYCLONE_STORM":
        wind = observation.wind_speed_kmh
        gust = observation.wind_gusts_kmh
        pressure = observation.pressure_hpa
        if wind is not None and wind >= cfg.gale_wind_speed_kmh:
            verdict = PhysicalCorroborationVerdict.SUPPORTS
            observed_val = wind
            unit = "km/h"
            variable = "wind_speed"
            explanation = (
                f"Gale force sustained winds of {wind:.1f} km/h (>= {cfg.gale_wind_speed_kmh} km/h)"
            )
        elif gust is not None and gust >= cfg.cyclone_wind_gust_kmh:
            verdict = PhysicalCorroborationVerdict.SUPPORTS
            observed_val = gust
            unit = "km/h"
            variable = "wind_gusts"
            explanation = (
                f"Cyclonic wind gusts of {gust:.1f} km/h (>= {cfg.cyclone_wind_gust_kmh} km/h)"
            )
        elif pressure is not None and pressure <= cfg.cyclone_min_pressure_hpa:
            verdict = PhysicalCorroborationVerdict.SUPPORTS
            observed_val = pressure
            unit = "hPa"
            variable = "pressure"
            explanation = (
                f"Low barometric core pressure {pressure:.1f} hPa indicates cyclonic depression"
            )
        elif (
            gust is not None
            and gust <= cfg.contradict_wind_gust_kmh
            and (wind is None or wind <= 15.0)
        ):
            verdict = PhysicalCorroborationVerdict.CONTRADICTS
            observed_val = gust
            unit = "km/h"
            variable = "wind_gusts"
            explanation = f"Observed wind gusts of {gust:.1f} km/h are calm/light breeze"
        else:
            verdict = PhysicalCorroborationVerdict.NEUTRAL
            observed_val = wind
            unit = "km/h"
            variable = "wind_speed"
            explanation = "Wind metrics are within moderate non-cyclonic range"

    # STRONG WIND & GALE
    elif cat == "STRONG_WIND":
        wind = observation.wind_speed_kmh
        gust = observation.wind_gusts_kmh
        if wind is not None and wind >= cfg.strong_wind_speed_kmh:
            verdict = PhysicalCorroborationVerdict.SUPPORTS
            observed_val = wind
            unit = "km/h"
            variable = "wind_speed"
            explanation = (
                f"Sustained wind speed {wind:.1f} km/h reaches strong wind/squall threshold"
            )
        elif gust is not None and gust >= 60.0:
            verdict = PhysicalCorroborationVerdict.SUPPORTS
            observed_val = gust
            unit = "km/h"
            variable = "wind_gusts"
            explanation = f"Peak wind gusts {gust:.1f} km/h indicate squall conditions"
        elif (
            gust is not None
            and gust <= cfg.contradict_wind_gust_kmh
            and (wind is None or wind <= 10.0)
        ):
            verdict = PhysicalCorroborationVerdict.CONTRADICTS
            observed_val = gust
            unit = "km/h"
            variable = "wind_gusts"
            explanation = (
                f"Station recorded light breeze ({gust:.1f} km/h gusts), disproving strong wind"
            )
        else:
            verdict = PhysicalCorroborationVerdict.NEUTRAL
            observed_val = wind
            unit = "km/h"
            variable = "wind_speed"
            explanation = "Winds within normal range"

    # DUST STORM
    elif cat == "DUST_STORM":
        vis = observation.visibility_m
        gust = observation.wind_gusts_kmh
        if (
            vis is not None
            and vis < cfg.dust_storm_visibility_m
            and (gust is None or gust >= cfg.dust_storm_gust_kmh)
        ):
            verdict = PhysicalCorroborationVerdict.SUPPORTS
            observed_val = vis
            unit = "m"
            variable = "visibility"
            explanation = f"Blinding dust visibility drop ({vis:.0f} m < {cfg.dust_storm_visibility_m} m) with active gusts"
        elif vis is not None and vis > 6000.0 and (gust is None or gust <= 15.0):
            verdict = PhysicalCorroborationVerdict.CONTRADICTS
            observed_val = vis
            unit = "m"
            variable = "visibility"
            explanation = f"Clear visibility ({vis:.0f} m) and calm winds contradict dust storm"
        else:
            verdict = PhysicalCorroborationVerdict.NEUTRAL
            observed_val = vis
            unit = "m"
            variable = "visibility"
            explanation = "Atmospheric visibility above dust storm threshold"

    # FOG
    elif cat == "FOG":
        vis = observation.visibility_m
        hum = observation.relative_humidity_pct
        if vis is not None and vis <= cfg.fog_moderate_visibility_m:
            verdict = PhysicalCorroborationVerdict.SUPPORTS
            observed_val = vis
            unit = "m"
            variable = "visibility"
            level = "Dense" if vis <= cfg.fog_dense_visibility_m else "Moderate"
            explanation = f"{level} fog observed with visibility of {vis:.0f} m (<= {cfg.fog_moderate_visibility_m} m)"
        elif (
            vis is not None
            and vis > cfg.contradict_fog_visibility_m
            and (hum is None or hum < 70.0)
        ):
            verdict = PhysicalCorroborationVerdict.CONTRADICTS
            observed_val = vis
            unit = "m"
            variable = "visibility"
            explanation = f"Clear visibility ({vis:.0f} m) and low humidity ({hum}%) disprove fog"
        else:
            verdict = PhysicalCorroborationVerdict.NEUTRAL
            observed_val = vis
            unit = "m"
            variable = "visibility"
            explanation = "Visibility above fog threshold"

    # HEATWAVE
    elif cat == "HEATWAVE":
        temp = observation.max_temperature_c or observation.temperature_c
        if temp is not None and temp >= cfg.heatwave_temp_c:
            verdict = PhysicalCorroborationVerdict.SUPPORTS
            observed_val = temp
            unit = "°C"
            variable = "temperature"
            explanation = f"Recorded maximum temperature {temp:.1f}°C meets IMD heatwave criteria"
        elif temp is not None and temp <= cfg.contradict_heatwave_temp_c:
            verdict = PhysicalCorroborationVerdict.CONTRADICTS
            observed_val = temp
            unit = "°C"
            variable = "temperature"
            explanation = f"Temperature of {temp:.1f}°C is well below heatwave levels"
        else:
            verdict = PhysicalCorroborationVerdict.NEUTRAL
            observed_val = temp
            unit = "°C"
            variable = "temperature"
            explanation = "Temperature within seasonal moderate range"

    # THUNDERSTORM / LIGHTNING
    elif cat == "THUNDERSTORM_LIGHTNING":
        wmo = observation.weather_code
        rain_1h = observation.rainfall_1h_mm
        if (wmo is not None and wmo in (91, 92, 95, 96, 99)) or (
            rain_1h is not None and rain_1h >= 15.0
        ):
            verdict = PhysicalCorroborationVerdict.SUPPORTS
            observed_val = float(wmo) if wmo else rain_1h
            unit = "wmo_code" if wmo else "mm/1h"
            variable = "weather_code" if wmo else "rainfall_1h"
            explanation = "Thunderstorm weather code or severe convective shower observed"
        else:
            verdict = PhysicalCorroborationVerdict.NEUTRAL
            observed_val = float(wmo) if wmo is not None else None
            unit = "wmo_code"
            variable = "weather_code"
            explanation = (
                "Localized lightning strike cannot be disproven by grid model; verdict is NEUTRAL"
            )

    # HAILSTORM
    elif cat == "HAILSTORM":
        wmo = observation.weather_code
        if wmo is not None and wmo in (89, 90, 96, 99):
            verdict = PhysicalCorroborationVerdict.SUPPORTS
            observed_val = float(wmo)
            unit = "wmo_code"
            variable = "weather_code"
            explanation = f"WMO hail code {wmo} detected"
        else:
            verdict = PhysicalCorroborationVerdict.NEUTRAL
            explanation = "Hail footprint is micro-scale (<2 km); non-detection does not contradict"

    # LANDSLIDE
    elif cat == "LANDSLIDE":
        rain_72h = observation.rainfall_72h_mm or observation.rainfall_24h_mm
        if rain_72h is not None and rain_72h >= cfg.landslide_rain_72h_mm:
            verdict = PhysicalCorroborationVerdict.SUPPORTS
            observed_val = rain_72h
            unit = "mm/72h"
            variable = "rainfall_72h"
            explanation = f"High cumulative rainfall ({rain_72h:.1f} mm) provides physical slope failure trigger"
        else:
            verdict = PhysicalCorroborationVerdict.NEUTRAL
            explanation = "Landslides may be dry/seismic; low rainfall does not contradict"

    # DROUGHT / OTHER
    else:
        verdict = PhysicalCorroborationVerdict.NEUTRAL
        explanation = f"Hazard category '{cat}' does not have hourly physical station indicators (NOT_APPLICABLE)"
        return PhysicalCorroborationResult(
            verdict=verdict,
            observed_value=None,
            unit="",
            variable="",
            source=observation.source_name,
            source_type=observation.source_type,
            station_or_grid_id=observation.station_or_grid_id,
            distance_km=round(distance_km, 2),
            time_gap_hours=round(time_gap_hours, 2),
            provider_status=ProviderStatus.NOT_APPLICABLE,
            explanation=explanation,
            is_simulated=observation.is_simulated,
        )

    # 4. Enforce P4: Suppress CONTRADICTS from MODEL data unless explicitly configured
    if verdict == PhysicalCorroborationVerdict.CONTRADICTS:
        if observation.source_type == PhysicalSourceType.MODEL and not cfg.allow_model_contradicts:
            verdict = PhysicalCorroborationVerdict.NEUTRAL
            explanation = (
                f"{explanation} -> Note: Under P4, numerical MODEL contradictions are suppressed "
                f"(numerical models miss convective micro-bursts); verdict converted to NEUTRAL"
            )

    # 5. Compute Weight and Contribution
    source_weight = (
        cfg.weight_station
        if observation.source_type == PhysicalSourceType.STATION
        else cfg.weight_model
    )
    dist_decay = max(0.20, 1.0 - (distance_km / max_distance))
    time_decay = max(0.30, 1.0 - (time_gap_hours / max_time_window))
    combined_weight = round(source_weight * dist_decay * time_decay, 4)

    if verdict == PhysicalCorroborationVerdict.SUPPORTS:
        raw_contrib = combined_weight * cfg.base_support_boost
        contribution = round(min(cfg.total_physical_cap, raw_contrib), 4)
    elif verdict == PhysicalCorroborationVerdict.CONTRADICTS:
        raw_contrib = combined_weight * cfg.base_contradict_penalty
        contribution = -round(min(cfg.total_physical_cap, raw_contrib), 4)
    else:
        contribution = 0.0

    return PhysicalCorroborationResult(
        verdict=verdict,
        observed_value=round(observed_val, 2) if observed_val is not None else None,
        unit=unit,
        variable=variable,
        source=observation.source_name,
        source_type=observation.source_type,
        station_or_grid_id=observation.station_or_grid_id,
        distance_km=round(distance_km, 2),
        time_gap_hours=round(time_gap_hours, 2),
        weight=combined_weight,
        contribution=contribution,
        provider_status=ProviderStatus.OK,
        explanation=explanation,
        is_simulated=observation.is_simulated,
    )
