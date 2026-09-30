"""Physical weather corroboration service.

Integrates with observation caching, providers, evaluator logic,
and PostgreSQL persistence with idempotent deduplication and outbox staging.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.intelligence.physical_corroboration.config import (
    PhysicalCorroborationConfig,
    default_physical_config,
)
from app.intelligence.physical_corroboration.evaluator import evaluate
from app.intelligence.physical_corroboration.models import (
    PhysicalCorroborationResult,
    PhysicalCorroborationVerdict,
    PhysicalObservation,
    PhysicalSourceType,
    ProviderStatus,
)
from app.intelligence.physical_corroboration.providers.base import BaseWeatherProvider
from app.intelligence.physical_corroboration.providers.cache import SingleFlightGridHourCache
from app.intelligence.physical_corroboration.providers.open_meteo import OpenMeteoProvider
from app.models.corroboration import IncidentPhysicalCorroboration
from app.models.outbox import RealtimeOutbox
from app.models.report import WeatherReport

logger = logging.getLogger(__name__)


class PhysicalCorroborationService:
    """Orchestrates physical weather corroboration, provider fetches, and persistence."""

    def __init__(
        self,
        provider: Optional[BaseWeatherProvider] = None,
        cache: Optional[SingleFlightGridHourCache] = None,
        config: Optional[PhysicalCorroborationConfig] = None,
    ) -> None:
        if provider:
            self.provider = provider
        elif getattr(settings, "PHYSICAL_CORROBORATION_DEMO_FIXTURE_ENABLED", False):
            from app.intelligence.physical_corroboration.providers.fixture_provider import (
                FixtureWeatherProvider,
            )

            self.provider = FixtureWeatherProvider()
        else:
            self.provider = OpenMeteoProvider()

        self.cache = cache or SingleFlightGridHourCache(ttl_seconds=3600)
        self.config = config or default_physical_config

    async def corroborate_incident(
        self,
        db: AsyncSession,
        report: WeatherReport,
        force_run: bool = False,
    ) -> Optional[IncidentPhysicalCorroboration]:
        """Corroborate an incident against physical weather data with idempotent persistence.

        Guarantees:
        - Gated behind PHYSICAL_CORROBORATION_ENABLED (Product Rule P8)
        - Kill switch stops all processing instantly
        - Failures fallback to NEUTRAL (Product Rule P2)
        - Idempotent: re-running for same report/observation updates without duplicates
        """
        # Feature flag and kill switch check
        if not force_run:
            if getattr(settings, "PHYSICAL_CORROBORATION_KILL_SWITCH", False):
                logger.info("Physical corroboration killed via PHYSICAL_CORROBORATION_KILL_SWITCH.")
                return None
            if not getattr(settings, "PHYSICAL_CORROBORATION_ENABLED", False):
                logger.debug("Physical corroboration disabled via PHYSICAL_CORROBORATION_ENABLED.")
                return None

        if report.latitude is None or report.longitude is None:
            logger.warning("Report %s lacks coordinates; cannot corroborate physically.", report.id)
            return None

        category = report.reported_category or "OTHER"
        lat = float(report.latitude)
        lon = float(report.longitude)
        incident_time = report.occurred_at
        if incident_time.tzinfo is None:
            incident_time = incident_time.replace(tzinfo=timezone.utc)

        # 1. Fetch observation via single-flight cache
        async def _fetch():
            return await self.provider.fetch_observation(
                lat=lat,
                lon=lon,
                target_time=incident_time,
                category=category,
            )

        obs, provider_status, err_msg, _ = await self.cache.get_or_fetch(
            lat=lat,
            lon=lon,
            target_time=incident_time,
            fetch_coroutine_fn=_fetch,
        )

        # 2. Evaluate corroboration logic
        eval_result: PhysicalCorroborationResult = evaluate(
            category=category,
            observation=obs,
            incident_time=incident_time,
            incident_coords=(lat, lon),
            config=self.config,
        )

        # Override provider status if the provider explicitly failed
        if provider_status != ProviderStatus.OK:
            eval_result.provider_status = provider_status
            if err_msg and not eval_result.explanation:
                eval_result.explanation = f"Provider {provider_status.value}: {err_msg}"

        # 3. Idempotent persistence (Upsert semantics)
        obs_time = obs.observed_at if obs else incident_time
        if obs_time.tzinfo is None:
            obs_time = obs_time.replace(tzinfo=timezone.utc)

        var_name = eval_result.variable or "unknown"
        src_name = eval_result.source or self.provider.name

        # Query existing row for (incident_id, variable, source, observation_time)
        stmt = (
            select(IncidentPhysicalCorroboration)
            .where(
                IncidentPhysicalCorroboration.incident_id == report.id,
                IncidentPhysicalCorroboration.variable == var_name,
                IncidentPhysicalCorroboration.source == src_name,
                IncidentPhysicalCorroboration.observation_time == obs_time,
            )
            .limit(1)
        )
        existing_res = await db.execute(stmt)
        record = existing_res.scalar_one_or_none()

        if record is None:
            record = IncidentPhysicalCorroboration(
                id=uuid.uuid4(),
                incident_id=report.id,
                variable=var_name,
                observed_value=eval_result.observed_value,
                unit=eval_result.unit,
                source=src_name,
                source_type=eval_result.source_type.value,
                station_or_grid_id=eval_result.station_or_grid_id,
                distance_km=eval_result.distance_km,
                time_gap_h=eval_result.time_gap_hours,
                verdict=eval_result.verdict.value,
                weight=eval_result.weight,
                contribution=eval_result.contribution,
                provider_status=eval_result.provider_status.value,
                observation_time=obs_time,
                computed_at=datetime.now(timezone.utc),
                explanation=eval_result.explanation,
                is_simulated=obs.is_simulated if obs else False,
            )
            db.add(record)
        else:
            # Update existing row
            record.observed_value = eval_result.observed_value
            record.unit = eval_result.unit
            record.source_type = eval_result.source_type.value
            record.station_or_grid_id = eval_result.station_or_grid_id
            record.distance_km = eval_result.distance_km
            record.time_gap_h = eval_result.time_gap_hours
            record.verdict = eval_result.verdict.value
            record.weight = eval_result.weight
            record.contribution = eval_result.contribution
            record.provider_status = eval_result.provider_status.value
            record.computed_at = datetime.now(timezone.utc)
            record.explanation = eval_result.explanation
            record.is_simulated = obs.is_simulated if obs else False

        await db.flush()
        return record

    def stage_corroboration_event(
        self,
        db: AsyncSession,
        report: WeatherReport,
        record: IncidentPhysicalCorroboration,
    ) -> RealtimeOutbox:
        """Stage an outbox event for frontend SSE streaming and reactivity."""
        payload: Dict[str, Any] = {
            "incident_id": str(report.id),
            "tracking_id": report.tracking_id,
            "verdict": record.verdict,
            "variable": record.variable,
            "observed_value": record.observed_value,
            "unit": record.unit,
            "source": record.source,
            "source_type": record.source_type,
            "provider_status": record.provider_status,
            "contribution": record.contribution,
            "is_simulated": record.is_simulated,
        }

        outbox = RealtimeOutbox(
            event_id=uuid.uuid4(),
            event_type="incident.physical_corroboration_completed",
            entity_id=str(report.id),
            tracking_id=report.tracking_id,
            occurred_at=datetime.now(timezone.utc),
            payload=payload,
            status="PENDING",
            attempts=0,
            max_attempts=5,
        )
        db.add(outbox)
        return outbox


physical_corroboration_service = PhysicalCorroborationService()
