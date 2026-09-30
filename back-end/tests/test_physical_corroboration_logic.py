"""Unit tests for pure physical corroboration evaluation logic (No DB, No Network)."""

from datetime import datetime, timezone, timedelta
import zoneinfo
import pytest

from app.intelligence.physical_corroboration import (
    evaluate,
    compute_grid_hour_cache_key,
    PhysicalObservation,
    PhysicalSourceType,
    PhysicalCorroborationVerdict,
    PhysicalCorroborationConfig,
    ProviderStatus,
)

IST = zoneinfo.ZoneInfo("Asia/Kolkata")
REF_TIME = datetime(2026, 10, 1, 12, 0, 0, tzinfo=timezone.utc)
DELHI_COORDS = (28.6139, 77.2090)


def create_obs(
    source_type: PhysicalSourceType = PhysicalSourceType.STATION,
    coords: tuple = DELHI_COORDS,
    obs_time: datetime = REF_TIME,
    **metrics,
) -> PhysicalObservation:
    return PhysicalObservation(
        source_name="TestStation" if source_type == PhysicalSourceType.STATION else "TestModel",
        source_type=source_type,
        station_or_grid_id="STN-001",
        latitude=coords[0],
        longitude=coords[1],
        observed_at=obs_time,
        **metrics,
    )


class TestPhysicalCorroborationLogic:
    """Test suite for pure mathematical evaluation rules."""

    def test_grid_hour_cache_key_generation(self):
        """Grid key accurately discretizes to 0.25 deg grid and hourly timestamp in UTC."""
        dt = datetime(2026, 10, 1, 14, 35, 22, tzinfo=IST)  # 14:35 IST = 09:05 UTC
        key = compute_grid_hour_cache_key(28.6139, 77.2090, dt, grid_size=0.25)
        # 28.6139 / 0.25 = 114.4556 -> 114 * 0.25 = 28.50
        # 77.2090 / 0.25 = 308.836 -> 309 * 0.25 = 77.25
        assert key == "cache:weather:physical:28.50:77.25:2026-10-01T09"

    # --- 1. HEAVY RAINFALL ---
    def test_heavy_rainfall_support_and_contradict(self):
        # Support case (>= 64.5 mm)
        obs_sup = create_obs(rainfall_24h_mm=75.0)
        res_sup = evaluate("HEAVY_RAINFALL", obs_sup, REF_TIME, DELHI_COORDS)
        assert res_sup.verdict == PhysicalCorroborationVerdict.SUPPORTS
        assert res_sup.observed_value == 75.0
        assert res_sup.unit == "mm/24h"
        assert res_sup.contribution > 0.0

        # Contradict case from STATION (<= 0.1 mm)
        obs_con = create_obs(source_type=PhysicalSourceType.STATION, rainfall_24h_mm=0.0)
        res_con = evaluate("HEAVY_RAINFALL", obs_con, REF_TIME, DELHI_COORDS)
        assert res_con.verdict == PhysicalCorroborationVerdict.CONTRADICTS
        assert res_con.contribution < 0.0

        # Threshold boundary: exactly 64.5 mm
        obs_bound = create_obs(rainfall_24h_mm=64.5)
        res_bound = evaluate("HEAVY_RAINFALL", obs_bound, REF_TIME, DELHI_COORDS)
        assert res_bound.verdict == PhysicalCorroborationVerdict.SUPPORTS

    # --- 2. FLOOD & URBAN FLOOD (P3: NEVER CONTRADICTS) ---
    def test_flood_waterlogging_never_contradicts(self):
        # Support case: high rain
        obs_flood = create_obs(rainfall_24h_mm=85.0)
        res_flood = evaluate("FLOOD_WATERLOGGING", obs_flood, REF_TIME, DELHI_COORDS)
        assert res_flood.verdict == PhysicalCorroborationVerdict.SUPPORTS

        # P3 Rule: Zero rain does NOT contradict flood
        obs_dry = create_obs(source_type=PhysicalSourceType.STATION, rainfall_24h_mm=0.0)
        res_dry = evaluate("FLOOD_WATERLOGGING", obs_dry, REF_TIME, DELHI_COORDS)
        assert res_dry.verdict == PhysicalCorroborationVerdict.NEUTRAL
        assert "does NOT contradict" in res_dry.explanation
        assert res_dry.contribution == 0.0

    def test_urban_flood_never_contradicts(self):
        # Support case: intense 1h burst >= 20 mm
        obs_urban = create_obs(rainfall_1h_mm=24.5)
        res_urban = evaluate("URBAN_FLOOD", obs_urban, REF_TIME, DELHI_COORDS)
        assert res_urban.verdict == PhysicalCorroborationVerdict.SUPPORTS

        # P3: Zero rain does NOT contradict urban flood
        obs_urban_dry = create_obs(source_type=PhysicalSourceType.STATION, rainfall_1h_mm=0.0)
        res_urban_dry = evaluate("URBAN_FLOOD", obs_urban_dry, REF_TIME, DELHI_COORDS)
        assert res_urban_dry.verdict == PhysicalCorroborationVerdict.NEUTRAL

    # --- 3. CYCLONE & STORM ---
    def test_cyclone_storm_support_and_contradict(self):
        # Support by gale winds (>= 62 km/h)
        obs_cyc = create_obs(wind_speed_kmh=68.0, wind_gusts_kmh=90.0, pressure_hpa=985.0)
        res_cyc = evaluate("CYCLONE_STORM", obs_cyc, REF_TIME, DELHI_COORDS)
        assert res_cyc.verdict == PhysicalCorroborationVerdict.SUPPORTS

        # Contradict by station: calm breeze
        obs_calm = create_obs(
            source_type=PhysicalSourceType.STATION, wind_speed_kmh=8.0, wind_gusts_kmh=12.0
        )
        res_calm = evaluate("CYCLONE_STORM", obs_calm, REF_TIME, DELHI_COORDS)
        assert res_calm.verdict == PhysicalCorroborationVerdict.CONTRADICTS

    # --- 4. STRONG WIND ---
    def test_strong_wind_support_and_contradict(self):
        obs_wind = create_obs(wind_speed_kmh=52.0)
        res_wind = evaluate("STRONG_WIND", obs_wind, REF_TIME, DELHI_COORDS)
        assert res_wind.verdict == PhysicalCorroborationVerdict.SUPPORTS

        obs_nowind = create_obs(
            source_type=PhysicalSourceType.STATION, wind_speed_kmh=5.0, wind_gusts_kmh=10.0
        )
        res_nowind = evaluate("STRONG_WIND", obs_nowind, REF_TIME, DELHI_COORDS)
        assert res_nowind.verdict == PhysicalCorroborationVerdict.CONTRADICTS

    # --- 5. DUST STORM ---
    def test_dust_storm_support_and_contradict(self):
        # Low visibility (< 1000m) with high gusts (>= 40 km/h)
        obs_dust = create_obs(visibility_m=600.0, wind_gusts_kmh=45.0)
        res_dust = evaluate("DUST_STORM", obs_dust, REF_TIME, DELHI_COORDS)
        assert res_dust.verdict == PhysicalCorroborationVerdict.SUPPORTS

        # High visibility (> 6000m) and calm winds
        obs_nodust = create_obs(
            source_type=PhysicalSourceType.STATION, visibility_m=9000.0, wind_gusts_kmh=10.0
        )
        res_nodust = evaluate("DUST_STORM", obs_nodust, REF_TIME, DELHI_COORDS)
        assert res_nodust.verdict == PhysicalCorroborationVerdict.CONTRADICTS

    # --- 6. FOG ---
    def test_fog_support_and_contradict(self):
        # Dense fog (<= 200m)
        obs_fog = create_obs(visibility_m=150.0, relative_humidity_pct=95.0)
        res_fog = evaluate("FOG", obs_fog, REF_TIME, DELHI_COORDS)
        assert res_fog.verdict == PhysicalCorroborationVerdict.SUPPORTS

        # Clear air (> 3000m) and low humidity (< 70%)
        obs_nofog = create_obs(
            source_type=PhysicalSourceType.STATION, visibility_m=5000.0, relative_humidity_pct=50.0
        )
        res_nofog = evaluate("FOG", obs_nofog, REF_TIME, DELHI_COORDS)
        assert res_nofog.verdict == PhysicalCorroborationVerdict.CONTRADICTS

    # --- 7. HEATWAVE ---
    def test_heatwave_support_and_contradict(self):
        obs_heat = create_obs(max_temperature_c=42.5)
        res_heat = evaluate("HEATWAVE", obs_heat, REF_TIME, DELHI_COORDS)
        assert res_heat.verdict == PhysicalCorroborationVerdict.SUPPORTS

        obs_cool = create_obs(source_type=PhysicalSourceType.STATION, max_temperature_c=28.0)
        res_cool = evaluate("HEATWAVE", obs_cool, REF_TIME, DELHI_COORDS)
        assert res_cool.verdict == PhysicalCorroborationVerdict.CONTRADICTS

    # --- 8. THUNDERSTORM / HAILSTORM / LANDSLIDE ---
    def test_thunderstorm_and_hailstorm_support(self):
        obs_thunder = create_obs(weather_code=95)
        res_thunder = evaluate("THUNDERSTORM_LIGHTNING", obs_thunder, REF_TIME, DELHI_COORDS)
        assert res_thunder.verdict == PhysicalCorroborationVerdict.SUPPORTS

        obs_hail = create_obs(weather_code=89)
        res_hail = evaluate("HAILSTORM", obs_hail, REF_TIME, DELHI_COORDS)
        assert res_hail.verdict == PhysicalCorroborationVerdict.SUPPORTS

    def test_landslide_support_and_neutral(self):
        obs_landslide = create_obs(rainfall_72h_mm=120.0)
        res_landslide = evaluate("LANDSLIDE", obs_landslide, REF_TIME, DELHI_COORDS)
        assert res_landslide.verdict == PhysicalCorroborationVerdict.SUPPORTS

        # Landslide without heavy rain returns NEUTRAL, never contradicts
        obs_dry_land = create_obs(rainfall_72h_mm=10.0)
        res_dry_land = evaluate("LANDSLIDE", obs_dry_land, REF_TIME, DELHI_COORDS)
        assert res_dry_land.verdict == PhysicalCorroborationVerdict.NEUTRAL

    # --- 9. MISSING, STALE, AND DISTANT OBSERVATIONS ---
    def test_missing_data_returns_neutral(self):
        obs_empty = create_obs()  # No metrics populated
        res = evaluate("HEAVY_RAINFALL", obs_empty, REF_TIME, DELHI_COORDS)
        assert res.verdict == PhysicalCorroborationVerdict.NEUTRAL
        assert "No rainfall metrics available" in res.explanation

    def test_too_far_observation_returns_neutral_too_far(self):
        far_coords = (DELHI_COORDS[0] + 0.50, DELHI_COORDS[1] + 0.50)  # ~70 km away
        obs_far = create_obs(coords=far_coords, rainfall_24h_mm=80.0)
        res = evaluate("HEAVY_RAINFALL", obs_far, REF_TIME, DELHI_COORDS)
        assert res.verdict == PhysicalCorroborationVerdict.NEUTRAL
        assert res.provider_status == ProviderStatus.TOO_FAR

    def test_stale_observation_returns_neutral_stale(self):
        stale_time = REF_TIME - timedelta(hours=30)
        obs_stale = create_obs(obs_time=stale_time, rainfall_24h_mm=80.0)
        res = evaluate("HEAVY_RAINFALL", obs_stale, REF_TIME, DELHI_COORDS)
        assert res.verdict == PhysicalCorroborationVerdict.NEUTRAL
        assert res.provider_status == ProviderStatus.STALE_DATA

    # --- 10. P4: MODEL CONTRADICT DISABLED BY DEFAULT ---
    def test_model_contradict_disabled_by_default(self):
        cfg = PhysicalCorroborationConfig(allow_model_contradicts=False)
        # Numerical model says 0 rain during reported heavy rainfall
        obs_model = create_obs(source_type=PhysicalSourceType.MODEL, rainfall_24h_mm=0.0)
        res = evaluate("HEAVY_RAINFALL", obs_model, REF_TIME, DELHI_COORDS, config=cfg)
        # Must be suppressed to NEUTRAL under P4
        assert res.verdict == PhysicalCorroborationVerdict.NEUTRAL
        assert "Under P4, numerical MODEL contradictions are suppressed" in res.explanation

        # When explicitly enabled, model CAN contradict
        cfg_enabled = PhysicalCorroborationConfig(allow_model_contradicts=True)
        res_enabled = evaluate(
            "HEAVY_RAINFALL", obs_model, REF_TIME, DELHI_COORDS, config=cfg_enabled
        )
        assert res_enabled.verdict == PhysicalCorroborationVerdict.CONTRADICTS

    # --- 11. STATION VS MODEL WEIGHTING ---
    def test_station_vs_model_weighting(self):
        obs_stn = create_obs(source_type=PhysicalSourceType.STATION, rainfall_24h_mm=80.0)
        res_stn = evaluate("HEAVY_RAINFALL", obs_stn, REF_TIME, DELHI_COORDS)

        obs_mod = create_obs(source_type=PhysicalSourceType.MODEL, rainfall_24h_mm=80.0)
        res_mod = evaluate("HEAVY_RAINFALL", obs_mod, REF_TIME, DELHI_COORDS)

        # Station has higher weight than model
        assert res_stn.weight > res_mod.weight
        assert res_stn.contribution >= res_mod.contribution

    # --- 12. CONTRIBUTION CAP ---
    def test_contribution_cap_enforced(self):
        cfg = PhysicalCorroborationConfig(total_physical_cap=0.05, base_support_boost=0.50)
        obs = create_obs(rainfall_24h_mm=250.0)  # Extreme rain
        res = evaluate("HEAVY_RAINFALL", obs, REF_TIME, DELHI_COORDS, config=cfg)
        assert res.contribution <= 0.05

    # --- 13. TIMEZONE HANDLING (IST VS UTC) ---
    def test_timezone_handling_ist_vs_utc(self):
        # Incident in IST (17:30 IST)
        inc_ist = datetime(2026, 10, 1, 17, 30, tzinfo=IST)
        # Observation in UTC (12:00 UTC == 17:30 IST)
        obs_utc = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)
        obs = create_obs(obs_time=obs_utc, rainfall_24h_mm=75.0)

        res = evaluate("HEAVY_RAINFALL", obs, inc_ist, DELHI_COORDS)
        # Time gap should be exactly 0.0 hours
        assert res.time_gap_hours == 0.0
        assert res.verdict == PhysicalCorroborationVerdict.SUPPORTS
