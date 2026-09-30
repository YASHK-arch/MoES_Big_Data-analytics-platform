import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.db.session import async_session_factory
from app.main import app
from app.models.report import WeatherReport
from app.services.storage import storage_service


@pytest.fixture(autouse=True)
def ensure_storage_ready():
    """Ensure MinIO bucket exists before running tests."""
    storage_service.ensure_bucket_exists()


@pytest.mark.asyncio
async def test_demo_flag_detection_and_filter():
    """Test is_demo detection on report submission and hide_demo query filtering across API surfaces."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # 1. Submit a DEMO report
        demo_payload = {
            "latitude": "19.0760",
            "longitude": "72.8777",
            "category_code": "FLOOD_WATERLOGGING",
            "severity": "HIGH",
            "title": "[DEMO] Simulated Flash Flood in Bandra",
            "description": "Simulated flood scenario for drill exercise.",
            "location_name": "Bandra West, Mumbai",
        }
        res_demo = await client.post("/api/v1/reports", data=demo_payload)
        assert res_demo.status_code == 201
        demo_id = res_demo.json()["data"]["id"]

        # 2. Submit a LIVE real report
        live_payload = {
            "latitude": "19.0800",
            "longitude": "72.8850",
            "category_code": "HEAVY_RAINFALL",
            "severity": "MODERATE",
            "title": "Continuous heavy downpour near BKC junction",
            "description": "Visibility reduced, moderate water accumulation.",
            "location_name": "BKC, Mumbai",
        }
        res_live = await client.post("/api/v1/reports", data=live_payload)
        assert res_live.status_code == 201
        live_id = res_live.json()["data"]["id"]

        # Verify DB is_demo flags
        async with async_session_factory() as session:
            demo_row = await session.scalar(
                select(WeatherReport).where(WeatherReport.id == demo_id)
            )
            assert demo_row is not None
            assert demo_row.is_demo is True

            live_row = await session.scalar(
                select(WeatherReport).where(WeatherReport.id == live_id)
            )
            assert live_row is not None
            assert live_row.is_demo is False

        # 3. Test GET /api/v1/reports with hide_demo
        # Without hide_demo (default False): both present
        res_all_reports = await client.get("/api/v1/reports?limit=100")
        assert res_all_reports.status_code == 200
        ids_all = [r["id"] for r in res_all_reports.json()["data"]]
        assert demo_id in ids_all
        assert live_id in ids_all

        # With hide_demo=true: demo excluded, live included
        res_filtered_reports = await client.get("/api/v1/reports?limit=100&hide_demo=true")
        assert res_filtered_reports.status_code == 200
        ids_filtered = [r["id"] for r in res_filtered_reports.json()["data"]]
        assert demo_id not in ids_filtered
        assert live_id in ids_filtered

        # Check is_demo field in serialized report detail
        demo_item = next(r for r in res_all_reports.json()["data"] if r["id"] == demo_id)
        assert demo_item.get("is_demo") is True
        live_item = next(r for r in res_all_reports.json()["data"] if r["id"] == live_id)
        assert live_item.get("is_demo") is False

        # 4. Test GET /api/v1/incidents with hide_demo
        res_incidents_all = await client.get("/api/v1/incidents?page_size=100")
        assert res_incidents_all.status_code == 200
        incident_ids_all = [i["id"] for i in res_incidents_all.json()["data"]]
        assert demo_id in incident_ids_all
        assert live_id in incident_ids_all

        res_incidents_live = await client.get("/api/v1/incidents?page_size=100&hide_demo=true")
        assert res_incidents_live.status_code == 200
        incident_ids_live = [i["id"] for i in res_incidents_live.json()["data"]]
        assert demo_id not in incident_ids_live
        assert live_id in incident_ids_live

        # 5. Test GET /api/v1/geo/incidents with hide_demo
        res_geo_all = await client.get("/api/v1/geo/incidents")
        assert res_geo_all.status_code == 200
        geo_all_features = res_geo_all.json()["features"]
        geo_all_ids = [f["properties"]["id"] for f in geo_all_features]
        assert demo_id in geo_all_ids
        assert live_id in geo_all_ids

        res_geo_live = await client.get("/api/v1/geo/incidents?hide_demo=true")
        assert res_geo_live.status_code == 200
        geo_live_features = res_geo_live.json()["features"]
        geo_live_ids = [f["properties"]["id"] for f in geo_live_features]
        assert demo_id not in geo_live_ids
        assert live_id in geo_live_ids

        # 6. Test dashboard summary aggregation with hide_demo
        async with async_session_factory() as session:
            from app.services.incident_query_service import incident_query_service

            sum_all = await incident_query_service.get_dashboard_summary(
                session=session, time_range="all", hide_demo=False
            )
            sum_live = await incident_query_service.get_dashboard_summary(
                session=session, time_range="all", hide_demo=True
            )
            assert sum_all.total_count > sum_live.total_count
            assert sum_all.total_count - sum_live.total_count >= 1
