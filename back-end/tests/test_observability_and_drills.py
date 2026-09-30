"""Tests and failure recovery drills for S1 Observability, Metrics, and Failure Resilience."""

from __future__ import annotations

import asyncio
import time
import uuid
from datetime import datetime, timezone
from typing import List, Optional, Tuple

import numpy as np
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.metrics import (
    physical_cache_requests_total,
    physical_eval_duration_seconds,
    physical_fetch_duration_seconds,
    physical_provider_fetch_total,
    physical_recomputes_total,
    physical_verdicts_total,
)
from app.core.security import create_access_token
from app.intelligence.physical_corroboration.config import default_physical_config
from app.intelligence.physical_corroboration.models import (
    PhysicalObservation,
    PhysicalSourceType,
    ProviderStatus,
)
from app.intelligence.physical_corroboration.providers.base import BaseWeatherProvider
from app.intelligence.physical_corroboration.providers.cache import (
    SingleFlightGridHourCache,
)
from app.intelligence.physical_corroboration.service import (
    PhysicalCorroborationService,
)
from app.main import app
from app.models.corroboration import IncidentPhysicalCorroboration
from app.models.report import WeatherReport
from app.models.source import Source


class MockFailingProvider(BaseWeatherProvider):
    """Mock provider that returns configurable errors or healthy observations."""

    def __init__(self, mode: str = "ERROR") -> None:
        super().__init__(
            name="MOCK_DRILL_PROVIDER",
            source_type=PhysicalSourceType.MODEL,
            is_enabled=True,
            timeout_seconds=2.0,
            max_retries=0,
        )
        self.mode = mode

    async def _execute_fetch(
        self,
        lat: float,
        lon: float,
        target_time: datetime,
        category: str,
    ) -> Tuple[Optional[PhysicalObservation], ProviderStatus, Optional[str]]:
        if self.mode == "ERROR":
            return (
                None,
                ProviderStatus.PROVIDER_ERROR,
                "HTTP 503 Service Unavailable: upstream meteorological portal down",
            )
        if self.mode == "TIMEOUT":
            return None, ProviderStatus.TIMEOUT, "Request timed out after 2.0s"

        # Healthy SUPPORTS observation
        return (
            PhysicalObservation(
                source_name=self.name,
                source_type=self.source_type,
                station_or_grid_id="GRID_RECOVERY_01",
                latitude=lat,
                longitude=lon,
                observed_at=target_time,
                rainfall_1h_mm=85.0,
                is_simulated=False,
            ),
            ProviderStatus.OK,
            None,
        )


@pytest.fixture
async def api_client():
    token = create_access_token(subject="operator@weather-platform.gov.in", role="OPERATOR")
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport,
        base_url="http://testserver",
        headers={"Authorization": f"Bearer {token}"},
    ) as client:
        yield client


@pytest.mark.asyncio
async def test_prometheus_physical_metrics_in_endpoint(
    api_client: AsyncClient,
) -> None:
    """Verify physical corroboration metrics appear in Prometheus /api/v1/metrics output."""
    # Ensure at least one observation is recorded
    cache = SingleFlightGridHourCache(ttl_seconds=3600)

    async def _mock_fetch():
        return None, ProviderStatus.NO_DATA, "No data"

    await cache.get_or_fetch(
        lat=28.6,
        lon=77.2,
        target_time=datetime.now(timezone.utc),
        fetch_coroutine_fn=_mock_fetch,
    )

    res = await api_client.get("/api/v1/metrics")
    assert res.status_code == 200
    body = res.text

    assert "physical_cache_requests_total" in body
    assert "physical_provider_fetch_total" in body
    assert "physical_verdicts_total" in body
    assert "physical_recomputes_total" in body
    assert "physical_fetch_duration_seconds" in body
    assert "physical_eval_duration_seconds" in body


@pytest.mark.asyncio
async def test_drill_1_provider_outage_resilience_and_recovery(
    db_session: AsyncSession,
) -> None:
    """DRILL 1: Upstream provider returns errors for 5 mins.

    Guarantees:
    - 100% of incidents get NEUTRAL with explanation
    - Zero score penalty or false rejection
    - On provider recovery, recompute idempotently updates rows without duplicate entries
    """
    uid = uuid.uuid4().hex[:8]
    source = Source(
        source_code=f"SRC_D1_{uid}",
        name="Drill 1 Source",
        source_type="CITIZEN_REPORT",
        base_trust_score=0.70,
        is_active=True,
    )
    db_session.add(source)
    await db_session.flush()

    # Create 10 test reports
    reports: List[WeatherReport] = []
    now = datetime.now(timezone.utc)
    for i in range(10):
        r = WeatherReport(
            tracking_id=f"RPT-D1-{uid}-{i}",
            source_id=source.id,
            title=f"Drill 1 Flood Incident {i}",
            description="High water on arterial junction",
            location_name="Connaught Place, New Delhi",
            reported_category="HEAVY_RAINFALL",
            severity="HIGH",
            latitude=28.6315 + (i * 0.001),
            longitude=77.2167 + (i * 0.001),
            occurred_at=now,
            geom=f"SRID=4326;POINT({77.2167 + i * 0.001} {28.6315 + i * 0.001})",
            processing_status="PENDING",
            verification_status="PENDING",
            credibility_score=0.7000,
        )
        db_session.add(r)
        reports.append(r)
    await db_session.flush()

    # PHASE 1: Provider Outage (Returns HTTP 503 Provider Error)
    failing_provider = MockFailingProvider(mode="ERROR")
    outage_service = PhysicalCorroborationService(provider=failing_provider)

    for r in reports:
        corrob = await outage_service.corroborate_incident(
            db=db_session,
            report=r,
            force_run=True,
        )
        assert corrob is not None
        assert corrob.verdict == "NEUTRAL"
        assert corrob.provider_status == "PROVIDER_ERROR"
        assert corrob.contribution == 0.0
        # P6 invariant: status remains strictly PENDING
        assert r.verification_status == "PENDING"
        assert r.credibility_score == 0.7000

    await db_session.commit()

    # Verify 10 rows in DB
    report_ids = [r.id for r in reports]
    count_stmt = select(func.count(IncidentPhysicalCorroboration.id)).where(
        IncidentPhysicalCorroboration.incident_id.in_(report_ids)
    )
    total_outage_rows = (await db_session.execute(count_stmt)).scalar()
    assert total_outage_rows == 10

    # PHASE 2: Provider Recovers -> Recompute
    recovering_provider = MockFailingProvider(mode="HEALTHY")
    recovery_service = PhysicalCorroborationService(provider=recovering_provider)

    for r in reports:
        corrob_recovered = await recovery_service.corroborate_incident(
            db=db_session,
            report=r,
            force_run=True,
        )
        assert corrob_recovered is not None
        assert corrob_recovered.verdict == "SUPPORTS"
        assert corrob_recovered.provider_status == "OK"
        assert corrob_recovered.contribution > 0.0

    await db_session.commit()

    # Exactly 10 rows must remain in DB (Idempotent update, NO duplicates)
    total_recovered_rows = (await db_session.execute(count_stmt)).scalar()
    assert total_recovered_rows == 10


@pytest.mark.asyncio
async def test_drill_2_worker_crash_recovery_no_duplicate_rows(
    db_session: AsyncSession,
) -> None:
    """DRILL 2: Kill worker mid-batch and restart -> recovers with zero duplicate rows."""
    uid = uuid.uuid4().hex[:8]
    source = Source(
        source_code=f"SRC_D2_{uid}",
        name="Drill 2 Source",
        source_type="CITIZEN_REPORT",
        base_trust_score=0.70,
        is_active=True,
    )
    db_session.add(source)
    await db_session.flush()

    reports: List[WeatherReport] = []
    now = datetime.now(timezone.utc)
    for i in range(5):
        r = WeatherReport(
            tracking_id=f"RPT-D2-{uid}-{i}",
            source_id=source.id,
            title=f"Drill 2 Batch Incident {i}",
            reported_category="HEAVY_RAINFALL",
            severity="HIGH",
            latitude=19.0760 + (i * 0.002),
            longitude=72.8777 + (i * 0.002),
            occurred_at=now,
            geom=f"SRID=4326;POINT({72.8777 + i * 0.002} {19.0760 + i * 0.002})",
            processing_status="PENDING",
            verification_status="PENDING",
        )
        db_session.add(r)
        reports.append(r)
    await db_session.flush()

    provider = MockFailingProvider(mode="HEALTHY")
    service = PhysicalCorroborationService(provider=provider)

    # 1. First worker run: crashes after 2 reports
    for idx, r in enumerate(reports):
        if idx == 2:
            # Simulate worker SIGKILL / unhandled crash
            await db_session.commit()
            break
        await service.corroborate_incident(db=db_session, report=r, force_run=True)

    report_ids = [r.id for r in reports]
    count_stmt = select(func.count(IncidentPhysicalCorroboration.id)).where(
        IncidentPhysicalCorroboration.incident_id.in_(report_ids)
    )
    rows_mid_crash = (await db_session.execute(count_stmt)).scalar()
    assert rows_mid_crash == 2

    # 2. Worker restarts and re-processes the entire batch of 5 from stream
    restarted_service = PhysicalCorroborationService(provider=provider)
    for r in reports:
        await restarted_service.corroborate_incident(db=db_session, report=r, force_run=True)

    await db_session.commit()

    # Exactly 5 records must exist (Zero duplicate rows across restarts)
    rows_after_recovery = (await db_session.execute(count_stmt)).scalar()
    assert rows_after_recovery == 5


@pytest.mark.asyncio
async def test_drill_latency_benchmark() -> None:
    """Benchmark p50 and p95 latencies: With vs Without feature, Cache Hit vs Cache Miss."""
    provider = MockFailingProvider(mode="HEALTHY")
    cache = SingleFlightGridHourCache(ttl_seconds=3600)
    service = PhysicalCorroborationService(provider=provider, cache=cache)
    now = datetime.now(timezone.utc)
    iterations = 50

    # 1. Baseline latency: Pure evaluator (without network/provider fetch)
    eval_latencies_ms: List[float] = []
    obs = PhysicalObservation(
        source_name="BENCHMARK",
        source_type=PhysicalSourceType.MODEL,
        station_or_grid_id="GRID_01",
        latitude=28.6,
        longitude=77.2,
        observed_at=now,
        rainfall_1h_mm=45.0,
    )
    from app.intelligence.physical_corroboration.evaluator import evaluate

    for _ in range(iterations):
        t0 = time.perf_counter()
        _ = evaluate(
            category="HEAVY_RAINFALL",
            observation=obs,
            incident_time=now,
            incident_coords=(28.6, 77.2),
            config=default_physical_config,
        )
        eval_latencies_ms.append((time.perf_counter() - t0) * 1000.0)

    # 2. Cache Miss latency (unique coordinates per iteration)
    cache_miss_latencies_ms: List[float] = []
    for i in range(iterations):
        t0 = time.perf_counter()

        async def _fetch():
            return await provider.fetch_observation(
                lat=28.0 + (i * 0.5),
                lon=77.0 + (i * 0.5),
                target_time=now,
                category="HEAVY_RAINFALL",
            )

        await cache.get_or_fetch(
            lat=28.0 + (i * 0.5),
            lon=77.0 + (i * 0.5),
            target_time=now,
            fetch_coroutine_fn=_fetch,
        )
        cache_miss_latencies_ms.append((time.perf_counter() - t0) * 1000.0)

    # 3. Cache Hit latency (repeated coordinate lookups against populated cache)
    cache_hit_latencies_ms: List[float] = []
    for _ in range(iterations):
        t0 = time.perf_counter()

        async def _fetch():
            return None, ProviderStatus.NO_DATA, "Should not be called"

        await cache.get_or_fetch(
            lat=28.0,
            lon=77.0,
            target_time=now,
            fetch_coroutine_fn=_fetch,
        )
        cache_hit_latencies_ms.append((time.perf_counter() - t0) * 1000.0)

    p50_eval = float(np.percentile(eval_latencies_ms, 50))
    p95_eval = float(np.percentile(eval_latencies_ms, 95))

    p50_miss = float(np.percentile(cache_miss_latencies_ms, 50))
    p95_miss = float(np.percentile(cache_miss_latencies_ms, 95))

    p50_hit = float(np.percentile(cache_hit_latencies_ms, 50))
    p95_hit = float(np.percentile(cache_hit_latencies_ms, 95))

    print("\n" + "=" * 80)
    print("S1 PHYSICAL CORROBORATION LATENCY BENCHMARK (50 iterations)")
    print("=" * 80)
    print(f"Pure Logic Evaluation : p50 = {p50_eval:.4f} ms | p95 = {p95_eval:.4f} ms")
    print(f"Cache Miss (Provider) : p50 = {p50_miss:.4f} ms | p95 = {p95_miss:.4f} ms")
    print(f"Cache Hit (In-Memory) : p50 = {p50_hit:.4f} ms | p95 = {p95_hit:.4f} ms")
    print("=" * 80)

    # Performance invariants
    assert p50_eval < 2.0, f"Pure logic evaluation p50 {p50_eval}ms exceeds 2ms budget"
    assert p50_hit < 1.0, f"Cache hit p50 {p50_hit}ms exceeds 1ms budget"
    assert p95_hit < 5.0, f"Cache hit p95 {p95_hit}ms exceeds 5ms budget"
