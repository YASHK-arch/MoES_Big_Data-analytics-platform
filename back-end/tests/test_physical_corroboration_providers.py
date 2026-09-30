"""Mock-only tests for physical weather providers, cache, and single-flight deduplication."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Optional, Tuple
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from app.intelligence.physical_corroboration.models import (
    PhysicalObservation,
    PhysicalSourceType,
    ProviderStatus,
)
from app.intelligence.physical_corroboration.providers.base import BaseWeatherProvider
from app.intelligence.physical_corroboration.providers.cache import SingleFlightGridHourCache
from app.intelligence.physical_corroboration.providers.imd_slot import IMDStationProviderSlot
from app.intelligence.physical_corroboration.providers.open_meteo import OpenMeteoProvider


class DummyFlakyProvider(BaseWeatherProvider):
    """Dummy provider for testing retry and timeout logic."""

    def __init__(self, outcomes: list, **kwargs):
        super().__init__(name="DUMMY", source_type=PhysicalSourceType.MODEL, **kwargs)
        self.outcomes = list(outcomes)
        self.call_count = 0

    async def _execute_fetch(
        self, lat: float, lon: float, target_time: datetime, category: str
    ) -> Tuple[Optional[PhysicalObservation], ProviderStatus, Optional[str]]:
        self.call_count += 1
        if not self.outcomes:
            return None, ProviderStatus.NO_DATA, "No outcomes left"
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


@pytest.mark.asyncio
class TestPhysicalWeatherProvidersAndCache:
    """Test suite for providers, error semantics, cache hits, and single-flight deduplication."""

    async def test_provider_timeout_fallback(self) -> None:
        """Test provider timeout fallback to TIMEOUT and NEUTRAL."""

        async def slow_fetch(*args, **kwargs):
            await asyncio.sleep(0.5)
            return None, ProviderStatus.OK, None

        provider = DummyFlakyProvider(
            outcomes=[],
            timeout_seconds=0.05,
            max_retries=1,
            initial_backoff_seconds=0.01,
        )
        provider._execute_fetch = slow_fetch

        target_time = datetime(2026, 7, 15, 12, 0, tzinfo=timezone.utc)
        obs, status, err = await provider.fetch_observation(
            28.61, 77.20, target_time, "HEAVY_RAINFALL"
        )

        assert obs is None
        assert status == ProviderStatus.TIMEOUT
        assert "timed out" in (err or "").lower()

    async def test_provider_exception_handling(self) -> None:
        """Test unexpected exception handling yields PROVIDER_ERROR and does not raise."""
        provider = DummyFlakyProvider(
            outcomes=[RuntimeError("Socket reset by peer"), RuntimeError("Socket reset by peer")],
            timeout_seconds=1.0,
            max_retries=1,
            initial_backoff_seconds=0.01,
        )
        target_time = datetime(2026, 7, 15, 12, 0, tzinfo=timezone.utc)
        obs, status, err = await provider.fetch_observation(
            28.61, 77.20, target_time, "HEAVY_RAINFALL"
        )

        assert obs is None
        assert status == ProviderStatus.PROVIDER_ERROR
        assert "Socket reset by peer" in (err or "")
        assert provider.call_count == 2

    async def test_open_meteo_429_rate_limited(self) -> None:
        """Test 429 response from Open-Meteo returns PROVIDER_RATE_LIMITED status."""
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 429
        mock_response.headers = {"Retry-After": "60"}
        mock_client.get = AsyncMock(return_value=mock_response)

        provider = OpenMeteoProvider(http_client=mock_client)
        target_time = datetime(2026, 7, 15, 12, 0, tzinfo=timezone.utc)
        obs, status, err = await provider.fetch_observation(
            28.61, 77.20, target_time, "HEAVY_RAINFALL"
        )

        assert obs is None
        assert status == ProviderStatus.PROVIDER_RATE_LIMITED
        assert "Retry-After: 60" in (err or "")

    async def test_open_meteo_malformed_json(self) -> None:
        """Test malformed JSON response yields MALFORMED_DATA."""
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 200
        mock_response.json = MagicMock(side_effect=ValueError("Invalid JSON token"))
        mock_client.get = AsyncMock(return_value=mock_response)

        provider = OpenMeteoProvider(http_client=mock_client)
        target_time = datetime(2026, 7, 15, 12, 0, tzinfo=timezone.utc)
        obs, status, err = await provider.fetch_observation(
            28.61, 77.20, target_time, "HEAVY_RAINFALL"
        )

        assert obs is None
        assert status == ProviderStatus.MALFORMED_DATA
        assert "Failed to parse JSON" in (err or "")

    async def test_open_meteo_empty_response(self) -> None:
        """Test empty payload missing 'hourly' yields NO_DATA."""
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 200
        mock_response.json = MagicMock(return_value={"latitude": 28.6})
        mock_client.get = AsyncMock(return_value=mock_response)

        provider = OpenMeteoProvider(http_client=mock_client)
        target_time = datetime(2026, 7, 15, 12, 0, tzinfo=timezone.utc)
        obs, status, err = await provider.fetch_observation(
            28.61, 77.20, target_time, "HEAVY_RAINFALL"
        )

        assert obs is None
        assert status == ProviderStatus.NO_DATA
        assert "missing 'hourly'" in (err or "")

    async def test_open_meteo_successful_parse(self) -> None:
        """Test valid Open-Meteo response parsed into PhysicalObservation."""
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 200
        mock_response.json = MagicMock(
            return_value={
                "latitude": 28.6,
                "longitude": 77.2,
                "hourly": {
                    "time": ["2026-07-15T11:00", "2026-07-15T12:00", "2026-07-15T13:00"],
                    "precipitation": [0.0, 75.4, 12.0],
                    "temperature_2m": [32.0, 31.5, 30.0],
                    "wind_speed_10m": [15.0, 48.0, 22.0],
                    "wind_gusts_10m": [25.0, 72.0, 35.0],
                    "visibility": [8000, 1500, 4000],
                    "surface_pressure": [1002.0, 998.5, 1000.0],
                    "relative_humidity_2m": [70, 92, 85],
                },
            }
        )
        mock_client.get = AsyncMock(return_value=mock_response)

        provider = OpenMeteoProvider(http_client=mock_client)
        target_time = datetime(2026, 7, 15, 12, 10, tzinfo=timezone.utc)
        obs, status, err = await provider.fetch_observation(
            28.61, 77.20, target_time, "HEAVY_RAINFALL"
        )

        assert status == ProviderStatus.OK
        assert obs is not None
        assert obs.rainfall_1h_mm == 75.4
        assert obs.temperature_c == 31.5
        assert obs.wind_speed_kmh == 48.0
        assert obs.wind_gusts_kmh == 72.0
        assert obs.source_name == "OPEN_METEO"
        assert obs.source_type == PhysicalSourceType.MODEL

    async def test_cache_hit_and_expiration(self) -> None:
        """Test cache hit avoids redundant computation and serves cached object."""
        cache = SingleFlightGridHourCache(ttl_seconds=10)
        target_time = datetime(2026, 7, 15, 12, 0, tzinfo=timezone.utc)
        lat, lon = 28.61, 77.20

        sample_obs = PhysicalObservation(
            source_name="OPEN_METEO",
            source_type=PhysicalSourceType.MODEL,
            station_or_grid_id="OM_GRID_28.61_77.20",
            latitude=lat,
            longitude=lon,
            observed_at=target_time,
            rainfall_1h_mm=50.0,
        )

        call_count = 0

        async def mock_fetch():
            nonlocal call_count
            call_count += 1
            return sample_obs, ProviderStatus.OK, None

        # Call 1: Miss
        obs1, status1, err1, is_hit1 = await cache.get_or_fetch(lat, lon, target_time, mock_fetch)
        assert is_hit1 is False
        assert call_count == 1
        assert obs1.rainfall_1h_mm == 50.0

        # Call 2: Hit
        obs2, status2, err2, is_hit2 = await cache.get_or_fetch(lat, lon, target_time, mock_fetch)
        assert is_hit2 is True
        assert call_count == 1
        assert cache.cache_hits == 1
        assert obs2.rainfall_1h_mm == 50.0

    async def test_single_flight_concurrent_deduplication(self) -> None:
        """Test 5 concurrent requests for same grid-hour execute provider exactly once."""
        cache = SingleFlightGridHourCache(ttl_seconds=10)
        target_time = datetime(2026, 7, 15, 12, 0, tzinfo=timezone.utc)
        lat, lon = 19.07, 72.87

        call_count = 0

        async def slow_fetch():
            nonlocal call_count
            call_count += 1
            await asyncio.sleep(0.05)  # Simulate network latency
            return (
                PhysicalObservation(
                    source_name="OPEN_METEO",
                    source_type=PhysicalSourceType.MODEL,
                    station_or_grid_id="OM_GRID_19.07_72.87",
                    latitude=lat,
                    longitude=lon,
                    observed_at=target_time,
                    rainfall_1h_mm=85.0,
                ),
                ProviderStatus.OK,
                None,
            )

        # Launch 5 concurrent calls
        tasks = [cache.get_or_fetch(lat, lon, target_time, slow_fetch) for _ in range(5)]
        results = await asyncio.gather(*tasks)

        # Single flight ensures provider called only once
        assert call_count == 1
        assert len(results) == 5
        for obs, status, err, _ in results:
            assert status == ProviderStatus.OK
            assert obs is not None
            assert obs.rainfall_1h_mm == 85.0

    async def test_imd_station_slot_is_disabled(self) -> None:
        """Test IMD station provider slot is disabled by default per Rule P9."""
        imd_slot = IMDStationProviderSlot(is_enabled=False)
        target_time = datetime(2026, 7, 15, 12, 0, tzinfo=timezone.utc)
        obs, status, err = await imd_slot.fetch_observation(
            28.61, 77.20, target_time, "HEAVY_RAINFALL"
        )

        assert obs is None
        assert status == ProviderStatus.DISABLED
        assert "disabled" in (err or "").lower()
        assert imd_slot.source_type == PhysicalSourceType.STATION
