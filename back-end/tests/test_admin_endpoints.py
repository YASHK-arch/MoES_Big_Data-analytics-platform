import uuid
from datetime import datetime, timezone

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.main import app
from app.models.audit import AuditLog
from app.models.outbox import RealtimeOutbox
from app.models.report import WeatherReport
from app.models.verification import VerificationEvent


@pytest.mark.asyncio
class TestAdminEndpoints:
    """Comprehensive test suite for R3 Admin features:
    - 401 without auth
    - Hard limit enforcement (max 50k export, max 100 bulk ids)
    - Streaming CSV and GeoJSON exports
    - Atomic bulk verification and audit trail creation
    - Audit log querying and pagination
    """

    async def test_admin_endpoints_require_auth_401(self):
        """Unauthenticated requests must return 401 Unauthorized across all admin endpoints."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            res_csv = await client.get("/api/v1/admin/export/csv")
            assert res_csv.status_code == 401

            res_geo = await client.get("/api/v1/admin/export/geojson")
            assert res_geo.status_code == 401

            res_bulk = await client.post(
                "/api/v1/admin/verification/bulk",
                json={"incident_ids": ["test-id"], "action": "VERIFY"},
            )
            assert res_bulk.status_code == 401

            res_logs = await client.get("/api/v1/admin/audit-logs")
            assert res_logs.status_code == 401

    async def test_export_limits_enforced_422(self, api_client: AsyncClient):
        """Export limit exceeding 50,000 rows must be rejected with HTTP 422."""
        res_csv = await api_client.get("/api/v1/admin/export/csv?limit=50001")
        assert res_csv.status_code == 422

        res_geo = await api_client.get("/api/v1/admin/export/geojson?limit=50001")
        assert res_geo.status_code == 422

    async def test_bulk_verification_limit_enforced_422(self, api_client: AsyncClient):
        """Bulk verification exceeding 100 incident IDs must be rejected with HTTP 422."""
        excessive_ids = [f"INC-{i:04d}" for i in range(101)]
        res = await api_client.post(
            "/api/v1/admin/verification/bulk",
            json={"incident_ids": excessive_ids, "action": "VERIFY"},
        )
        assert res.status_code == 422

    async def test_csv_export_streaming(self, api_client: AsyncClient, db_session: AsyncSession):
        """Streamed CSV export must include headers and properly formatted CSV rows."""
        from app.services.report_service import report_service

        source = await report_service.get_or_create_source(db_session, source_code="CITIZEN")
        tracking_id = f"R3-CSV-{uuid.uuid4().hex[:8].upper()}"
        now = datetime.now(timezone.utc)
        rep = WeatherReport(
            id=uuid.uuid4(),
            tracking_id=tracking_id,
            source_id=source.id,
            title="CSV Export Stream Test Incident",
            description="Testing CSV streaming export",
            reported_category="FLOOD_WATERLOGGING",
            severity="SEVERE",
            verification_status="PENDING",
            processing_status="PENDING",
            credibility_score=0.88,
            latitude=19.0760,
            longitude=72.8777,
            location_name="Mumbai, Maharashtra",
            geom="SRID=4326;POINT(72.8777 19.0760)",
            occurred_at=now,
            is_demo=False,
        )
        db_session.add(rep)
        await db_session.commit()

        res = await api_client.get("/api/v1/admin/export/csv?limit=100")
        assert res.status_code == 200
        assert "text/csv" in res.headers["content-type"]
        assert "attachment; filename=" in res.headers["content-disposition"]

        content = res.text
        lines = content.strip().split("\r\n")
        header = lines[0]
        assert "id,tracking_id,title,category,severity,status" in header
        assert tracking_id in content
        assert "FLOOD_WATERLOGGING" in content

    async def test_geojson_export_streaming(
        self, api_client: AsyncClient, db_session: AsyncSession
    ):
        """Streamed GeoJSON export must return a valid FeatureCollection structure."""
        from app.services.report_service import report_service

        source = await report_service.get_or_create_source(db_session, source_code="CITIZEN")
        tracking_id = f"R3-GEO-{uuid.uuid4().hex[:8].upper()}"
        now = datetime.now(timezone.utc)
        rep = WeatherReport(
            id=uuid.uuid4(),
            tracking_id=tracking_id,
            source_id=source.id,
            title="GeoJSON Stream Test Incident",
            description="Testing GeoJSON streaming export",
            reported_category="CYCLONE_STORM",
            severity="CRITICAL",
            verification_status="PENDING",
            processing_status="PENDING",
            credibility_score=0.92,
            latitude=20.2961,
            longitude=85.8245,
            location_name="Bhubaneswar, Odisha",
            geom="SRID=4326;POINT(85.8245 20.2961)",
            occurred_at=now,
            is_demo=False,
        )
        db_session.add(rep)
        await db_session.commit()

        res = await api_client.get("/api/v1/admin/export/geojson?limit=100")
        assert res.status_code == 200
        assert "application/geo+json" in res.headers["content-type"]

        data = res.json()
        assert data["type"] == "FeatureCollection"
        assert isinstance(data["features"], list)
        matching = [f for f in data["features"] if f["properties"]["tracking_id"] == tracking_id]
        assert len(matching) == 1
        assert matching[0]["geometry"]["type"] == "Point"
        assert matching[0]["geometry"]["coordinates"] == [85.8245, 20.2961]

    async def test_bulk_verify_atomic_and_audit_rows(
        self, api_client: AsyncClient, db_session: AsyncSession
    ):
        """Bulk verify updates statuses atomically and creates exactly 1 audit row per incident."""
        from app.services.report_service import report_service

        source = await report_service.get_or_create_source(db_session, source_code="CITIZEN")
        now = datetime.now(timezone.utc)
        inc_1 = WeatherReport(
            id=uuid.uuid4(),
            tracking_id=f"R3-BULK-A-{uuid.uuid4().hex[:8].upper()}",
            source_id=source.id,
            title="Bulk Triage Incident 1",
            reported_category="FLOOD_WATERLOGGING",
            severity="MODERATE",
            verification_status="PENDING",
            processing_status="PENDING",
            latitude=19.0760,
            longitude=72.8777,
            geom="SRID=4326;POINT(72.8777 19.0760)",
            occurred_at=now,
            is_demo=False,
        )
        inc_2 = WeatherReport(
            id=uuid.uuid4(),
            tracking_id=f"R3-BULK-B-{uuid.uuid4().hex[:8].upper()}",
            source_id=source.id,
            title="Bulk Triage Incident 2",
            reported_category="FLOOD_WATERLOGGING",
            severity="MODERATE",
            verification_status="PENDING",
            processing_status="PENDING",
            latitude=19.0760,
            longitude=72.8777,
            geom="SRID=4326;POINT(72.8777 19.0760)",
            occurred_at=now,
            is_demo=False,
        )
        db_session.add_all([inc_1, inc_2])
        await db_session.commit()

        res = await api_client.post(
            "/api/v1/admin/verification/bulk",
            json={
                "incident_ids": [str(inc_1.id), str(inc_2.id)],
                "action": "VERIFY",
                "notes": "Verified by regional operator squad",
            },
        )
        assert res.status_code == 200
        data = res.json()["data"]
        assert data["processed_count"] == 2
        assert data["action"] == "VERIFY"

        await db_session.refresh(inc_1)
        await db_session.refresh(inc_2)
        assert inc_1.verification_status == "VERIFIED"
        assert inc_2.verification_status == "VERIFIED"

        v1_res = await db_session.execute(
            select(VerificationEvent).where(VerificationEvent.report_id == inc_1.id)
        )
        v1_events = list(v1_res.scalars().all())
        assert len(v1_events) == 1
        assert v1_events[0].previous_status == "PENDING"
        assert v1_events[0].new_status == "VERIFIED"

        v2_res = await db_session.execute(
            select(VerificationEvent).where(VerificationEvent.report_id == inc_2.id)
        )
        v2_events = list(v2_res.scalars().all())
        assert len(v2_events) == 1
        assert v2_events[0].previous_status == "PENDING"
        assert v2_events[0].new_status == "VERIFIED"

        a_res = await db_session.execute(
            select(AuditLog).where(
                AuditLog.action == "BULK_VERIFY",
                AuditLog.entity_id.in_([str(inc_1.id), str(inc_2.id)]),
            )
        )
        audit_rows = list(a_res.scalars().all())
        assert len(audit_rows) >= 2

        outbox_res = await db_session.execute(
            select(RealtimeOutbox).where(
                RealtimeOutbox.entity_id == str(inc_1.id),
                RealtimeOutbox.event_type == "report.verification_changed",
            )
        )
        outbox_row = outbox_res.scalar_one()
        assert outbox_row.status == "PENDING"

        from app.core.redis import redis_client

        stream_entries = await redis_client.xrevrange(
            "stream:weather:realtime", max_id="+", min_id="-", count=100
        )
        assert any(
            entry[1].get("event_id") == str(outbox_row.event_id)
            and entry[1].get("event_type") == "report.verification_changed"
            for entry in stream_entries
        )

        res_logs = await api_client.get("/api/v1/admin/audit-logs?action=BULK_VERIFY")
        assert res_logs.status_code == 200
        logs_data = res_logs.json()
        assert logs_data["success"] is True
        assert len(logs_data["data"]) >= 2
        first_log = logs_data["data"][0]
        assert first_log["action"] == "BULK_VERIFY"
        assert first_log["user_email"] is not None

    async def test_bulk_verify_rollback_on_invalid_id(
        self, api_client: AsyncClient, db_session: AsyncSession
    ):
        """Atomic guarantee: if any ID in the bulk batch is invalid, all updates roll back."""
        from app.services.report_service import report_service

        source = await report_service.get_or_create_source(db_session, source_code="CITIZEN")
        now = datetime.now(timezone.utc)
        valid_inc = WeatherReport(
            id=uuid.uuid4(),
            tracking_id=f"R3-ROLLBACK-{uuid.uuid4().hex[:8].upper()}",
            source_id=source.id,
            title="Rollback Test Incident",
            reported_category="FLOOD_WATERLOGGING",
            severity="MODERATE",
            verification_status="PENDING",
            processing_status="PENDING",
            latitude=19.0760,
            longitude=72.8777,
            geom="SRID=4326;POINT(72.8777 19.0760)",
            occurred_at=now,
            is_demo=False,
        )
        db_session.add(valid_inc)
        await db_session.commit()

        res = await api_client.post(
            "/api/v1/admin/verification/bulk",
            json={
                "incident_ids": [str(valid_inc.id), str(uuid.uuid4())],
                "action": "VERIFY",
            },
        )
        assert res.status_code == 400

        await db_session.refresh(valid_inc)
        assert valid_inc.verification_status == "PENDING"

    async def test_bulk_verify_rejects_invalid_transition(
        self, api_client: AsyncClient, db_session: AsyncSession
    ):
        """Bulk verification rejects reports already in a terminal state."""
        from app.services.report_service import report_service

        source = await report_service.get_or_create_source(db_session, source_code="CITIZEN")
        terminal_incident = WeatherReport(
            id=uuid.uuid4(),
            tracking_id=f"R3-TERMINAL-{uuid.uuid4().hex[:8].upper()}",
            source_id=source.id,
            title="Already verified incident",
            reported_category="FLOOD_WATERLOGGING",
            severity="MODERATE",
            verification_status="VERIFIED",
            processing_status="COMPLETED",
            latitude=19.0760,
            longitude=72.8777,
            geom="SRID=4326;POINT(72.8777 19.0760)",
            occurred_at=datetime.now(timezone.utc),
            is_demo=False,
        )
        db_session.add(terminal_incident)
        await db_session.commit()

        response = await api_client.post(
            "/api/v1/admin/verification/bulk",
            json={"incident_ids": [str(terminal_incident.id)], "action": "VERIFY"},
        )

        assert response.status_code == 400
        await db_session.refresh(terminal_incident)
        assert terminal_incident.verification_status == "VERIFIED"
