"""Database Seeding Script for Evaluator & Demo Accounts, Relief Shelters, and Weather Incidents."""

import asyncio
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone

# Add parent directory to path so 'app' package imports work cleanly
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from geoalchemy2.elements import WKTElement
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_password_hash
from app.db.session import async_session_factory
from app.models.category import EventCategory
from app.models.forecast import ForecastAdvisory
from app.models.relief_center import ReliefCenter
from app.models.report import WeatherReport
from app.models.source import Source
from app.models.user import User


async def seed_users(session: AsyncSession) -> None:
    """Seed default Admin, Operator, and Citizen accounts."""
    admin_pwd = get_password_hash("EmergencyAdmin2026!")
    operator_pwd = get_password_hash("EmergencyOps2026!")
    citizen_pwd = get_password_hash("CitizenPassword2026!")

    users_data = [
        {
            "id": uuid.UUID("00000000-0000-0000-0000-000000000001"),
            "email": "admin@weather-platform.gov.in",
            "full_name": "Chief System Administrator",
            "hashed_password": admin_pwd,
            "role": "ADMIN",
            "jurisdiction_code": "NATIONAL_HQ",
        },
        {
            "id": uuid.UUID("a1b2c3d4-e5f6-7890-abcd-1234567890ab"),
            "email": "operator@weather-platform.gov.in",
            "full_name": "National DEOC Lead Operator",
            "hashed_password": operator_pwd,
            "role": "OPERATOR",
            "jurisdiction_code": "NATIONAL_DEOC",
        },
        {
            "id": uuid.UUID("c1c2c3c4-c5c6-7890-abcd-1234567890ab"),
            "email": "citizen@example.com",
            "full_name": "Aarav Sharma",
            "hashed_password": citizen_pwd,
            "role": "CITIZEN",
            "home_location_lat": 12.9716,
            "home_location_lng": 77.5946,
            "home_location_name": "Bengaluru Central",
            "alert_radius_km": 25.0,
        },
    ]

    for data in users_data:
        stmt = select(User).where(User.email == data["email"])
        res = await session.execute(stmt)
        existing = res.scalar_one_or_none()
        if not existing:
            user = User(
                id=data["id"],
                email=data["email"],
                full_name=data["full_name"],
                hashed_password=data["hashed_password"],
                role=data["role"],
                jurisdiction_code=data.get("jurisdiction_code"),
                home_location_lat=data.get("home_location_lat"),
                home_location_lng=data.get("home_location_lng"),
                home_location_name=data.get("home_location_name"),
                alert_radius_km=data.get("alert_radius_km", 25.0),
                is_active=True,
            )
            session.add(user)
        else:
            existing.hashed_password = data["hashed_password"]
            existing.role = data["role"]
            existing.is_active = True

    await session.commit()
    print("✅ Seeded Admin, Operator, and Citizen accounts.")


async def seed_relief_centers(session: AsyncSession) -> None:
    """Seed comprehensive relief centers across major Indian metropolitan centers."""
    shelters_data = [
        {
            "id": uuid.UUID("11111111-1111-1111-1111-111111111111"),
            "name": "Bengaluru Central Cyclone & Flood Relief Shelter",
            "center_type": "SHELTER",
            "address": "Kanteerava Indoor Stadium Complex, MG Road, Bengaluru",
            "district_name": "Bengaluru Urban",
            "state_name": "Karnataka",
            "capacity": 1500,
            "occupied_count": 120,
            "contact_phone": "080-22942222",
            "latitude": 12.9700,
            "longitude": 77.5900,
        },
        {
            "id": uuid.UUID("22222222-2222-2222-2222-222222222222"),
            "name": "Victoria Hospital Emergency Disaster Care Unit",
            "center_type": "HOSPITAL",
            "address": "Fort, Near City Market, Bengaluru",
            "district_name": "Bengaluru Urban",
            "state_name": "Karnataka",
            "capacity": 800,
            "occupied_count": 340,
            "contact_phone": "080-26701150",
            "latitude": 12.9630,
            "longitude": 77.5740,
        },
        {
            "id": uuid.UUID("33333333-3333-3333-3333-333333333333"),
            "name": "Chennai Central Multipurpose Evacuation Shelter",
            "center_type": "SHELTER",
            "address": "Marina Beach Promenade, Triplicane, Chennai",
            "district_name": "Chennai",
            "state_name": "Tamil Nadu",
            "capacity": 2500,
            "occupied_count": 450,
            "contact_phone": "044-25619200",
            "latitude": 13.0600,
            "longitude": 80.2800,
        },
        {
            "id": uuid.UUID("44444444-4444-4444-4444-444444444444"),
            "name": "Mumbai Coastal Relief Camp #4",
            "center_type": "RELIEF_CAMP",
            "address": "Dadar West Flood Relief Center, Dadar, Mumbai",
            "district_name": "Mumbai City",
            "state_name": "Maharashtra",
            "capacity": 3000,
            "occupied_count": 600,
            "contact_phone": "022-24137800",
            "latitude": 19.0180,
            "longitude": 72.8430,
        },
        {
            "id": uuid.UUID("55555555-5555-5555-5555-555555555555"),
            "name": "Delhi NCR Flood Relief Camp & Evacuation Hub",
            "center_type": "SHELTER",
            "address": "Yamuna Sports Complex, Surajmal Vihar, Delhi",
            "district_name": "East Delhi",
            "state_name": "Delhi",
            "capacity": 3500,
            "occupied_count": 210,
            "contact_phone": "011-22156700",
            "latitude": 28.6650,
            "longitude": 77.3010,
        },
        {
            "id": uuid.UUID("66666666-6666-6666-6666-666666666666"),
            "name": "Kolkata Cyclone Emergency Shelter #2",
            "center_type": "SHELTER",
            "address": "Salt Lake Stadium Gate 3, Sector III, Kolkata",
            "district_name": "North 24 Parganas",
            "state_name": "West Bengal",
            "capacity": 4000,
            "occupied_count": 780,
            "contact_phone": "033-23351234",
            "latitude": 22.5697,
            "longitude": 88.4060,
        },
    ]

    for s_data in shelters_data:
        stmt = select(ReliefCenter).where(ReliefCenter.id == s_data["id"])
        res = await session.execute(stmt)
        existing = res.scalar_one_or_none()

        geom = WKTElement(f"POINT({s_data['longitude']} {s_data['latitude']})", srid=4326)

        if not existing:
            center = ReliefCenter(
                id=s_data["id"],
                name=s_data["name"],
                center_type=s_data["center_type"],
                address=s_data["address"],
                district_name=s_data["district_name"],
                state_name=s_data["state_name"],
                capacity=s_data["capacity"],
                occupied_count=s_data["occupied_count"],
                contact_phone=s_data["contact_phone"],
                latitude=s_data["latitude"],
                longitude=s_data["longitude"],
                geom=geom,
                is_active=True,
            )
            session.add(center)
        else:
            existing.capacity = s_data["capacity"]
            existing.occupied_count = s_data["occupied_count"]

    await session.commit()
    print("✅ Seeded 6 Metropolitan Relief Shelters.")


async def seed_active_incidents(session: AsyncSession) -> None:
    """Seed active verified incidents with PostGIS coordinates across India."""
    # Ensure source exists
    src_res = await session.execute(select(Source).where(Source.source_code == "CITIZEN_WEB"))
    source = src_res.scalar_one_or_none()
    if not source:
        source = Source(
            source_code="CITIZEN_WEB",
            name="Citizen Web Portal",
            source_type="CITIZEN_REPORT",
            base_trust_score=0.6,
            is_active=True,
        )
        session.add(source)
        await session.flush()

    # Ensure categories exist
    flood_cat = await session.execute(select(EventCategory).where(EventCategory.category_code == "FLOOD_WATERLOGGING"))
    cat_flood = flood_cat.scalar_one_or_none()
    cat_flood_id = cat_flood.id if cat_flood else None

    incidents_data = [
        {
            "tracking_id": "RPT-DEMO-BLR001",
            "title": "Severe Waterlogging on S.V. Road & Underpass",
            "severity": "HIGH",
            "category_id": cat_flood_id,
            "reported_category": "FLOOD_WATERLOGGING",
            "description": "Water level reaching 2 feet near railway underpass causing traffic halt.",
            "location_name": "MG Road / Brigade Road, Bengaluru",
            "latitude": 12.9716,
            "longitude": 77.5946,
            "credibility_score": 0.88,
            "verification_status": "VERIFIED",
        },
        {
            "tracking_id": "RPT-DEMO-MUM002",
            "title": "Severe Coastal Flash Inundation",
            "severity": "SEVERE",
            "category_id": cat_flood_id,
            "reported_category": "FLOOD_WATERLOGGING",
            "description": "High tide combining with cloudburst rainfall inundating lower levels.",
            "location_name": "Bandra West, Mumbai",
            "latitude": 19.0596,
            "longitude": 72.8295,
            "credibility_score": 0.92,
            "verification_status": "VERIFIED",
        },
        {
            "tracking_id": "RPT-DEMO-DEL003",
            "title": "Yamuna River Bank Overtopping Alert",
            "severity": "SEVERE",
            "category_id": cat_flood_id,
            "reported_category": "FLOOD_WATERLOGGING",
            "description": "Water discharge from upstream causing low-lying area inundation.",
            "location_name": "Kashmere Gate / Ring Road, Delhi",
            "latitude": 28.6692,
            "longitude": 77.2285,
            "credibility_score": 0.95,
            "verification_status": "VERIFIED",
        },
        {
            "tracking_id": "RPT-DEMO-CHN004",
            "title": "Waterlogging in Velachery Low-lying Sectors",
            "severity": "MODERATE",
            "category_id": cat_flood_id,
            "reported_category": "FLOOD_WATERLOGGING",
            "description": "Storm water drain overflow along main arterial residential stretch.",
            "location_name": "Velachery, Chennai",
            "latitude": 12.9815,
            "longitude": 80.2180,
            "credibility_score": 0.82,
            "verification_status": "VERIFIED",
        },
    ]

    for inc in incidents_data:
        stmt = select(WeatherReport).where(WeatherReport.tracking_id == inc["tracking_id"])
        res = await session.execute(stmt)
        existing = res.scalar_one_or_none()

        geom = WKTElement(f"POINT({inc['longitude']} {inc['latitude']})", srid=4326)

        if not existing:
            report = WeatherReport(
                id=uuid.uuid4(),
                tracking_id=inc["tracking_id"],
                source_id=source.id,
                category_id=inc["category_id"],
                reported_category=inc["reported_category"],
                severity=inc["severity"],
                title=inc["title"],
                description=inc["description"],
                location_name=inc["location_name"],
                latitude=inc["latitude"],
                longitude=inc["longitude"],
                geom=geom,
                occurred_at=datetime.now(timezone.utc),
                processing_status="COMPLETED",
                verification_status=inc["verification_status"],
                credibility_score=inc["credibility_score"],
            )
            session.add(report)

    await session.commit()
    print("✅ Seeded Active Verified Metro Weather Incidents.")


async def seed_forecast_advisories(session: AsyncSession) -> None:
    """Seed active official forecast advisories across representative Indian regions."""
    now = datetime.now(timezone.utc)
    advisories = [
        {
            "source_code": "NDMA_SACHET",
            "hazard_type": "CYCLONE_TRACK",
            "severity": "HIGH",
            "advisory_title": "Cyclone Track Advisory - Arabian Sea Coast",
            "advisory_text": "Forecast track indicates hazardous winds and heavy rainfall along the west coast.",
            "geom": "LINESTRING(72.8777 19.0760, 72.6500 19.5000, 72.4000 20.0500)",
        },
        {
            "source_code": "NDMA_SACHET",
            "hazard_type": "FLOOD_WARNING",
            "severity": "SEVERE",
            "advisory_title": "Flood Warning Zone - Brahmaputra Basin",
            "advisory_text": "Low-lying districts should prepare for river level rise and localized inundation.",
            "geom": "POLYGON((91.5000 26.0000, 92.3000 26.0000, 92.3000 26.7000, 91.5000 26.7000, 91.5000 26.0000))",
        },
        {
            "source_code": "IMD_NOWCAST",
            "hazard_type": "HEAVY_RAINFALL",
            "severity": "MODERATE",
            "advisory_title": "Heavy Rainfall Watch - Bengaluru Region",
            "advisory_text": "Thunderstorm activity and intense rainfall are possible during the advisory window.",
            "geom": "POINT(77.5946 12.9716)",
        },
        {
            "source_code": "NDMA_SACHET",
            "hazard_type": "CYCLONE_TRACK",
            "severity": "MODERATE",
            "advisory_title": "Cyclone Track Advisory - Bay of Bengal",
            "advisory_text": "Coastal authorities should monitor changing wind and rainfall conditions.",
            "geom": "LINESTRING(87.6000 15.2000, 87.9000 16.0000, 88.2000 16.8000)",
        },
    ]

    for advisory in advisories:
        existing = await session.scalar(
            select(ForecastAdvisory).where(
                ForecastAdvisory.source_code == advisory["source_code"],
                ForecastAdvisory.advisory_title == advisory["advisory_title"],
            )
        )
        if existing:
            existing.valid_from = now
            existing.valid_until = now + timedelta(days=3)
            continue

        session.add(
            ForecastAdvisory(
                source_code=advisory["source_code"],
                hazard_type=advisory["hazard_type"],
                severity=advisory["severity"],
                advisory_title=advisory["advisory_title"],
                advisory_text=advisory["advisory_text"],
                geom=WKTElement(advisory["geom"], srid=4326),
                valid_from=now,
                valid_until=now + timedelta(days=3),
                issued_at=now,
                raw_payload={"seed": True, "source_code": advisory["source_code"]},
            )
        )

    await session.commit()
    print("✅ Seeded 4 active forecast advisories.")


async def main() -> None:
    print("🌱 Running National Weather Platform Database Seeder...")
    async with async_session_factory() as session:
        await seed_users(session)
        await seed_relief_centers(session)
        await seed_active_incidents(session)
        await seed_forecast_advisories(session)
    print("🚀 All demo data seeded successfully!")


if __name__ == "__main__":
    asyncio.run(main())
