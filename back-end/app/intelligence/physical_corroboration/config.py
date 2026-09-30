"""Configuration thresholds and parameters for physical weather corroboration."""

from pydantic import BaseModel, Field


class PhysicalCorroborationConfig(BaseModel):
    """Configuration container for physical meteorological corroboration thresholds."""

    # Feature flags
    enabled: bool = Field(
        default=False, description="Master feature flag for physical corroboration"
    )
    allow_model_contradicts: bool = Field(
        default=False, description="P4: Disallow CONTRADICTS from MODEL data by default"
    )

    # Caps and weights
    total_physical_cap: float = Field(
        default=0.10, description="P5: Unified cap for all physical evidence contributions"
    )
    weight_station: float = Field(
        default=1.00, description="Reliability multiplier for ground station sensors"
    )
    weight_model: float = Field(
        default=0.60, description="Reliability multiplier for numerical models (e.g. Open-Meteo)"
    )
    base_support_boost: float = Field(
        default=0.10, description="Maximum positive contribution before decay"
    )
    base_contradict_penalty: float = Field(
        default=0.12, description="Maximum negative contribution before decay"
    )

    # Distance limits (km) [ASSUMPTION - unverified]
    max_distance_station_km: float = Field(
        default=25.0, description="Maximum distance to ground station"
    )
    max_distance_model_km: float = Field(
        default=20.0, description="Maximum distance to numerical model grid center"
    )

    # Time gap limits (hours) [ASSUMPTION - unverified]
    max_time_gap_precipitation_hours: float = Field(
        default=24.0, description="Window for 24h accumulation and runoff"
    )
    max_time_gap_transient_hours: float = Field(
        default=3.0, description="Window for wind, fog, dust storm"
    )
    max_time_gap_heatwave_hours: float = Field(
        default=24.0, description="Window for daily max temperature"
    )

    # Meteorological Thresholds (Heavy Rainfall) - Source: IMD SOP Chapter 3
    heavy_rain_24h_mm: float = Field(
        default=64.5, description="IMD Heavy Rain lower threshold (64.5 mm / 24h)"
    )
    very_heavy_rain_24h_mm: float = Field(
        default=115.6, description="IMD Very Heavy Rain threshold (115.6 mm / 24h)"
    )
    extremely_heavy_rain_24h_mm: float = Field(
        default=204.5, description="IMD Extremely Heavy Rain threshold (204.5 mm / 24h)"
    )
    intense_rain_1h_mm: float = Field(
        default=15.0, description="IMD Nowcast intense hourly rainfall burst"
    )
    urban_flood_rain_1h_mm: float = Field(
        default=20.0, description="IMD Urban cloudburst / intense inundation burst"
    )
    urban_flood_rain_3h_mm: float = Field(
        default=40.0, description="3-hour cumulative urban drainage overload"
    )
    contradict_rain_24h_mm: float = Field(
        default=0.1, description="Absolute zero rain threshold for contradiction"
    )

    # Meteorological Thresholds (Heatwave) - Source: IMD Criteria for Heat Wave
    heatwave_temp_c: float = Field(default=40.0, description="IMD Heatwave baseline for plains")
    heatwave_severe_temp_c: float = Field(
        default=45.0, description="IMD Severe Heatwave absolute threshold"
    )
    contradict_heatwave_temp_c: float = Field(
        default=32.0, description="Non-heatwave threshold for contradiction"
    )

    # Meteorological Thresholds (Visibility & Fog) - Source: IMD Aviation Fog Standards
    fog_dense_visibility_m: float = Field(
        default=200.0, description="IMD Dense Fog threshold (<= 200 m)"
    )
    fog_moderate_visibility_m: float = Field(
        default=500.0, description="IMD Moderate Fog threshold (<= 500 m)"
    )
    contradict_fog_visibility_m: float = Field(
        default=3000.0, description="Clear air threshold for fog contradiction"
    )

    # Meteorological Thresholds (Dust Storm) - Source: WMO-No. 8 / IMD
    dust_storm_visibility_m: float = Field(
        default=1000.0, description="Visibility threshold for dust storm"
    )
    dust_storm_gust_kmh: float = Field(
        default=40.0, description="Wind gust threshold for blowing dust"
    )

    # Meteorological Thresholds (Wind & Gale) - Source: Beaufort Scale / WMO-No. 9 / IMD
    strong_wind_speed_kmh: float = Field(
        default=50.0, description="IMD Squall / High wind threshold"
    )
    gale_wind_speed_kmh: float = Field(
        default=62.0, description="WMO Gale Force threshold (Beaufort 8)"
    )
    cyclone_wind_gust_kmh: float = Field(default=80.0, description="Cyclone gust threshold")
    cyclone_min_pressure_hpa: float = Field(
        default=990.0, description="Tropical cyclonic depression core pressure"
    )
    contradict_wind_gust_kmh: float = Field(
        default=20.0, description="Calm/breeze threshold for wind contradiction"
    )

    # Landslide rainfall trigger [ASSUMPTION - unverified]
    landslide_rain_72h_mm: float = Field(
        default=100.0, description="Cumulative 72h antecedent rainfall for slope saturation"
    )


default_physical_config = PhysicalCorroborationConfig()
