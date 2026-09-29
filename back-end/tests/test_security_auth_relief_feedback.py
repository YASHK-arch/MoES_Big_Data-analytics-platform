"""Unit tests for Security Auth, Relief Center Locator, and Community Feedback API endpoints."""

import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.core.security import create_access_token, get_password_hash, verify_password
from app.main import app


@pytest.mark.asyncio
async def test_password_hashing_and_verification():
    """Test bcrypt password hashing and verification helper."""
    pwd = "EmergencyOps2026!"
    hashed = get_password_hash(pwd)

    assert verify_password(pwd, hashed) is True
    assert verify_password("WrongPassword", hashed) is False


@pytest.mark.asyncio
async def test_jwt_token_creation_and_decryption():
    """Test JWT access token encoding and decoding."""
    token = create_access_token(subject="user_123", role="OPERATOR")
    assert token is not None

    from app.core.security import decode_access_token
    payload = decode_access_token(token)
    assert payload["sub"] == "user_123"
    assert payload["role"] == "OPERATOR"


@pytest.mark.asyncio
async def test_auth_login_endpoint_success_and_failure():
    """Test POST /api/v1/auth/login with valid and invalid credentials."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as ac:
        # 1. Failure with invalid password
        fail_res = await ac.post(
            "/api/v1/auth/login",
            json={"username": "operator@weather-platform.gov.in", "password": "WrongPassword!"},
        )
        assert fail_res.status_code == 401
        assert fail_res.json()["error"]["code"] == "INVALID_CREDENTIALS"

        # 2. Success with valid password
        success_res = await ac.post(
            "/api/v1/auth/login",
            json={"username": "operator@weather-platform.gov.in", "password": "EmergencyOps2026!"},
        )
        assert success_res.status_code == 200
        data = success_res.json()["data"]
        assert "access_token" in data
        assert data["operator"]["email"] == "operator@weather-platform.gov.in"
        assert data["operator"]["role"] == "OPERATOR"


@pytest.mark.asyncio
async def test_unauthenticated_verification_queue_access_denied():
    """Test GET /api/v1/verification/queue without token returns 401 Unauthorized."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as ac:
        res = await ac.get("/api/v1/verification/queue")
        assert res.status_code == 401
        assert res.json()["error"]["code"] == "UNAUTHORIZED"


@pytest.mark.asyncio
async def test_authenticated_verification_queue_access_success():
    """Test GET /api/v1/verification/queue with valid Bearer token succeeds."""
    token = create_access_token(subject="a1b2c3d4-e5f6-7890-abcd-1234567890ab", role="OPERATOR")

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as ac:
        res = await ac.get(
            "/api/v1/verification/queue",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res.status_code == 200
        assert res.json()["success"] is True


@pytest.mark.asyncio
async def test_nearby_relief_centers_endpoint():
    """Test GET /api/v1/geo/relief-centers spatial proximity query."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as ac:
        # Query near Bengaluru (12.9716, 77.5946) within 50 km
        res = await ac.get("/api/v1/geo/relief-centers?lat=12.9716&lng=77.5946&radius_km=50.0")
        assert res.status_code == 200
        data = res.json()["data"]
        assert len(data) >= 1
        bengaluru_shelter = data[0]
        assert "Bengaluru" in bengaluru_shelter["name"]
        assert bengaluru_shelter["distance_km"] <= 10.0


@pytest.mark.asyncio
async def test_community_feedback_vote_endpoint():
    """Test POST /api/v1/incidents/{id}/feedback confirm/dispute voting."""
    from app.db.session import async_session_factory
    from app.models.report import WeatherReport
    from app.models.source import Source

    async with async_session_factory() as session:
        stmt = select(WeatherReport).limit(1)
        res = await session.execute(stmt)
        report = res.scalar_one_or_none()

        if not report:
            src_res = await session.execute(select(Source).limit(1))
            src = src_res.scalar_one_or_none()
            src_id = src.id if src else None

            report = WeatherReport(
                tracking_id=f"RPT-VOTE-{uuid.uuid4().hex[:8]}",
                source_id=src_id,
                title="Heavy Rain Voting Test",
                severity="MODERATE",
                verification_status="VERIFIED",
                latitude=12.9716,
                longitude=77.5946,
            )
            session.add(report)
            await session.commit()
            await session.refresh(report)

        inc_id = str(report.id)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as ac:
        vote_res = await ac.post(
            f"/api/v1/incidents/{inc_id}/feedback",
            json={"vote_type": "CONFIRM"},
        )
        assert vote_res.status_code == 200
        vote_data = vote_res.json()["data"]
        assert vote_data["confirm_count"] >= 1
        assert vote_data["user_voted"] is True
        assert vote_data["voted_type"] == "CONFIRM"


@pytest.mark.asyncio
async def test_citizen_signup_forces_citizen_role_and_autologin():
    """Test POST /api/v1/auth/signup registers citizen and always enforces CITIZEN role."""
    unique_email = f"citizen_{uuid.uuid4().hex[:8]}@example.com"
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as ac:
        res = await ac.post(
            "/api/v1/auth/signup",
            json={
                "email": unique_email,
                "password": "ValidPassword123!",
                "full_name": "Aarav Sharma",
            },
        )
        assert res.status_code == 201
        data = res.json()["data"]
        assert "access_token" in data
        assert data["user"]["email"] == unique_email
        assert data["user"]["role"] == "CITIZEN"

        # Attempt duplicate signup with same email -> 409 Conflict
        dup_res = await ac.post(
            "/api/v1/auth/signup",
            json={
                "email": unique_email,
                "password": "ValidPassword123!",
                "full_name": "Aarav Sharma Duplicate",
            },
        )
        assert dup_res.status_code == 409
        assert dup_res.json()["error"]["code"] == "EMAIL_ALREADY_EXISTS"


@pytest.mark.asyncio
async def test_citizen_cannot_access_operator_verification_queue():
    """Test that a valid logged-in citizen is strictly blocked from Operator endpoints (403 Forbidden)."""
    unique_email = f"citizen_{uuid.uuid4().hex[:8]}@example.com"
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as ac:
        # 1. Signup citizen
        signup_res = await ac.post(
            "/api/v1/auth/signup",
            json={
                "email": unique_email,
                "password": "CitizenSecret2026!",
                "full_name": "Citizen User",
            },
        )
        assert signup_res.status_code == 201
        token = signup_res.json()["data"]["access_token"]

        # 2. Try to access operator verification queue with citizen JWT -> 403 Forbidden
        queue_res = await ac.get(
            "/api/v1/verification/queue",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert queue_res.status_code == 403
        assert queue_res.json()["error"]["code"] == "FORBIDDEN"


@pytest.mark.asyncio
async def test_citizen_location_persistence_and_profile():
    """Test PUT /api/v1/citizen/me/location and GET /api/v1/citizen/me."""
    unique_email = f"citizen_{uuid.uuid4().hex[:8]}@example.com"
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as ac:
        # 1. Signup citizen
        signup_res = await ac.post(
            "/api/v1/auth/signup",
            json={
                "email": unique_email,
                "password": "CitizenSecret2026!",
                "full_name": "Priya Patel",
            },
        )
        assert signup_res.status_code == 201
        token = signup_res.json()["data"]["access_token"]

        # 2. Save location preferences
        loc_res = await ac.put(
            "/api/v1/citizen/me/location",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "latitude": 19.0760,
                "longitude": 72.8777,
                "location_name": "Mumbai South",
                "alert_radius_km": 30.0,
            },
        )
        assert loc_res.status_code == 200
        loc_data = loc_res.json()
        assert loc_data["home_location_name"] == "Mumbai South"
        assert loc_data["home_location_lat"] == 19.0760
        assert loc_data["alert_radius_km"] == 30.0

        # 3. Retrieve /api/v1/citizen/me
        me_res = await ac.get(
            "/api/v1/citizen/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert me_res.status_code == 200
        assert me_res.json()["home_location_name"] == "Mumbai South"
