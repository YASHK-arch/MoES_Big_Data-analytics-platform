#!/usr/bin/env python3
"""H4 load sampler: 50 concurrent geo requests + pg_stat_activity + docker stats snapshots."""
import asyncio
import time
import subprocess
import httpx

API_URL = "http://127.0.0.1:8010/api/v1/geo/incidents?limit=500&hours_ago=24"
CONCURRENCY = 50
REQUESTS = 100


async def shoot():
    results = []
    # Use separate clients per request to avoid shared ETag state
    sem = asyncio.Semaphore(CONCURRENCY)

    async def one():
        async with sem:
            async with httpx.AsyncClient(timeout=30, headers={"Cache-Control": "no-cache"}) as client:
                t0 = time.monotonic()
                r = await client.get(API_URL)
                return time.monotonic() - t0, r.status_code

    tasks = [asyncio.create_task(one()) for _ in range(REQUESTS)]
    for coro in asyncio.as_completed(tasks):
        elapsed, code = await coro
        results.append((elapsed, code))
    return results


def sample_pg():
    out = subprocess.check_output([
        "docker", "exec", "weather_postgres",
        "psql", "-U", "postgres", "-d", "weather_platform",
        "-c",
        "SELECT state, count(*) FROM pg_stat_activity WHERE datname='weather_platform' GROUP BY state ORDER BY state;"
    ]).decode()
    return out.strip()


def sample_docker():
    out = subprocess.check_output([
        "docker", "stats", "--no-stream", "--format",
        "{{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}"
    ]).decode()
    lines = [l for l in out.strip().splitlines() if any(k in l for k in ("weather_", "uvicorn"))]
    return "\n".join(lines) if lines else out.strip()[:500]


async def main():
    print("=== Starting 50-user geo load sampler ===")
    # Sample before
    print("\n[BEFORE] pg_stat_activity:")
    print(sample_pg())
    print("\n[BEFORE] docker stats (weather_ containers):")
    print(sample_docker())

    # Fire load in background, sample midway
    shoot_task = asyncio.create_task(shoot())

    await asyncio.sleep(2.0)
    print("\n[DURING] pg_stat_activity:")
    print(sample_pg())
    print("\n[DURING] docker stats (weather_ containers):")
    print(sample_docker())

    results = await shoot_task

    print("\n[AFTER] pg_stat_activity:")
    print(sample_pg())
    print("\n[AFTER] docker stats (weather_ containers):")
    print(sample_docker())

    latencies = [r[0] for r in results]
    latencies.sort()
    ok = sum(1 for _, s in results if s in (200, 304))
    n = len(latencies)
    by_code = {}
    for _, s in results:
        by_code[s] = by_code.get(s, 0) + 1
    print(f"\n=== Results: {ok}/{REQUESTS} success ===")
    print(f"  Status codes: {by_code}")
    print(f"  p50={latencies[n//2]*1000:.0f}ms  p95={latencies[int(n*0.95)]*1000:.0f}ms  max={latencies[-1]*1000:.0f}ms")


if __name__ == "__main__":
    asyncio.run(main())
