import logging
from typing import Optional

from geoalchemy2.shape import from_shape
from shapely.geometry import Point
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ingestion.schemas import NormalizedObservationEvent
from app.models.observation import WeatherObservation
from app.models.outbox import RealtimeOutbox
from app.models.source import Source
from app.services.realtime_service import RealtimeService, realtime_service

logger = logging.getLogger(__name__)


class ObservationService:
    """Service handling persistence, idempotency, and retrieval of physical sensor observations."""

    def __init__(self, realtime_svc: Optional[RealtimeService] = None) -> None:
        self.realtime_svc = realtime_svc or realtime_service

    async def get_or_create_source(
        self,
        session: AsyncSession,
        source_code: str = "CWC_NWDP",
        name: Optional[str] = None,
        source_type: Optional[str] = None,
        base_trust_score: Optional[float] = None,
    ) -> Source:
        """Fetch existing observation source or register a new one idempotently."""
        normalized_code = source_code.strip().upper()
        stmt = select(Source).where(Source.source_code == normalized_code)
        result = await session.execute(stmt)
        source = result.scalar_one_or_none()

        if source is not None:
            if base_trust_score is not None:
                source.base_trust_score = base_trust_score
            else:
                from app.ingestion.registry import adapter_registry

                registered = adapter_registry.get(normalized_code)
                if registered:
                    source.base_trust_score = registered.base_trust_score
            return source

        resolved_trust = base_trust_score
        resolved_name = name
        resolved_type = source_type or "GOV_OPEN_DATA"

        from app.ingestion.registry import adapter_registry

        registered = adapter_registry.get(normalized_code)
        if registered:
            if resolved_trust is None:
                resolved_trust = registered.base_trust_score
            if not resolved_name:
                resolved_name = registered.source_name
            resolved_type = registered.source_type

        source = Source(
            source_code=normalized_code,
            name=resolved_name or f"Observation Source {normalized_code}",
            source_type=resolved_type,
            base_trust_score=resolved_trust if resolved_trust is not None else 0.92,
            is_active=True,
        )
        session.add(source)
        await session.flush()
        logger.info(f"Registered observation source: {normalized_code} (trust: {source.base_trust_score})")

        return source

    async def ingest_normalized_observation(
        self,
        session: AsyncSession,
        event: NormalizedObservationEvent,
        stage_outbox: bool = True,
    ) -> WeatherObservation:
        """Persist or update a normalized observation idempotently via (source_id, external_id)."""
        source = await self.get_or_create_source(
            session=session,
            source_code=event.source_code,
        )

        existing: Optional[WeatherObservation] = None
        if event.external_id:
            stmt = select(WeatherObservation).where(
                WeatherObservation.source_id == source.id,
                WeatherObservation.external_id == event.external_id,
            )
            result = await session.execute(stmt)
            existing = result.scalar_one_or_none()

        if not existing:
            # Secondary check on (source_id, station_code, observed_at)
            stmt = select(WeatherObservation).where(
                WeatherObservation.source_id == source.id,
                WeatherObservation.station_code == event.station_code,
                WeatherObservation.observed_at == event.observed_at,
            )
            result = await session.execute(stmt)
            existing = result.scalar_one_or_none()

        point_geom = from_shape(Point(event.longitude, event.latitude), srid=4326)
        orch_outbox_row: Optional[RealtimeOutbox] = None

        if existing:
            existing.station_name = event.station_name
            existing.geom = point_geom
            existing.water_level_m = event.water_level_m
            existing.rainfall_mm = event.rainfall_mm
            existing.temperature_c = event.temperature_c
            existing.humidity_pct = event.humidity_pct
            existing.wind_speed_kmh = event.wind_speed_kmh
            existing.wind_direction_deg = event.wind_direction_deg
            existing.pressure_hpa = event.pressure_hpa
            existing.raw_metrics = event.raw_metrics

            if stage_outbox:
                orch_outbox_row = self.realtime_svc.stage_observation_orchestration_trigger(
                    session=session,
                    observation=existing,
                )

            await session.commit()
            await session.refresh(existing)

            if orch_outbox_row is not None:
                await self.realtime_svc.publish_staged_outbox(orch_outbox_row)

            logger.debug(
                f"Updated existing observation '{existing.station_code}' ({existing.external_id})"
            )
            return existing

        observation = WeatherObservation(
            source_id=source.id,
            external_id=event.external_id,
            station_code=event.station_code,
            station_name=event.station_name,
            geom=point_geom,
            observed_at=event.observed_at,
            water_level_m=event.water_level_m,
            rainfall_mm=event.rainfall_mm,
            temperature_c=event.temperature_c,
            humidity_pct=event.humidity_pct,
            wind_speed_kmh=event.wind_speed_kmh,
            wind_direction_deg=event.wind_direction_deg,
            pressure_hpa=event.pressure_hpa,
            raw_metrics=event.raw_metrics,
        )
        session.add(observation)
        await session.flush()

        if stage_outbox:
            orch_outbox_row = self.realtime_svc.stage_observation_orchestration_trigger(
                session=session,
                observation=observation,
            )

        await session.commit()
        await session.refresh(observation)

        if orch_outbox_row is not None:
            await self.realtime_svc.publish_staged_outbox(orch_outbox_row)

        logger.info(
            f"Persisted new observation '{observation.station_code}' "
            f"@ {observation.observed_at} ({observation.external_id})"
        )
        return observation


observation_service = ObservationService()
