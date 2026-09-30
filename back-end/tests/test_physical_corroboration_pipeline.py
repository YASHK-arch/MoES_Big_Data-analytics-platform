"""Tests for physical weather corroboration pipeline integration, idempotency, and recovery."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.intelligence.physical_corroboration.models import (
    PhysicalCorroborationVerdict,
    PhysicalObservation,
    PhysicalSourceType,
    ProviderStatus,
)
from app.intelligence.physical_corroboration.providers.base import BaseWeatherProvider
from app.intelligence.physical_corroboration.service import PhysicalCorroborationService
from app.models.corroboration import IncidentPhysicalCorroboration
from app.models.report import WeatherReport
from app.models.source import Source


class MockWeatherProvider(BaseWeatherProvider):
    """Mock provider with controllable outcomes."""

    def __init__(self, observation=None, status=ProviderStatus.OK, error=None, name="OPEN_METEO"):
        super().__init__(name=name, source_type=PhysicalSourceType.MODEL)
        self.mock_observation = observation
        self.mock_status = status
        self.mock_error = error

    async def _execute_fetch(self, lat, lon, target_time, category):
        return self.mock_observation, self.mock_status, self.mock_error


@pytest.mark.asyncio
class TestPhysicalCorroborationPipelineIntegration:
    """Tests for worker/pipeline integration, idempotency, and outage recovery."""

    async def _create_test_report(self, db: AsyncSession) -> WeatherReport:
        src_stmt = select(Source).limit(1)
        res = await db.execute(src_stmt)
        source = res.scalar_one_or_none()
        if not source:
            source = Source(
                id=uuid.uuid4(),
                code="CITIZEN_APP",
                name="Citizen Portal",
                source_type="CITIZEN",
                base_trust_score=0.5,
            )
            db.add(source)
            await db.flush()

        occurred = datetime(2026, 7, 15, 14, 0, tzinfo=timezone.utc)
        report = WeatherReport(
            id=uuid.uuid4(),
            tracking_id=f"TEST-{uuid.uuid4().hex[:8].upper()}",
            source_id=source.id,
            reported_category="HEAVY_RAINFALL",
            severity="SEVERE",
            title="Heavy downpour in Indiranagar",
            description="Continuous heavy rain flooding roads.",
            latitude=12.9716,
            longitude=77.5946,
            geom=func.ST_SetSRID(func.ST_MakePoint(77.5946, 12.9716), 4326),
            occurred_at=occurred,
            verification_status="PENDING",
            processing_status="PROCESSING",
        )
        db.add(report)
        await db.flush()
        return report

    async def test_idempotent_replay_no_duplicates(self, db_session: AsyncSession) -> None:
        """Test that replaying corroboration multiple times creates no duplicate rows."""
        report = await self._create_test_report(db_session)
        target_time = report.occurred_at

        sample_obs = PhysicalObservation(
            source_name="OPEN_METEO",
            source_type=PhysicalSourceType.MODEL,
            station_or_grid_id="OM_GRID_12.97_77.59",
            latitude=12.97,
            longitude=77.59,
            observed_at=target_time,
            rainfall_1h_mm=70.0,
        )

        provider = MockWeatherProvider(observation=sample_obs, status=ProviderStatus.OK)
        service = PhysicalCorroborationService(provider=provider)

        # Run 1: Initial creation
        rec1 = await service.corroborate_incident(db_session, report, force_run=True)
        assert rec1 is not None
        assert rec1.verdict == PhysicalCorroborationVerdict.SUPPORTS.value

        # Run 2: Idempotent replay
        rec2 = await service.corroborate_incident(db_session, report, force_run=True)
        assert rec2 is not None
        assert rec2.id == rec1.id  # Same record updated

        # Run 3: Another replay
        rec3 = await service.corroborate_incident(db_session, report, force_run=True)
        assert rec3 is not None
        assert rec3.id == rec1.id

        # Verify exactly 1 row exists in DB for this incident
        stmt = select(func.count(IncidentPhysicalCorroboration.id)).where(
            IncidentPhysicalCorroboration.incident_id == report.id
        )
        count_res = await db_session.execute(stmt)
        total_rows = count_res.scalar()
        assert total_rows == 1

    async def test_provider_outage_yields_neutral_and_later_recovery_recomputes(
        self, db_session: AsyncSession
    ) -> None:
        """Test provider outage yields NEUTRAL and subsequent recovery updates row."""
        report = await self._create_test_report(db_session)
        target_time = report.occurred_at

        # Phase 1: Provider outage (Timeout)
        failing_provider = MockWeatherProvider(
            observation=None,
            status=ProviderStatus.TIMEOUT,
            error="Connection timed out after 5.0s",
        )
        service = PhysicalCorroborationService(provider=failing_provider)

        outage_rec = await service.corroborate_incident(db_session, report, force_run=True)
        assert outage_rec is not None
        assert outage_rec.verdict == PhysicalCorroborationVerdict.NEUTRAL.value
        assert outage_rec.provider_status == ProviderStatus.TIMEOUT.value
        assert outage_rec.contribution == 0.0

        # Phase 2: Provider recovers and serves valid heavy rain observation
        recovered_obs = PhysicalObservation(
            source_name="OPEN_METEO",
            source_type=PhysicalSourceType.MODEL,
            station_or_grid_id="OM_GRID_12.97_77.59",
            latitude=12.97,
            longitude=77.59,
            observed_at=target_time,
            rainfall_1h_mm=85.0,
        )
        healthy_provider = MockWeatherProvider(
            observation=recovered_obs,
            status=ProviderStatus.OK,
        )
        recovered_service = PhysicalCorroborationService(provider=healthy_provider)

        recovered_rec = await recovered_service.corroborate_incident(
            db_session, report, force_run=True
        )
        assert recovered_rec is not None
        assert recovered_rec.id == outage_rec.id  # Same record mutated
        assert recovered_rec.verdict == PhysicalCorroborationVerdict.SUPPORTS.value
        assert recovered_rec.provider_status == ProviderStatus.OK.value
        assert recovered_rec.contribution > 0.0

        # Outbox event staged
        outbox = recovered_service.stage_corroboration_event(db_session, report, recovered_rec)
        assert outbox is not None
        assert outbox.event_type == "incident.physical_corroboration_completed"
        assert outbox.payload["verdict"] == PhysicalCorroborationVerdict.SUPPORTS.value

    async def test_at_least_once_redelivery_is_safe(self, db_session: AsyncSession) -> None:
        """Test at-least-once redelivery of corroboration results is idempotent and safe."""
        report = await self._create_test_report(db_session)
        target_time = report.occurred_at

        sample_obs = PhysicalObservation(
            source_name="OPEN_METEO",
            source_type=PhysicalSourceType.MODEL,
            station_or_grid_id="OM_GRID_12.97_77.59",
            latitude=12.97,
            longitude=77.59,
            observed_at=target_time,
            rainfall_1h_mm=40.0,
        )

        provider = MockWeatherProvider(observation=sample_obs, status=ProviderStatus.OK)
        service = PhysicalCorroborationService(provider=provider)

        # Redeliver 5 times in succession
        for _ in range(5):
            rec = await service.corroborate_incident(db_session, report, force_run=True)
            assert rec is not None

        # Verify only 1 row exists
        stmt = select(func.count(IncidentPhysicalCorroboration.id)).where(
            IncidentPhysicalCorroboration.incident_id == report.id
        )
        count_res = await db_session.execute(stmt)
        assert count_res.scalar() == 1
