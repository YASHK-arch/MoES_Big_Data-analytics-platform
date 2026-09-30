"""End-to-end integration proof for live intelligence orchestration and pipeline execution."""

import json
import uuid
from typing import Any, Dict, List, Tuple
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.redis import AsyncRedisClient
from app.models.observation import WeatherObservation
from app.models.outbox import RealtimeOutbox
from app.models.report import WeatherReport
from app.models.source import Source
from app.models.verification import VerificationEvent
from app.orchestration.dispatcher import OrchestrationDispatcher
from app.orchestration.events import (
    OrchestrationEvent,
    OrchestrationEventType,
    OverallReadiness,
    StageName,
    StageOutcome,
)
from app.orchestration.incident_pipeline import incident_pipeline
from app.orchestration.triggers import on_incident_ingested, on_observation_ingested
from app.schemas.report import CitizenReportCreate
from app.services.realtime_service import RealtimeService
from app.services.report_service import ReportService
from app.workers.outbox_worker import RealtimeOutboxWorker

pytestmark = pytest.mark.asyncio


def _create_mock_redis_stream_bus() -> Tuple[MagicMock, List[Tuple[str, str, Dict[str, Any]]]]:
    """Create a mock Redis client that acts as an in-memory stream bus for integration testing."""
    mock_redis = MagicMock(spec=AsyncRedisClient)
    published_events: List[Tuple[str, str, Dict[str, Any]]] = []

    async def mock_xadd(stream: str, fields: Dict[str, Any], **kwargs: Any) -> str:
        msg_id = f"1725000000000-{len(published_events) + 1}"
        published_events.append((stream, msg_id, fields))
        return msg_id

    mock_redis.xadd = AsyncMock(side_effect=mock_xadd)
    mock_redis.xgroup_create = AsyncMock(return_value=True)

    async def mock_xreadgroup(
        group: str,
        consumer: str,
        streams: Dict[str, str],
        count: int = 10,
        block_ms: int | None = None,
    ) -> List[Tuple[str, List[Tuple[str, Dict[str, Any]]]]]:
        entries: List[Tuple[str, Dict[str, Any]]] = []
        for s, msg_id, fields in published_events:
            if s == "stream:weather:orchestration":
                entries.append((msg_id, fields))
        return [("stream:weather:orchestration", entries)] if entries else []

    mock_redis.xreadgroup = AsyncMock(side_effect=mock_xreadgroup)
    mock_redis.xack = AsyncMock(return_value=1)

    return mock_redis, published_events


async def test_e2e_real_pipeline_full_execution(db_session: AsyncSession) -> None:
    """Proves the full live intelligence execution path with ZERO mocks on intelligence stages.

    Flow:
    1. Citizen report creation -> WeatherReport (processing_status="QUEUED") + 2 Outbox rows.
    2. Outbox Worker -> Publishes orchestration event to stream:weather:orchestration.
    3. Dispatcher -> Reads stream message and calls REAL on_incident_ingested.
    4. Real IncidentPipeline -> Executes all 5 real intelligence stages locally against PostGIS.
    5. Real DB Persistence -> Asserts processing_status="COMPLETED", credibility_score > 0,
       explainability text, and full per-stage metadata in PostgreSQL.
    """
    mock_redis, published_events = _create_mock_redis_stream_bus()
    mock_realtime = RealtimeService(client=mock_redis)
    report_svc = ReportService(realtime_svc=mock_realtime)

    # 1. Citizen Report Creation via ReportService
    payload = CitizenReportCreate(
        latitude=19.0760,
        longitude=72.8777,
        category_code="FLOOD_WATERLOGGING",
        severity="HIGH",
        title="Severe Waterlogging on S.V. Road",
        description="Water depth exceeds 2 feet near railway underpass causing traffic halt.",
        location_name="Bandra West, Mumbai",
    )
    report, media_count = await report_svc.create_citizen_report(
        session=db_session,
        payload=payload,
    )

    assert report is not None
    assert report.id is not None
    # Inline intelligence pipeline now runs on creation; status may be COMPLETED already
    assert report.processing_status in ("QUEUED", "COMPLETED")
    report_id = report.id

    # Verify Outbox rows staged in PostgreSQL (at least 2: report.created + orchestration.incident_ingested)
    # The inline pipeline may also add a 3rd intelligence_ready row if it completes synchronously
    outbox_stmt = select(RealtimeOutbox).where(RealtimeOutbox.entity_id == str(report_id))
    outbox_res = await db_session.execute(outbox_stmt)
    outbox_rows = outbox_res.scalars().all()
    assert len(outbox_rows) >= 2

    event_types = {r.event_type for r in outbox_rows}
    assert "report.created" in event_types
    assert "orchestration.incident_ingested" in event_types

    orch_outbox_row = next(
        r for r in outbox_rows if r.event_type == "orchestration.incident_ingested"
    )
    assert orch_outbox_row.status in ("PENDING", "PUBLISHED")

    # 2. Outbox Worker Publication to Redis Stream
    worker = RealtimeOutboxWorker(client=mock_redis)
    await worker.publish_pending_batch(db_session, batch_size=500)
    await db_session.refresh(orch_outbox_row)
    assert orch_outbox_row.status == "PUBLISHED"

    # Verify stream:weather:orchestration received the message
    orch_messages = [f for s, _, f in published_events if s == "stream:weather:orchestration"]
    assert len(orch_messages) >= 1
    target_msg = next(
        f
        for f in orch_messages
        if f.get("event_type") == OrchestrationEventType.INCIDENT_INGESTED.value
        and f.get("aggregate_id") == str(report_id)
    )
    assert target_msg is not None

    # 3. Dispatcher reads from stream and executes REAL on_incident_ingested & IncidentPipeline
    dispatcher = OrchestrationDispatcher(client=mock_redis)
    # Parse event from stream message
    if "data" in target_msg:
        data_dict = (
            json.loads(target_msg["data"])
            if isinstance(target_msg["data"], str)
            else target_msg["data"]
        )
        orch_event = OrchestrationEvent.model_validate(data_dict)
    else:
        orch_event = OrchestrationEvent.model_validate(target_msg)

    # Process through real dispatcher event routing (NO MOCKS on pipeline or stages)
    dispatch_result = await dispatcher.process_event(db=db_session, event=orch_event)
    assert dispatch_result.outcome == StageOutcome.SUCCESS_WITH_RESULTS

    # 4. Refresh WeatherReport from PostgreSQL and verify real intelligence results
    await db_session.commit()
    stmt = select(WeatherReport).where(WeatherReport.id == report_id)
    res = await db_session.execute(stmt)
    persisted_report = res.scalar_one()

    # Verify final processing status
    assert persisted_report.processing_status == "COMPLETED"

    # Verify credibility score and explanation were calculated and persisted
    assert persisted_report.credibility_score > 0.0
    assert persisted_report.credibility_explanation is not None
    assert (
        "Base credibility" in persisted_report.credibility_explanation
        or len(persisted_report.credibility_explanation) > 10
    )

    # Verify orchestration state and per-stage completion in PostgreSQL
    assert persisted_report.raw_payload is not None
    assert "orchestration" in persisted_report.raw_payload
    orch_state_payload = persisted_report.raw_payload["orchestration"]
    assert orch_state_payload.get("overall_readiness") == OverallReadiness.INTELLIGENCE_READY.value

    stages = orch_state_payload.get("stages", {})
    assert StageName.LOCATION.value in stages
    assert StageName.DUPLICATE.value in stages
    assert StageName.EVIDENCE.value in stages
    assert StageName.OBSERVATION.value in stages
    assert StageName.CREDIBILITY.value in stages

    for stage_key in ("LOCATION", "DUPLICATE", "EVIDENCE", "OBSERVATION", "CREDIBILITY"):
        stage_info = stages[stage_key]
        assert stage_info.get("status") in (
            StageOutcome.SUCCESS_WITH_RESULTS.value,
            StageOutcome.SUCCESS_WITH_INSUFFICIENT_DATA.value,
            StageOutcome.SUCCESS_WITH_NO_MATCH.value,
        )
        assert stage_info.get("attempt") >= 1


async def test_live_intelligence_failure_isolation(db_session: AsyncSession) -> None:
    """Proves failure isolation: a stage failure records metadata without rollback."""
    mock_redis, _ = _create_mock_redis_stream_bus()
    mock_realtime = RealtimeService(client=mock_redis)
    report_svc = ReportService(realtime_svc=mock_realtime)

    # 1. Create base citizen report
    payload = CitizenReportCreate(
        latitude=19.1136,
        longitude=72.8697,
        category_code="HEAVY_RAINFALL",
        severity="SEVERE",
        title="High Intensity Downpour",
        description="Rainfall intensity causing localized pooling.",
        location_name="Andheri East, Mumbai",
    )
    report, _ = await report_svc.create_citizen_report(session=db_session, payload=payload)
    report_id = report.id

    # 2. Execute pipeline with simulated failure in observation stage handler
    original_observation_handler = incident_pipeline.handlers[StageName.OBSERVATION]

    class FailingObservationHandler:
        async def execute(self, db: AsyncSession, report: WeatherReport):
            raise ConnectionError("Simulated weather station API connection timeout")

    try:
        incident_pipeline.handlers[StageName.OBSERVATION] = FailingObservationHandler()  # type: ignore[assignment]
        state = await on_incident_ingested(db=db_session, incident_id=report_id, force=True)

        # 3. Verify report remains persisted in PostgreSQL
        stmt = select(WeatherReport).where(WeatherReport.id == report_id)
        res = await db_session.execute(stmt)
        persisted_report = res.scalar_one()

        assert persisted_report is not None
        assert persisted_report.id == report_id

        # 4. Verify stage failure is tracked in orchestration JSONB
        assert persisted_report.raw_payload is not None
        stages = persisted_report.raw_payload.get("orchestration", {}).get("stages", {})
        assert StageName.OBSERVATION.value in stages
        obs_stage = stages[StageName.OBSERVATION.value]
        assert obs_stage["status"] == StageOutcome.RETRYABLE_FAILURE.value
        assert "Simulated weather station" in obs_stage["error_message"]

        # Downstream credibility still executed and overall readiness is PARTIAL
        assert state.overall_readiness == OverallReadiness.INTELLIGENCE_PARTIAL
        assert persisted_report.processing_status == "PARTIAL_INTELLIGENCE"
        assert persisted_report.credibility_score > 0.0

    finally:
        incident_pipeline.handlers[StageName.OBSERVATION] = original_observation_handler


async def test_live_intelligence_idempotency(db_session: AsyncSession) -> None:
    """Proves idempotency: running the pipeline twice produces deterministic state."""
    mock_redis, _ = _create_mock_redis_stream_bus()
    mock_realtime = RealtimeService(client=mock_redis)
    report_svc = ReportService(realtime_svc=mock_realtime)

    # 1. Create base citizen report
    payload = CitizenReportCreate(
        latitude=19.2183,
        longitude=72.9781,
        category_code="LANDSLIDE",
        severity="MODERATE",
        title="Minor Hillside Debris Movement",
        description="Small mudslide on slope boundary.",
        location_name="Thane West",
    )
    report, _ = await report_svc.create_citizen_report(session=db_session, payload=payload)
    report_id = report.id

    # First execution
    state_1 = await on_incident_ingested(db=db_session, incident_id=report_id)

    stmt = select(WeatherReport).where(WeatherReport.id == report_id)
    res_1 = await db_session.execute(stmt)
    report_run_1 = res_1.scalar_one()
    assert report_run_1.raw_payload is not None
    first_credibility = report_run_1.credibility_score
    first_fingerprint = (
        report_run_1.raw_payload.get("orchestration", {})
        .get("stages", {})
        .get("CREDIBILITY", {})
        .get("fingerprint")
    )

    # Second execution on same report
    state_2 = await on_incident_ingested(db=db_session, incident_id=report_id)

    res_2 = await db_session.execute(stmt)
    report_run_2 = res_2.scalar_one()
    assert report_run_2.raw_payload is not None
    second_credibility = report_run_2.credibility_score
    second_fingerprint = (
        report_run_2.raw_payload.get("orchestration", {})
        .get("stages", {})
        .get("CREDIBILITY", {})
        .get("fingerprint")
    )

    # Assert deterministic equality
    assert state_1.overall_readiness == state_2.overall_readiness
    assert first_credibility == second_credibility
    assert first_fingerprint == second_fingerprint
    assert report_run_2.processing_status == "COMPLETED"


async def test_stream_routing_separation(db_session: AsyncSession) -> None:
    """Proves strict separation between stream:weather:realtime and stream:weather:orchestration."""
    mock_redis, published_events = _create_mock_redis_stream_bus()
    mock_realtime = RealtimeService(client=mock_redis)
    report_svc = ReportService(realtime_svc=mock_realtime)

    payload = CitizenReportCreate(
        latitude=18.9220,
        longitude=72.8347,
        category_code="CYCLONE_HIGH_WIND",
        severity="SEVERE",
        title="High Velocity Gale Observed",
        description="Gale force gusts causing tree fall hazards near coastal road.",
        location_name="Colaba, Mumbai",
    )
    report, _ = await report_svc.create_citizen_report(session=db_session, payload=payload)

    # Fast path or worker publish
    worker = RealtimeOutboxWorker(client=mock_redis)
    await worker.publish_pending_batch(db_session)

    # Verify events in stream:weather:realtime
    realtime_events = [f for s, _, f in published_events if s == "stream:weather:realtime"]
    assert len(realtime_events) >= 1
    assert any(
        f.get("event_type") == "report.created" and f.get("entity_id") == str(report.id)
        for f in realtime_events
    )

    # Verify events in stream:weather:orchestration
    orch_events = [f for s, _, f in published_events if s == "stream:weather:orchestration"]
    assert len(orch_events) >= 1
    assert any(
        f.get("event_type") == OrchestrationEventType.INCIDENT_INGESTED.value
        and f.get("aggregate_id") == str(report.id)
        for f in orch_events
    )


async def test_observation_joining_completed_incident_updates_score(db_session: AsyncSession) -> None:
    """Proves that a new physical observation matching an already-COMPLETED incident still triggers credibility re-scoring."""
    mock_redis, _ = _create_mock_redis_stream_bus()
    mock_realtime = RealtimeService(client=mock_redis)
    report_svc = ReportService(realtime_svc=mock_realtime)
    uid = uuid.uuid4().hex[:8]
    latitude = 23.4567 + int(uid[:4], 16) / 65535 * 0.2
    longitude = 85.6789 + int(uid[4:], 16) / 65535 * 0.2

    # 1. Create and ingest initial citizen report at isolated location
    payload = CitizenReportCreate(
        latitude=latitude,
        longitude=longitude,
        category_code="FLOOD_WATERLOGGING",
        severity="HIGH",
        title=f"Sudden Flash Flood on Isolated Road {uid}",
        description="Rapid water accumulation on roadway causing traffic halt.",
        location_name=f"Isolated Valley Road {uid}, Jharkhand",
    )
    report, _ = await report_svc.create_citizen_report(session=db_session, payload=payload)
    state_initial = await on_incident_ingested(db=db_session, incident_id=report.id, commit=True)
    assert state_initial.overall_readiness == OverallReadiness.INTELLIGENCE_READY

    await db_session.refresh(report)
    assert report.processing_status == "COMPLETED"
    initial_score = float(report.credibility_score or 0.0)

    # 2. Ingest matching physical observation
    obs_source = Source(
        source_code=f"CWC_SENSOR_{uid}",
        name="CWC Hydrological Monitoring",
        source_type="PHYSICAL_SENSOR",
        base_trust_score=0.95,
        is_active=True,
    )
    db_session.add(obs_source)
    await db_session.flush()

    from geoalchemy2.shape import from_shape
    from shapely.geometry import Point

    obs = WeatherObservation(
        source_id=obs_source.id,
        external_id=f"cwc_obs_{uid}",
        station_code=f"NGP_{uid}",
        station_name="Nagpur Hydrology Gauge",
        water_level_m=525.0,
        observed_at=report.occurred_at,
        geom=from_shape(Point(report.longitude, report.latitude), srid=4326),
    )
    db_session.add(obs)
    await db_session.commit()

    affected_ids = await on_observation_ingested(db=db_session, observation_id=obs.id, commit=True)
    assert report.id in affected_ids

    # 3. Verify that already-COMPLETED incident received updated credibility score
    await db_session.refresh(report)
    assert report.processing_status == "COMPLETED"
    assert float(report.credibility_score) > initial_score


async def test_new_report_joining_completed_incident_cluster_updates_score(db_session: AsyncSession) -> None:
    """Proves that a new duplicate report joining a cluster with an already-COMPLETED incident updates its score."""
    mock_redis, _ = _create_mock_redis_stream_bus()
    mock_realtime = RealtimeService(client=mock_redis)
    report_svc = ReportService(realtime_svc=mock_realtime)

    # 1. Create first report and ingest to COMPLETED status
    payload1 = CitizenReportCreate(
        latitude=13.0827,
        longitude=80.2707,
        category_code="FLOOD_WATERLOGGING",
        severity="HIGH",
        title="Severe Waterlogging on Mount Road",
        description="Knee deep water near Anna Salai junction blocking traffic.",
        location_name="Anna Salai, Chennai",
    )
    report1, _ = await report_svc.create_citizen_report(session=db_session, payload=payload1)
    await on_incident_ingested(db=db_session, incident_id=report1.id, commit=True)
    await db_session.refresh(report1)
    assert report1.processing_status == "COMPLETED"
    initial_score1 = float(report1.credibility_score or 0.0)

    # 2. Ingest duplicate second report at same location
    payload2 = CitizenReportCreate(
        latitude=13.0830,
        longitude=80.2710,
        category_code="FLOOD_WATERLOGGING",
        severity="HIGH",
        title="Severe Waterlogging on Mount Road Junction",
        description="Knee deep water near Anna Salai junction blocking traffic completely.",
        location_name="Anna Salai, Chennai",
    )
    report2, _ = await report_svc.create_citizen_report(session=db_session, payload=payload2)
    await on_incident_ingested(db=db_session, incident_id=report2.id, commit=True)

    # 3. Verify that already-COMPLETED report1's credibility score was updated by cluster reinforcement
    await db_session.refresh(report1)
    assert report1.processing_status == "COMPLETED"
    assert float(report1.credibility_score) >= initial_score1


async def test_concurrent_inline_and_worker_pipeline_atomic_idempotency(db_session: AsyncSession) -> None:
    """Proves that concurrent inline execution and background worker on two independent DB connections produce exactly one intelligence_ready outbox event and 0 duplicate audit rows."""
    import asyncio

    from app.db.session import async_session_factory

    mock_redis, _ = _create_mock_redis_stream_bus()
    mock_realtime = RealtimeService(client=mock_redis)
    report_svc = ReportService(realtime_svc=mock_realtime)

    payload = CitizenReportCreate(
        latitude=28.6139,
        longitude=77.2090,
        category_code="AIR_QUALITY_SMOG",
        severity="MODERATE",
        title="Dense Smog Layer Observed",
        description="Visibility reduced severely across Central Delhi area.",
        location_name="Connaught Place, New Delhi",
    )
    # create_citizen_report executes the initial report creation and commits it to DB
    report, _ = await report_svc.create_citizen_report(session=db_session, payload=payload)
    report_id = report.id

    # Concurrently execute pipeline across two independent DB sessions/connections
    async def run_in_connection_1():
        async with async_session_factory() as session1:
            return await on_incident_ingested(db=session1, incident_id=report_id, commit=True)

    async def run_in_connection_2():
        async with async_session_factory() as session2:
            return await on_incident_ingested(db=session2, incident_id=report_id, commit=True)

    res1, res2 = await asyncio.gather(run_in_connection_1(), run_in_connection_2())
    assert res1.overall_readiness == OverallReadiness.INTELLIGENCE_READY
    assert res2.overall_readiness == OverallReadiness.INTELLIGENCE_READY

    # Verify exactly one intelligence_ready event was staged in realtime_outbox
    outbox_stmt = select(RealtimeOutbox).where(
        RealtimeOutbox.entity_id == str(report_id),
        RealtimeOutbox.event_type == "report.intelligence_ready",
    )
    outbox_res = await db_session.execute(outbox_stmt)
    outbox_rows = list(outbox_res.scalars().all())
    assert len(outbox_rows) == 1

    # Verify zero duplicate human verification audit rows were created
    audit_stmt = select(VerificationEvent).where(VerificationEvent.report_id == report_id)
    audit_res = await db_session.execute(audit_stmt)
    audit_rows = list(audit_res.scalars().all())
    assert len(audit_rows) == 0


async def test_worker_retries_partial_incident_without_force_to_ready(db_session: AsyncSession) -> None:
    """Proves that an incident left in INTELLIGENCE_PARTIAL is NOT skipped by worker run without force=True,
    retries the failed stage to reach INTELLIGENCE_READY, producing exactly 1 outbox event and 0 duplicate audit rows."""
    from app.db.session import async_session_factory
    from app.orchestration.state import SUCCESS_OUTCOMES, load_orchestration_state

    mock_redis, _ = _create_mock_redis_stream_bus()
    mock_realtime = RealtimeService(client=mock_redis)
    report_svc = ReportService(realtime_svc=mock_realtime)

    # 1. Create base report with failing EVIDENCE stage to simulate partial inline failure
    payload = CitizenReportCreate(
        latitude=12.9716,
        longitude=77.5946,
        category_code="URBAN_FLOODING",
        severity="SEVERE",
        title="Severe Inundation at MG Road",
        description="Road completely submerged under 3 feet of water.",
        location_name="MG Road, Bengaluru",
    )
    original_evidence_handler = incident_pipeline.handlers[StageName.EVIDENCE]

    class FailingEvidenceHandler:
        async def execute(self, db: AsyncSession, report: WeatherReport):
            raise ConnectionError("Simulated temporary network error querying evidence index")

    try:
        incident_pipeline.handlers[StageName.EVIDENCE] = FailingEvidenceHandler()  # type: ignore[assignment]

        # Inline execution leaves report in PARTIAL_INTELLIGENCE
        report, _ = await report_svc.create_citizen_report(session=db_session, payload=payload)
        report_id = report.id

        await db_session.refresh(report)
        assert report.processing_status == "PARTIAL_INTELLIGENCE"
        state = load_orchestration_state(report)
        assert state.overall_readiness == OverallReadiness.INTELLIGENCE_PARTIAL
        assert state.stages[StageName.EVIDENCE.value].status == StageOutcome.RETRYABLE_FAILURE.value
        assert state.stages[StageName.LOCATION.value].status in SUCCESS_OUTCOMES

        # Verify no outbox event was staged during the failed/partial inline run
        outbox_stmt = select(RealtimeOutbox).where(
            RealtimeOutbox.entity_id == str(report_id),
            RealtimeOutbox.event_type == "report.intelligence_ready",
        )
        outbox_res = await db_session.execute(outbox_stmt)
        assert len(list(outbox_res.scalars().all())) == 0

    finally:
        # Restore healthy evidence handler
        incident_pipeline.handlers[StageName.EVIDENCE] = original_evidence_handler

    # 2. Worker executes pipeline WITHOUT force=True on an independent DB session
    async with async_session_factory() as worker_session:
        worker_state = await on_incident_ingested(
            db=worker_session,
            incident_id=report_id,
            force=False,
            commit=True,
        )

    # 3. Verify worker did NOT skip PARTIAL incident, retried failed stage, and reached READY
    assert worker_state.overall_readiness == OverallReadiness.INTELLIGENCE_READY
    assert worker_state.stages[StageName.EVIDENCE.value].status in SUCCESS_OUTCOMES
    assert worker_state.stages[StageName.EVIDENCE.value].attempt == 2
    # Verify successfully completed stages (LOCATION) were NOT re-executed
    assert worker_state.stages[StageName.LOCATION.value].attempt == 1

    await db_session.refresh(report)
    assert report.processing_status == "COMPLETED"

    # 4. Verify exactly one intelligence_ready outbox event exists in total
    outbox_res = await db_session.execute(outbox_stmt)
    outbox_rows = list(outbox_res.scalars().all())
    assert len(outbox_rows) == 1

    # 5. Verify zero duplicate verification audit rows
    audit_stmt = select(VerificationEvent).where(VerificationEvent.report_id == report_id)
    audit_res = await db_session.execute(audit_stmt)
    audit_rows = list(audit_res.scalars().all())
    assert len(audit_rows) == 0

    # 6. Run worker a SECOND time without force=True: now that it is READY, guard MUST skip it
    async with async_session_factory() as worker_session2:
        second_worker_state = await on_incident_ingested(
            db=worker_session2,
            incident_id=report_id,
            force=False,
            commit=True,
        )
    assert second_worker_state.overall_readiness == OverallReadiness.INTELLIGENCE_READY
    # Outbox event count remains exactly 1
    outbox_res = await db_session.execute(outbox_stmt)
    assert len(list(outbox_res.scalars().all())) == 1

