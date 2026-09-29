import uuid
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from geoalchemy2.shape import from_shape
from httpx import ASGITransport, AsyncClient
from shapely.geometry import Point, Polygon

from app.db.session import async_session_factory
from app.main import app
from app.models.category import EventCategory
from app.models.forecast import ForecastAdvisory
from app.models.report import WeatherReport
from app.models.source import Source


@pytest_asyncio.fixture
async def async_client():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        yield client


@pytest.mark.asyncio
async def test_route_corridor_check_with_intersecting_hazard():
    """Test POST /api/v1/routes/check detects hazards within corridor buffer."""
    async with async_session_factory() as session:
        # Fetch valid source and category
        src_res = await session.execute(Source.__table__.select().limit(1))
        src = src_res.first()
        src_id = src.id if src else None

        cat_res = await session.execute(
            EventCategory.__table__.select().where(EventCategory.category_code == "URBAN_FLOOD")
        )
        cat = cat_res.first()
        cat_id = cat.id if cat else None

        # Insert hazard point directly along line between (77.5900, 12.9700) and (77.6100, 12.9700)
        track_id = f"RPT-ROUTE-{uuid.uuid4().hex[:8].upper()}"
        hazard_point = Point(77.6000, 12.9700)
        report = WeatherReport(
            tracking_id=track_id,
            source_id=src_id,
            title="Severe Waterlogging on Route Corridor",
            severity="SEVERE",
            verification_status="VERIFIED",
            credibility_score=0.92,
            credibility_explanation={"positive_drivers": ["High trust institutional source IMD_NOWCAST."]},
            latitude=12.9700,
            longitude=77.6000,
            geom=from_shape(hazard_point, srid=4326),
            occurred_at=datetime.now(timezone.utc),
            category_id=cat_id,
            reported_category="URBAN_FLOOD",
        )
        session.add(report)
        await session.commit()
        await session.refresh(report)

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            resp = await client.post(
                "/api/v1/routes/check",
                json={
                    "origin": {"latitude": 12.9700, "longitude": 77.5900, "name": "Point A"},
                    "destination": {"latitude": 12.9700, "longitude": 77.6100, "name": "Point B"},
                    "corridor_km": 2.0,
                },
            )
            assert resp.status_code == 200
            data = resp.json()["data"]
            assert data["is_blocked"] is True
            assert data["hazard_count"] >= 1
            assert data["corridor_km"] == 2.0
            assert data["highest_severity"] == "SEVERE"
            assert len(data["intersecting_incidents"]) >= 1
            matching_hazards = [h for h in data["intersecting_incidents"] if h["tracking_id"] == track_id]
            assert len(matching_hazards) == 1
            assert matching_hazards[0]["distance_to_corridor_center_m"] <= 2000.0


@pytest.mark.asyncio
async def test_nearby_geo_incidents_endpoint():
    """Test GET /api/v1/geo/incidents/nearby returns spatial radius features."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        resp = await client.get(
            "/api/v1/geo/incidents/nearby",
            params={"lat": 12.9716, "lng": 77.5946, "radius_km": 25.0},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["type"] == "FeatureCollection"
        assert isinstance(data["features"], list)


@pytest.mark.asyncio
async def test_forecast_advisories_endpoint():
    """Test forecast advisories creation and GET /api/v1/geo/forecasts endpoint."""
    async with async_session_factory() as session:
        poly = Polygon([(70.0, 15.0), (75.0, 15.0), (75.0, 20.0), (70.0, 20.0), (70.0, 15.0)])
        adv = ForecastAdvisory(
            source_code="IMD_BULLETIN",
            hazard_type="CYCLONE",
            severity="SEVERE",
            advisory_title="Severe Cyclonic Storm Alert - West Coast",
            advisory_text="Extremely heavy rainfall and gusty winds projected for coastal Maharashtra & Goa.",
            geom=from_shape(poly, srid=4326),
            issued_at=datetime.now(timezone.utc),
            valid_from=datetime.now(timezone.utc),
            valid_until=datetime.now(timezone.utc) + timedelta(hours=48),
        )
        session.add(adv)
        await session.commit()

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            resp = await client.get("/api/v1/geo/forecasts")
            assert resp.status_code == 200
            data = resp.json()
            assert data["type"] == "FeatureCollection"
            assert len(data["features"]) >= 1
            feat = data["features"][0]
            assert feat["properties"]["category_code"] == "CYCLONE"
            assert feat["properties"]["credibility_score"] == 0.95
