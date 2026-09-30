"""Benchmark incident-detail endpoint latency under 50 concurrent users.

Measures:
1. Incident-detail endpoint GET /api/v1/reports/{id}
   - PHYSICAL_CORROBORATION_ENABLED = False (Cache Miss vs Cache Hit)
   - PHYSICAL_CORROBORATION_ENABLED = True  (Cache Miss vs Cache Hit)
2. Corroboration observation fetch & evaluation service
   - Cache Miss (Provider fetch + Single-flight lock)
   - Cache Hit (In-memory / Redis cache hit)
All under 50 concurrent requests.
"""

import asyncio
import os
import sys
import time
from typing import List, Tuple

import numpy as np
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

# Ensure back-end is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../back-end")))

# Set environment
os.environ["DATABASE_URL"] = "postgresql+asyncpg://postgres:postgres@localhost:5432/weather_platform_s1"
os.environ["REDIS_URL"] = "redis://localhost:6379/6"

from app.core.config import settings
from app.db.session import async_session_factory
from app.intelligence.physical_corroboration.models import PhysicalObservation, ProviderStatus
from app.intelligence.physical_corroboration.providers.cache import SingleFlightGridHourCache
from app.intelligence.physical_corroboration.service import PhysicalCorroborationService
from app.main import app
from app.models.report import WeatherReport


def calculate_stats(latencies_ms: List[float]) -> dict:
    arr = np.array(latencies_ms)
    return {
        "p50": float(np.percentile(arr, 50)),
        "p90": float(np.percentile(arr, 90)),
        "p95": float(np.percentile(arr, 95)),
        "p99": float(np.percentile(arr, 99)),
        "min": float(np.min(arr)),
        "max": float(np.max(arr)),
        "mean": float(np.mean(arr)),
    }


async def benchmark_endpoint_concurrency(
    client: AsyncClient,
    url: str,
    concurrency: int = 50,
    rounds: int = 2,
) -> Tuple[List[float], List[float]]:
    """Fire concurrent requests.

    Round 1: Cache Miss / Cold DB query
    Round 2+: Cache Hit / Warm memory/buffer query
    """
    # Round 1: Cold / Miss
    async def single_req():
        t0 = time.perf_counter()
        resp = await client.get(url)
        t1 = time.perf_counter()
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
        return (t1 - t0) * 1000.0  # ms

    tasks_miss = [single_req() for _ in range(concurrency)]
    latencies_miss = await asyncio.gather(*tasks_miss)

    # Round 2: Warm / Hit
    tasks_hit = [single_req() for _ in range(concurrency)]
    latencies_hit = await asyncio.gather(*tasks_hit)

    return latencies_miss, latencies_hit


async def benchmark_service_concurrency(
    report: WeatherReport,
    concurrency: int = 50,
) -> Tuple[List[float], List[float]]:
    """Benchmark PhysicalCorroborationService under 50 concurrent requests."""
    cache = SingleFlightGridHourCache(ttl_seconds=3600)
    service = PhysicalCorroborationService(cache=cache)

    # Miss: Cold cache, concurrent requests coordinate via single-flight mutex
    async def run_corroborate():
        t0 = time.perf_counter()
        async with async_session_factory() as session:
            # Re-fetch report inside session
            res = await session.execute(select(WeatherReport).where(WeatherReport.id == report.id))
            r = res.scalar_one()
            await service.corroborate_incident(session, r, force_run=True)
        t1 = time.perf_counter()
        return (t1 - t0) * 1000.0

    tasks_miss = [run_corroborate() for _ in range(concurrency)]
    latencies_miss = await asyncio.gather(*tasks_miss)

    # Hit: Warm cache, 50 concurrent requests hit in-memory grid-hour cache
    tasks_hit = [run_corroborate() for _ in range(concurrency)]
    latencies_hit = await asyncio.gather(*tasks_hit)

    return latencies_miss, latencies_hit


async def main():
    print("================================================================================")
    print("INCIDENT-DETAIL ENDPOINT AND SERVICE LATENCY BENCHMARK")
    print("Concurrency: 50 concurrent users | Target DB: weather_platform_s1 | Redis DB: 6")
    print("================================================================================\n")

    # 1. Fetch target test incident
    async with async_session_factory() as session:
        stmt = (
            select(WeatherReport)
            .where(WeatherReport.physical_corroborations.any())
            .limit(1)
        )
        res = await session.execute(stmt)
        report = res.scalar_one_or_none()
        if not report:
            # Fallback to any report
            stmt2 = select(WeatherReport).limit(1)
            res2 = await session.execute(stmt2)
            report = res2.scalar_one()

        report_id = str(report.id)
        tracking_id = report.tracking_id
        category = report.reported_category

    print(f"Target Incident ID : {report_id}")
    print(f"Tracking ID        : {tracking_id}")
    print(f"Category           : {category}\n")

    url = f"/api/v1/reports/{report_id}"
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        # TEST 1: PHYSICAL_CORROBORATION_ENABLED = False
        settings.PHYSICAL_CORROBORATION_ENABLED = False
        print("--- SCENARIO 1: PHYSICAL_CORROBORATION_ENABLED = False ---")
        miss_off, hit_off = await benchmark_endpoint_concurrency(client, url, concurrency=50)
        stats_miss_off = calculate_stats(miss_off)
        stats_hit_off = calculate_stats(hit_off)

        print(f"  Cache Miss (Cold, 50 users) : p50 = {stats_miss_off['p50']:6.2f} ms | p95 = {stats_miss_off['p95']:6.2f} ms | mean = {stats_miss_off['mean']:6.2f} ms")
        print(f"  Cache Hit  (Warm, 50 users) : p50 = {stats_hit_off['p50']:6.2f} ms | p95 = {stats_hit_off['p95']:6.2f} ms | mean = {stats_hit_off['mean']:6.2f} ms")

        # TEST 2: PHYSICAL_CORROBORATION_ENABLED = True
        settings.PHYSICAL_CORROBORATION_ENABLED = True
        print("\n--- SCENARIO 2: PHYSICAL_CORROBORATION_ENABLED = True ---")
        miss_on, hit_on = await benchmark_endpoint_concurrency(client, url, concurrency=50)
        stats_miss_on = calculate_stats(miss_on)
        stats_hit_on = calculate_stats(hit_on)

        print(f"  Cache Miss (Cold, 50 users) : p50 = {stats_miss_on['p50']:6.2f} ms | p95 = {stats_miss_on['p95']:6.2f} ms | mean = {stats_miss_on['mean']:6.2f} ms")
        print(f"  Cache Hit  (Warm, 50 users) : p50 = {stats_hit_on['p50']:6.2f} ms | p95 = {stats_hit_on['p95']:6.2f} ms | mean = {stats_hit_on['mean']:6.2f} ms")

    # TEST 3: OBSERVATION PIPELINE SERVICE LATENCY (Provider + Cache)
    print("\n--- SCENARIO 3: PHYSICAL CORROBORATION SERVICE (Under 50 Concurrent Requests) ---")
    svc_miss, svc_hit = await benchmark_service_concurrency(report, concurrency=50)
    stats_svc_miss = calculate_stats(svc_miss)
    stats_svc_hit = calculate_stats(svc_hit)

    print(f"  Single-Flight Miss (1 live fetch + 49 mutex waits) : p50 = {stats_svc_miss['p50']:6.2f} ms | p95 = {stats_svc_miss['p95']:6.2f} ms")
    print(f"  Observation Cache Hit (50 concurrent memory hits)   : p50 = {stats_svc_hit['p50']:6.2f} ms | p95 = {stats_svc_hit['p95']:6.2f} ms")

    # COMPARISON TABLE
    print("\n================================================================================")
    print("SUMMARY LATENCY COMPARISON TABLE (INCIDENT-DETAIL ENDPOINT, 50 CONCURRENT USERS)")
    print("================================================================================")
    print(f"{'Condition':<40} | {'p50 (ms)':<10} | {'p95 (ms)':<10} | {'Mean (ms)':<10}")
    print("-" * 76)
    print(f"{'Corroboration OFF - Cache Miss':<40} | {stats_miss_off['p50']:<10.2f} | {stats_miss_off['p95']:<10.2f} | {stats_miss_off['mean']:<10.2f}")
    print(f"{'Corroboration OFF - Cache Hit':<40} | {stats_hit_off['p50']:<10.2f} | {stats_hit_off['p95']:<10.2f} | {stats_hit_off['mean']:<10.2f}")
    print(f"{'Corroboration ON  - Cache Miss':<40} | {stats_miss_on['p50']:<10.2f} | {stats_miss_on['p95']:<10.2f} | {stats_miss_on['mean']:<10.2f}")
    print(f"{'Corroboration ON  - Cache Hit':<40} | {stats_hit_on['p50']:<10.2f} | {stats_hit_on['p95']:<10.2f} | {stats_hit_on['mean']:<10.2f}")
    print("================================================================================")

    # Overhead calculation
    p50_overhead_miss = stats_miss_on['p50'] - stats_miss_off['p50']
    p95_overhead_miss = stats_miss_on['p95'] - stats_miss_off['p95']
    p50_overhead_hit = stats_hit_on['p50'] - stats_hit_off['p50']
    p95_overhead_hit = stats_hit_on['p95'] - stats_hit_off['p95']

    print(f"\nPhysical Corroboration Serialization Overhead:")
    print(f"  Cold/Miss Delta: p50 = {p50_overhead_miss:+.2f} ms | p95 = {p95_overhead_miss:+.2f} ms")
    print(f"  Warm/Hit  Delta: p50 = {p50_overhead_hit:+.2f} ms | p95 = {p95_overhead_hit:+.2f} ms")


if __name__ == "__main__":
    asyncio.run(main())
