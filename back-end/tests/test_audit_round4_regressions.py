from datetime import datetime, timezone

import pytest
import pytest_asyncio
from alembic.config import Config
from httpx import ASGITransport, AsyncClient

from alembic import command
from app.core.config import settings
from app.core.redis import AsyncRedisClient
from app.db.session import async_session_factory
from app.main import app
from app.services.report_service import REPORT_COUNT_CACHE_TTL_SECONDS, report_service


@pytest_asyncio.fixture
async def client():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as ac:
        yield ac

@pytest.mark.asyncio
async def test_geo_endpoint_honors_limit(client: AsyncClient):
    """Verify geo endpoint honors limit: default is 500, max is 500, custom limit is respected."""
    # 1. Custom limit=5
    resp = await client.get("/api/v1/geo/incidents", params={"bbox": "77.5,12.9,77.7,13.1", "limit": 5})
    assert resp.status_code == 200
    data = resp.json()
    assert data["type"] == "FeatureCollection"
    assert len(data["features"]) <= 5

    # 2. Default limit is 500
    resp_default = await client.get("/api/v1/geo/incidents", params={"bbox": "77.5,12.9,77.7,13.1"})
    assert resp_default.status_code == 200
    data_def = resp_default.json()
    assert len(data_def["features"]) <= 500

    # 3. Exceeding max limit (501) returns 422 validation error
    resp_excess = await client.get("/api/v1/geo/incidents", params={"bbox": "77.5,12.9,77.7,13.1", "limit": 501})
    assert resp_excess.status_code == 422
    assert "less than or equal to 500" in resp_excess.text

@pytest.mark.asyncio
async def test_report_list_count_cache_filter_separation_and_ttl():
    """Verify report-list count cache keeps different filters separate and documents TTL."""
    import time

    from app.services.report_service import _UNFILTERED_COUNT_CACHE

    # State TTL explicitly (30 seconds)
    assert REPORT_COUNT_CACHE_TTL_SECONDS == 30.0

    async with async_session_factory() as session:
        # 1. Unfiltered query populates count cache
        _UNFILTERED_COUNT_CACHE["expires_at"] = 0.0
        _, total_unfiltered_1, _, _, _ = await report_service.list_reports(session=session, page=1, page_size=5)
        assert _UNFILTERED_COUNT_CACHE["expires_at"] > time.monotonic()
        assert _UNFILTERED_COUNT_CACHE["count"] == total_unfiltered_1

        # 2. Filtered queries keep filters separate (do not pollute or read unfiltered count cache)
        _, total_verified, _, _, _ = await report_service.list_reports(
            session=session, page=1, page_size=5, status="VERIFIED"
        )
        _, total_pending, _, _, _ = await report_service.list_reports(
            session=session, page=1, page_size=5, status="PENDING"
        )
        # Filtered counts reflect their independent subsets
        assert total_verified <= total_unfiltered_1
        assert total_pending <= total_unfiltered_1

        # 3. Cache invalidation on new report creation
        from app.schemas.report import CitizenReportCreate
        test_payload = CitizenReportCreate(
            category_code="HEAVY_RAINFALL",
            severity="MODERATE",
            title="Count Cache Invalidation Test",
            description="Testing cache invalidation on report creation",
            location_name="Test Loc",
            latitude=12.9716,
            longitude=77.5946,
            occurred_at=datetime.now(timezone.utc),
        )
        report, _ = await report_service.create_citizen_report(session=session, payload=test_payload)
        # After creation, the count cache must be invalidated (expires_at == 0.0) so it does not serve stale total
        assert _UNFILTERED_COUNT_CACHE["expires_at"] == 0.0

        # Next unfiltered query fetches fresh total
        _, total_unfiltered_2, _, _, _ = await report_service.list_reports(session=session, page=1, page_size=5)
        assert total_unfiltered_2 == total_unfiltered_1 + 1

@pytest.mark.asyncio
async def test_dashboard_cache_ttl_0_truly_bypasses_redis(monkeypatch, client: AsyncClient):
    """Verify dashboard cache with TTL=0 truly bypasses Redis (0 GET, 0 SET calls)."""
    # Track Redis get/set calls
    get_calls = 0
    set_calls = 0

    orig_get = AsyncRedisClient.get
    orig_set = AsyncRedisClient.set

    async def mock_get(self, key):
        nonlocal get_calls
        get_calls += 1
        return await orig_get(self, key)

    async def mock_set(self, key, value, **kwargs):
        nonlocal set_calls
        set_calls += 1
        return await orig_set(self, key, value, **kwargs)

    monkeypatch.setattr(AsyncRedisClient, "get", mock_get)
    monkeypatch.setattr(AsyncRedisClient, "set", mock_set)
    monkeypatch.setattr(settings, "DASHBOARD_CACHE_TTL_SECONDS", 0)

    # Request dashboard summary
    resp = await client.get("/api/v1/dashboard/summary")
    assert resp.status_code == 200

    # Ensure 0 Redis get/set calls happened
    assert get_calls == 0
    assert set_calls == 0

def test_migration_0012_downgrade_and_upgrade():
    """Verify migration 0012 downgrade to 0011 and upgrade back to head."""
    from pathlib import Path
    ini_path = Path(__file__).resolve().parent.parent / "alembic.ini"
    cfg = Config(str(ini_path))
    cfg.set_main_option("script_location", str(ini_path.parent / "alembic"))
    cfg.attributes["skip_logging_config"] = True
    # Downgrade to 0011
    command.downgrade(cfg, "0011_summary_covering_index")
    # Upgrade back to head (0012)
    command.upgrade(cfg, "head")
