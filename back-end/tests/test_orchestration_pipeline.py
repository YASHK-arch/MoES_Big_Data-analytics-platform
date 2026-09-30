"""Integration tests for incident pipeline execution, failure isolation, and targeted triggers."""

import uuid
from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.evidence import EvidenceItem
from app.models.report import WeatherReport
from app.models.source import Source
from app.orchestration.events import (
    OverallReadiness,
    StageName,
    StageOutcome,
)
from app.orchestration.incident_pipeline import incident_pipeline
from app.orchestration.triggers import (
    on_evidence_ingested,
    on_human_verification_updated,
    on_incident_ingested,
)


@pytest.mark.asyncio
async def test_happy_path_full_pipeline(db_session: AsyncSession) -> None:
    """Verify full forward pipeline execution from Ingested to INTELLIGENCE_READY."""
    uid_hex = uuid.uuid4().hex[:8]
    source = Source(
        source_code=f"SRC_PIPE_{uid_hex}",
        name="Pipeline Ingestion Source",
        source_type="CITIZEN_REPORT",
        base_trust_score=0.60,
        is_active=True,
    )
    db_session.add(source)
    await db_session.flush()

    report = WeatherReport(
        tracking_id=f"RPT-PIPE-{uid_hex}",
        source_id=source.id,
        title="Heavy Flood in Kurla East",
        description="Water logging up to 3 feet in residential area near railway line.",
        location_name="Kurla, Mumbai",
        reported_category="FLOOD",
        latitude=19.0657,
        longitude=72.8794,
        occurred_at=datetime.now(timezone.utc),
        geom="SRID=4326;POINT(72.8794 19.0657)",
        processing_status="PENDING",
        verification_status="PENDING",
        credibility_score=0.0,
    )
    db_session.add(report)
    await db_session.commit()

    # Execute pipeline
    state = await on_incident_ingested(db=db_session, incident_id=report.id)

    assert state.overall_readiness in (
        OverallReadiness.INTELLIGENCE_READY,
        OverallReadiness.INTELLIGENCE_PARTIAL,
    )
    assert StageName.LOCATION in state.stages
    assert StageName.CREDIBILITY in state.stages
    assert state.stages[StageName.LOCATION].status in (
        StageOutcome.SUCCESS_WITH_RESULTS,
        StageOutcome.SUCCESS_WITH_INSUFFICIENT_DATA,
    )
    assert state.stages[StageName.CREDIBILITY].status == StageOutcome.SUCCESS_WITH_RESULTS

    # Verify report entity updated in database
    stmt = select(WeatherReport).where(WeatherReport.id == report.id)
    res = await db_session.execute(stmt)
    updated_report = res.scalar_one()

    assert updated_report.credibility_score > 0.0
    assert updated_report.credibility_explanation is not None
    assert updated_report.raw_payload is not None
    assert "orchestration" in updated_report.raw_payload


@pytest.mark.asyncio
async def test_partial_success_when_optional_stage_fails(db_session: AsyncSession) -> None:
    """Verify that an optional stage failure preserves incident and credibility."""
    uid_hex = uuid.uuid4().hex[:8]
    source = Source(
        source_code=f"SRC_PART_{uid_hex}",
        name="Partial Test Source",
        source_type="CITIZEN_REPORT",
        base_trust_score=0.60,
        is_active=True,
    )
    db_session.add(source)
    await db_session.flush()

    report = WeatherReport(
        tracking_id=f"RPT-PART-{uid_hex}",
        source_id=source.id,
        title="Urban Inundation Alert",
        description="Localized water accumulation after sudden cloudburst.",
        location_name="MG Road, Bangalore",
        reported_category="FLOOD",
        latitude=12.9716,
        longitude=77.5946,
        occurred_at=datetime.now(timezone.utc),
        geom="SRID=4326;POINT(77.5946 12.9716)",
        processing_status="PENDING",
        verification_status="PENDING",
        credibility_score=0.0,
    )
    db_session.add(report)
    await db_session.commit()

    # Simulate GDELT candidate generation failure
    with patch.object(
        incident_pipeline.handlers[StageName.EVIDENCE],
        "execute",
        side_effect=RuntimeError("GDELT HTTP 503 Gateway Timeout"),
    ):
        state = await incident_pipeline.execute_pipeline(db=db_session, incident_id=report.id)

    # Readiness should be PARTIAL, not FAILED
    assert state.overall_readiness == OverallReadiness.INTELLIGENCE_PARTIAL

    # Credibility stage should have executed successfully despite Evidence failure
    stmt = select(WeatherReport).where(WeatherReport.id == report.id)
    res = await db_session.execute(stmt)
    refreshed = res.scalar_one()

    assert refreshed.credibility_score > 0.0  # Quality-adjusted baseline evaluated cleanly
    assert refreshed.processing_status == "PARTIAL_INTELLIGENCE"


@pytest.mark.asyncio
async def test_stale_result_protection_skips_outdated_write(db_session: AsyncSession) -> None:
    """Verify compare-before-write detects modified input state and skips stale write."""
    uid_hex = uuid.uuid4().hex[:8]
    source = Source(
        source_code=f"SRC_STALE_{uid_hex}",
        name="Stale Protection Test Source",
        source_type="CITIZEN_REPORT",
        base_trust_score=0.60,
        is_active=True,
    )
    db_session.add(source)
    await db_session.flush()

    report = WeatherReport(
        tracking_id=f"RPT-STALE-{uid_hex}",
        source_id=source.id,
        title="River Swelling Alert",
        description="Bhadra river water level rising near old bridge.",
        location_name="Bhadravathi, Karnataka",
        reported_category="FLOOD",
        latitude=13.8415,
        longitude=75.7022,
        occurred_at=datetime.now(timezone.utc),
        geom="SRID=4326;POINT(75.7022 13.8415)",
        processing_status="PENDING",
        verification_status="PENDING",
        credibility_score=0.5000,
    )
    db_session.add(report)
    await db_session.commit()

    # Simulate fingerprint mismatch during compare-before-write
    with patch(
        "app.orchestration.handlers.compute_credibility_fingerprint",
        side_effect=["fingerprint_initial_f1", "fingerprint_current_f2"],
    ):
        result = await incident_pipeline.execute_single_stage(
            db=db_session,
            incident_id=report.id,
            stage_name=StageName.CREDIBILITY,
        )
        assert result.outcome == StageOutcome.SKIPPED_STALE

    # Verify original score in DB was NOT overwritten by stale calculation
    stmt = select(WeatherReport).where(WeatherReport.id == report.id)
    res = await db_session.execute(stmt)
    refreshed = res.scalar_one()
    assert refreshed.credibility_score == 0.5000


@pytest.mark.asyncio
async def test_targeted_evidence_recomputation(db_session: AsyncSession) -> None:
    """Verify new evidence item triggers targeted credibility update only for matched incident."""
    uid_hex = uuid.uuid4().hex[:8]
    source = Source(
        source_code=f"SRC_TRG_{uid_hex}",
        name="Trigger Test Source",
        source_type="CITIZEN_REPORT",
        base_trust_score=0.60,
        is_active=True,
    )
    db_session.add(source)
    await db_session.flush()

    report = WeatherReport(
        tracking_id=f"RPT-TRG-{uid_hex}",
        source_id=source.id,
        title="Cyclone Storm Damage",
        description="High velocity wind gale damaging structures.",
        location_name="Puri, Odisha",
        reported_category="CYCLONE",
        latitude=19.8135,
        longitude=85.8312,
        occurred_at=datetime.now(timezone.utc),
        geom="SRID=4326;POINT(85.8312 19.8135)",
        processing_status="COMPLETED",
        verification_status="PENDING",
        credibility_score=0.6000,
    )
    db_session.add(report)
    await db_session.commit()

    # Ingest new evidence item
    evidence = EvidenceItem(
        source_id=source.id,
        external_id=f"evi_trg_{uid_hex}",
        evidence_type="NEWS_ARTICLE",
        title="Cyclone Storm Gale Hits Puri Coast",
        text_snippet="Severe gale damage reported along Puri shoreline.",
        publisher_domain="odishatv.in",
        published_at=datetime.now(timezone.utc),
    )
    db_session.add(evidence)
    await db_session.commit()

    affected_ids = await on_evidence_ingested(db=db_session, evidence_id=evidence.id)
    assert report.id in affected_ids

    # Verify report credibility lifted above baseline
    stmt = select(WeatherReport).where(WeatherReport.id == report.id)
    res = await db_session.execute(stmt)
    refreshed = res.scalar_one()
    assert refreshed.credibility_score > 0.6000


@pytest.mark.asyncio
async def test_human_verification_state_isolation(db_session: AsyncSession) -> None:
    """Verify that human verification changes are isolated from machine credibility."""
    uid_hex = uuid.uuid4().hex[:8]
    source = Source(
        source_code=f"SRC_HUM_{uid_hex}",
        name="Human Test Source",
        source_type="CITIZEN_REPORT",
        base_trust_score=0.60,
        is_active=True,
    )
    db_session.add(source)
    await db_session.flush()

    report = WeatherReport(
        tracking_id=f"RPT-HUM-{uid_hex}",
        source_id=source.id,
        title="Flood Inundation",
        description="Water entering ground floor houses.",
        location_name="Cuttack, Odisha",
        reported_category="FLOOD",
        latitude=20.4625,
        longitude=85.8828,
        occurred_at=datetime.now(timezone.utc),
        geom="SRID=4326;POINT(85.8828 20.4625)",
        processing_status="COMPLETED",
        verification_status="PENDING",
        credibility_score=0.7081,
    )
    db_session.add(report)
    await db_session.commit()

    # Operator marks report VERIFIED
    updated_report = await on_human_verification_updated(
        db=db_session,
        report_id=report.id,
        new_status="VERIFIED",
    )
    assert updated_report is not None
    assert updated_report.verification_status == "VERIFIED"
    assert updated_report.credibility_score == 0.7081  # Machine score remains unchanged


@pytest.mark.asyncio
async def test_optional_permanent_failure_results_in_intelligence_partial(
    db_session: AsyncSession,
) -> None:
    """Verify permanent failure of optional stage results in INTELLIGENCE_PARTIAL, never FAILED."""
    uid_hex = uuid.uuid4().hex[:8]
    source = Source(
        source_code=f"SRC_OPT_FAIL_{uid_hex}",
        name="Optional Failure Source",
        source_type="CITIZEN_REPORT",
        base_trust_score=0.60,
        is_active=True,
    )
    db_session.add(source)
    await db_session.flush()

    report = WeatherReport(
        tracking_id=f"RPT-OPT-{uid_hex}",
        source_id=source.id,
        title="Landslide Warning",
        description="Soil displacement blocking state highway.",
        location_name="Wayanad, Kerala",
        reported_category="LANDSLIDE",
        latitude=11.6854,
        longitude=76.1320,
        occurred_at=datetime.now(timezone.utc),
        geom="SRID=4326;POINT(76.1320 11.6854)",
        processing_status="PENDING",
        verification_status="PENDING",
        credibility_score=0.0,
    )
    db_session.add(report)
    await db_session.commit()

    # Simulate permanent failure in EVIDENCE stage (e.g. unrecoverable malformed response)
    with patch.object(
        incident_pipeline.handlers[StageName.EVIDENCE],
        "execute",
        side_effect=ValueError("Unrecoverable data format error in external feed"),
    ):
        state = await incident_pipeline.execute_pipeline(db=db_session, incident_id=report.id)

    assert state.overall_readiness == OverallReadiness.INTELLIGENCE_PARTIAL
    assert state.stages[StageName.EVIDENCE].status == StageOutcome.PERMANENT_FAILURE
    assert state.stages[StageName.CREDIBILITY].status == StageOutcome.SUCCESS_WITH_RESULTS

    stmt = select(WeatherReport).where(WeatherReport.id == report.id)
    res = await db_session.execute(stmt)
    refreshed = res.scalar_one()

    assert refreshed.credibility_score > 0.0
    assert refreshed.processing_status == "PARTIAL_INTELLIGENCE"


@pytest.mark.asyncio
async def test_concurrent_stage_updates_no_jsonb_overwrite(
    db_session: AsyncSession,
) -> None:
    """Verify two concurrent stage updates on the same report do not overwrite each other."""
    uid_hex = uuid.uuid4().hex[:8]
    source = Source(
        source_code=f"SRC_CONCUR_{uid_hex}",
        name="Concurrency Test Source",
        source_type="CITIZEN_REPORT",
        base_trust_score=0.60,
        is_active=True,
    )
    db_session.add(source)
    await db_session.flush()

    report = WeatherReport(
        tracking_id=f"RPT-CONCUR-{uid_hex}",
        source_id=source.id,
        title="Flash Flood Alert",
        description="Rapid stream rise.",
        location_name="Rishikesh, Uttarakhand",
        reported_category="FLOOD",
        latitude=30.0869,
        longitude=78.2676,
        occurred_at=datetime.now(timezone.utc),
        geom="SRID=4326;POINT(78.2676 30.0869)",
        processing_status="PENDING",
        verification_status="PENDING",
        credibility_score=0.0,
    )
    db_session.add(report)
    await db_session.commit()

    # Worker A updates LOCATION stage
    await incident_pipeline.execute_single_stage(
        db=db_session,
        incident_id=report.id,
        stage_name=StageName.LOCATION,
        commit=True,
    )

    # Worker B updates EVIDENCE stage
    await incident_pipeline.execute_single_stage(
        db=db_session,
        incident_id=report.id,
        stage_name=StageName.EVIDENCE,
        commit=True,
    )

    # Verify both LOCATION and EVIDENCE stage entries are preserved in JSONB
    stmt = select(WeatherReport).where(WeatherReport.id == report.id)
    res = await db_session.execute(stmt)
    refreshed = res.scalar_one()

    assert refreshed.raw_payload is not None
    stages = refreshed.raw_payload["orchestration"]["stages"]
    assert "LOCATION" in stages
    assert "EVIDENCE" in stages
    assert stages["LOCATION"]["status"] in (
        StageOutcome.SUCCESS_WITH_RESULTS.value,
        StageOutcome.SUCCESS_WITH_INSUFFICIENT_DATA.value,
    )
    assert stages["EVIDENCE"]["status"] in (
        StageOutcome.SUCCESS_WITH_RESULTS.value,
        StageOutcome.SUCCESS_WITH_NO_MATCH.value,
    )


@pytest.mark.asyncio
async def test_consumer_killed_mid_batch_reclaimed_by_new_worker(db_session: AsyncSession):
    """Regression test: worker 1 reads messages mid-batch and crashes without ACKing; worker 2 reclaims and completes them."""
    from app.core.redis import AsyncRedisClient
    from app.orchestration.dispatcher import OrchestrationDispatcher
    from app.orchestration.events import AggregateType, OrchestrationEvent, OrchestrationEventType

    client = AsyncRedisClient(redis_url="redis://localhost:6379/5")
    await client.connect()
    stream_name = f"stream:test:reclaim:{uuid.uuid4().hex[:6]}"
    group_name = "group:test:reclaim"

    # Setup stream and group
    await client.xgroup_create(stream_name, group_name, id_str="0", mkstream=True)

    # Dispatcher 1 (Worker 1)
    dispatcher_1 = OrchestrationDispatcher(client=client, consumer_name="worker-1")
    dispatcher_1.DEFAULT_STREAM = stream_name
    dispatcher_1.DEFAULT_GROUP = group_name

    # Publish 2 events
    ev1 = OrchestrationEvent(
        event_id=uuid.uuid4(),
        event_type=OrchestrationEventType.INCIDENT_INGESTED,
        aggregate_type=AggregateType.WEATHER_REPORT,
        aggregate_id=uuid.uuid4(),
        producer="test",
        correlation_id="c1",
        idempotency_key=str(uuid.uuid4()),
        attempt=1,
        created_at=datetime.now(timezone.utc),
    )
    ev2 = OrchestrationEvent(
        event_id=uuid.uuid4(),
        event_type=OrchestrationEventType.INCIDENT_INGESTED,
        aggregate_type=AggregateType.WEATHER_REPORT,
        aggregate_id=uuid.uuid4(),
        producer="test",
        correlation_id="c2",
        idempotency_key=str(uuid.uuid4()),
        attempt=1,
        created_at=datetime.now(timezone.utc),
    )
    await dispatcher_1.publish_event(ev1)
    await dispatcher_1.publish_event(ev2)

    # Worker 1 reads 2 events from stream but crashes before ACKing
    events_w1 = await dispatcher_1.read_events(count=2, block_ms=500)
    assert len(events_w1) == 2

    # Verify 2 messages are pending on worker-1
    pending_w1 = await client.xpending_detail(stream_name, group_name)
    assert len(pending_w1) == 2
    assert all(p["consumer"] == "worker-1" for p in pending_w1)

    # Simulate worker 1 dying and idle time passing
    import asyncio

    await asyncio.sleep(0.05)

    # Dispatcher 2 (Worker 2) starts with claim_idle_ms=10 (10ms)
    dispatcher_2 = OrchestrationDispatcher(client=client, consumer_name="worker-2")
    dispatcher_2.DEFAULT_STREAM = stream_name
    dispatcher_2.DEFAULT_GROUP = group_name

    claimed_events = await dispatcher_2.read_events(count=10, block_ms=500, claim_idle_ms=10)
    assert len(claimed_events) == 2
    assert {e[1].event_id for e in claimed_events} == {ev1.event_id, ev2.event_id}

    # Worker 2 ACKs them after processing
    for msg_id, _ in claimed_events:
        await client.xack(stream_name, group_name, msg_id)

    # Verify pending list is now completely cleared
    pending_after = await client.xpending_detail(stream_name, group_name)
    assert len(pending_after) == 0

    await client.delete(stream_name)
    await client.close()
