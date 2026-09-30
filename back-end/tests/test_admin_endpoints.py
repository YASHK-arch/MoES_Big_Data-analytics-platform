import json
import uuid
from datetime import datetime, timezone

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, inspect, select
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
                AuditLog.action == "VERIFY",
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

        from unittest.mock import AsyncMock, MagicMock

        from app.api.v1.events import broadcaster, get_redis_client
        from app.core.redis import AsyncRedisClient, redis_client

        stream_entries = await redis_client.xrevrange(
            "stream:weather:realtime", max_id="+", min_id="-", count=100
        )
        matching_entry = next(
            (
                entry
                for entry in stream_entries
                if entry[1].get("event_id") == str(outbox_row.event_id)
                and entry[1].get("event_type") == "report.verification_changed"
            ),
            None,
        )
        assert matching_entry is not None

        sse_redis = MagicMock(spec=AsyncRedisClient)
        sse_redis.connect = AsyncMock()
        sse_redis.close = AsyncMock()
        sse_redis.xrange = AsyncMock(side_effect=[[('0-0', {})], [matching_entry]])
        sse_redis.xread = AsyncMock(side_effect=ConnectionError("End SSE test stream"))
        app.dependency_overrides[get_redis_client] = lambda: sse_redis
        try:
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://testserver"
            ) as sse_client:
                async with sse_client.stream(
                    "GET", "/api/v1/events/stream", headers={"Last-Event-ID": "0-0"}
                ) as sse_response:
                    assert sse_response.status_code == 200
                    sse_lines = [line async for line in sse_response.aiter_lines()]
            assert f"id: {matching_entry[0]}" in sse_lines
            assert "event: report.verification_changed" in sse_lines
        finally:
            app.dependency_overrides.pop(get_redis_client, None)
            await broadcaster.stop()

        res_logs = await api_client.get("/api/v1/admin/audit-logs?action=VERIFY")
        assert res_logs.status_code == 200
        logs_data = res_logs.json()
        assert logs_data["success"] is True
        assert len(logs_data["data"]) >= 2
        first_log = logs_data["data"][0]
        assert first_log["action"] == "VERIFY"
        assert first_log["user_email"] is not None

    async def test_single_and_bulk_verify_parity(
        self, api_client: AsyncClient, db_session: AsyncSession
    ):
        from app.services.report_service import report_service

        source = await report_service.get_or_create_source(db_session, source_code="CITIZEN")
        occurred_at = datetime(2026, 9, 30, 12, 0, tzinfo=timezone.utc)

        def make_report(tracking_id: str) -> WeatherReport:
            return WeatherReport(
                id=uuid.uuid4(),
                tracking_id=tracking_id,
                source_id=source.id,
                title="Parity verification incident",
                description="Matching data for single and bulk verification.",
                reported_category="FLOOD_WATERLOGGING",
                severity="HIGH",
                verification_status="PENDING",
                processing_status="PENDING",
                latitude=19.0760,
                longitude=72.8777,
                location_name="Mumbai, Maharashtra",
                geom="SRID=4326;POINT(72.8777 19.0760)",
                occurred_at=occurred_at,
                is_demo=False,
            )

        single_report = make_report(f"K1-SINGLE-{uuid.uuid4().hex[:8]}")
        bulk_report = make_report(f"K1-BULK-{uuid.uuid4().hex[:8]}")
        db_session.add_all([single_report, bulk_report])
        await db_session.commit()

        single_response = await api_client.post(
            f"/api/v1/verification/{single_report.id}/verify",
            json={"notes": "K1 parity"},
        )
        bulk_response = await api_client.post(
            "/api/v1/admin/verification/bulk",
            json={
                "incident_ids": [str(bulk_report.id)],
                "action": "VERIFY",
                "notes": "K1 parity",
            },
        )
        assert single_response.status_code == 200
        assert bulk_response.status_code == 200

        report_ids = [single_report.id, bulk_report.id]
        tracking_ids = {single_report.tracking_id, bulk_report.tracking_id}
        string_ids = {str(report_id) for report_id in report_ids}

        def normalize(value):
            if isinstance(value, (uuid.UUID, datetime)):
                return "<id-or-timestamp>"
            if isinstance(value, str) and value in string_ids | tracking_ids:
                return "<id-or-tracking-id>"
            if isinstance(value, dict):
                return {key: normalize(item) for key, item in value.items()}
            if isinstance(value, list):
                return [normalize(item) for item in value]
            return value

        def columns(row, excluded):
            return {
                attribute.key: normalize(getattr(row, attribute.key))
                for attribute in inspect(type(row)).column_attrs
                if attribute.key not in excluded
            }

        single_db_report = await db_session.get(WeatherReport, single_report.id)
        bulk_db_report = await db_session.get(WeatherReport, bulk_report.id)
        assert single_db_report is not None and bulk_db_report is not None
        single_events = list(
            (
                await db_session.scalars(
                    select(VerificationEvent).where(
                        VerificationEvent.report_id == single_report.id
                    )
                )
            ).all()
        )
        bulk_events = list(
            (
                await db_session.scalars(
                    select(VerificationEvent).where(VerificationEvent.report_id == bulk_report.id)
                )
            ).all()
        )
        outbox_rows = list(
            (
                await db_session.scalars(
                    select(RealtimeOutbox).where(
                        RealtimeOutbox.entity_id.in_(string_ids),
                        RealtimeOutbox.event_type == "report.verification_changed",
                    )
                )
            ).all()
        )
        single_outbox_rows = [row for row in outbox_rows if row.entity_id == str(single_report.id)]
        bulk_outbox_rows = [row for row in outbox_rows if row.entity_id == str(bulk_report.id)]
        assert len(single_outbox_rows) == len(bulk_outbox_rows) == 1
        assert single_outbox_rows[0].event_type == bulk_outbox_rows[0].event_type
        assert set(single_outbox_rows[0].payload) == set(bulk_outbox_rows[0].payload)
        print(
            "OUTBOX_PARITY",
            single_outbox_rows[0].event_type,
            sorted(single_outbox_rows[0].payload),
        )
        audit_rows = list(
            (
                await db_session.scalars(
                    select(AuditLog).where(AuditLog.entity_id.in_(report_ids))
                )
            ).all()
        )
        sections = {
            "incident": (
                columns(single_db_report, {"id", "tracking_id", "created_at", "updated_at"}),
                columns(bulk_db_report, {"id", "tracking_id", "created_at", "updated_at"}),
            ),
            "verification_events": (
                [columns(row, {"id", "report_id", "created_at"}) for row in single_events],
                [columns(row, {"id", "report_id", "created_at"}) for row in bulk_events],
            ),
            "realtime_outbox": (
                [columns(row, {"id", "event_id", "entity_id", "tracking_id", "occurred_at", "created_at"}) for row in outbox_rows if row.entity_id == str(single_report.id)],
                [columns(row, {"id", "event_id", "entity_id", "tracking_id", "occurred_at", "created_at"}) for row in outbox_rows if row.entity_id == str(bulk_report.id)],
            ),
            "audit_logs": (
                [columns(row, {"id", "entity_id", "created_at"}) for row in audit_rows if row.entity_id == single_report.id],
                [columns(row, {"id", "entity_id", "created_at"}) for row in audit_rows if row.entity_id == bulk_report.id],
            ),
        }
        differences = {
            section: {"single": single_value, "bulk": bulk_value}
            for section, (single_value, bulk_value) in sections.items()
            if single_value != bulk_value
        }
        print("PARITY_DIFF", json.dumps(differences, sort_keys=True, default=str))
        assert differences == {}
        assert len(single_events) == len(bulk_events) == 1
        assert len([row for row in outbox_rows if row.entity_id in string_ids]) == 2
        assert len(audit_rows) == 2

    async def test_bulk_invalid_id_changes_zero_of_four_record_groups(
        self, api_client: AsyncClient, db_session: AsyncSession
    ):
        from app.services.report_service import report_service

        source = await report_service.get_or_create_source(db_session, source_code="CITIZEN")
        report = WeatherReport(
            id=uuid.uuid4(),
            tracking_id=f"K1-ATOMIC-{uuid.uuid4().hex[:8]}",
            source_id=source.id,
            title="K1 invalid batch atomicity incident",
            reported_category="FLOOD_WATERLOGGING",
            severity="HIGH",
            verification_status="PENDING",
            processing_status="PENDING",
            latitude=19.0760,
            longitude=72.8777,
            geom="SRID=4326;POINT(72.8777 19.0760)",
            occurred_at=datetime.now(timezone.utc),
            is_demo=False,
        )
        db_session.add(report)
        await db_session.commit()

        response = await api_client.post(
            "/api/v1/admin/verification/bulk",
            json={"incident_ids": [str(report.id), str(uuid.uuid4())], "action": "VERIFY"},
        )
        assert response.status_code == 400
        await db_session.refresh(report)
        changed_incidents = int(
            report.verification_status != "PENDING" or report.processing_status != "PENDING"
        )
        verification_events = await db_session.scalar(
            select(func.count()).select_from(VerificationEvent).where(
                VerificationEvent.report_id == report.id
            )
        )
        outbox_rows = await db_session.scalar(
            select(func.count()).select_from(RealtimeOutbox).where(
                RealtimeOutbox.entity_id == str(report.id),
                RealtimeOutbox.event_type == "report.verification_changed",
            )
        )
        audit_rows = await db_session.scalar(
            select(func.count()).select_from(AuditLog).where(AuditLog.entity_id == report.id)
        )
        print(
            "ATOMIC_COUNTS",
            f"changed_incidents={changed_incidents}",
            f"verification_events={verification_events}",
            f"realtime_outbox={outbox_rows}",
            f"audit_logs={audit_rows}",
        )
        assert changed_incidents == 0
        assert verification_events == 0
        assert outbox_rows == 0
        assert audit_rows == 0

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
