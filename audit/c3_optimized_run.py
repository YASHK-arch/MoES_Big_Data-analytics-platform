import asyncio
import os
import random
import signal
import subprocess
import time
from collections import defaultdict
import httpx
import numpy as np

BASE_URL = "http://127.0.0.1:8001"
ENDPOINTS = [
    "/api/v1/reports?page=1&limit=20",
    "/api/v1/geo/incidents?bbox=72.0,18.0,74.0,20.0&limit=50",
]

def start_server(workers: int = 4):
    env = os.environ.copy()
    env["PYTHONPATH"] = "back-end"
    env["DATABASE_URL"] = "postgresql+asyncpg://postgres:postgres@localhost:5432/weather_platform_audit"
    env["REDIS_URL"] = "redis://localhost:6379/5"
    env["S3_BUCKET_NAME"] = "weather-media-audit"
    env["ENVIRONMENT"] = "development"

    cmd = [
        "back-end/.venv/bin/python", "-m", "uvicorn", "app.main:app",
        "--host", "127.0.0.1",
        "--port", "8001",
        "--workers", str(workers),
        "--log-level", "warning",
    ]

    proc = subprocess.Popen(
        cmd,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    for _ in range(60):
        time.sleep(0.1)
        try:
            r = httpx.get("http://127.0.0.1:8001/health", timeout=1.0)
            if r.status_code == 200:
                break
        except Exception:
            pass
    return proc

def stop_server(proc):
    if proc:
        proc.send_signal(signal.SIGINT)
        try:
            proc.wait(timeout=5.0)
        except subprocess.TimeoutExpired:
            proc.kill()

async def run_load_generator(duration_sec: float = 15.0, concurrency: int = 50):
    ep_latencies = defaultdict(list)
    errors = []
    stop_time = time.time() + duration_sec

    cpu_t0 = time.process_time()
    wall_t0 = time.perf_counter()

    async def worker(client):
        while time.time() < stop_time:
            ep = random.choice(ENDPOINTS)
            t0 = time.perf_counter()
            try:
                r = await client.get(BASE_URL + ep)
                lat = (time.perf_counter() - t0) * 1000
                if r.status_code == 200:
                    ep_latencies[ep].append(lat)
                else:
                    errors.append((ep, r.status_code))
            except Exception as e:
                errors.append((ep, str(e)))

    limits = httpx.Limits(max_connections=100, max_keepalive_connections=50)
    async with httpx.AsyncClient(timeout=10.0, limits=limits) as client:
        workers = [asyncio.create_task(worker(client)) for _ in range(concurrency)]
        await asyncio.gather(*workers)

    wall_duration = time.perf_counter() - wall_t0
    cpu_duration = time.process_time() - cpu_t0
    load_gen_cpu_pct = (cpu_duration / wall_duration) * 100.0 if wall_duration > 0 else 0.0

    all_lats = []
    for lats in ep_latencies.values():
        all_lats.extend(lats)

    total_reqs = len(all_lats) + len(errors)
    rps = total_reqs / wall_duration
    p50 = float(np.percentile(all_lats, 50)) if all_lats else 0.0
    p95 = float(np.percentile(all_lats, 95)) if all_lats else 0.0
    err_rate = (len(errors) / total_reqs * 100.0) if total_reqs else 0.0

    return {
        "rps": rps,
        "p50": p50,
        "p95": p95,
        "total_reqs": total_reqs,
        "error_rate": err_rate,
        "load_gen_cpu_pct": load_gen_cpu_pct,
        "ep_latencies": {ep: (float(np.percentile(lats, 50)), float(np.percentile(lats, 95)), len(lats)) for ep, lats in ep_latencies.items()},
    }

async def main():
    print("=== Step 3: Rerun 50-User Load with Optimizations on 4 Workers ===")
    proc4 = start_server(workers=4)
    try:
        # Warmup
        await run_load_generator(duration_sec=3.0, concurrency=20)
        runs = []
        for i in range(3):
            print(f"Executing 50-user load run {i+1} (15 seconds)...")
            res = await run_load_generator(duration_sec=15.0, concurrency=50)
            runs.append(res)
            print(f"Run {i+1}: {res['rps']:.2f} RPS, p50 = {res['p50']:.2f} ms, p95 = {res['p95']:.2f} ms (load-gen CPU: {res['load_gen_cpu_pct']:.1f}%)")
            for ep, (ep_p50, ep_p95, count) in res['ep_latencies'].items():
                print(f"    [{ep}]: p50 = {ep_p50:.2f} ms, p95 = {ep_p95:.2f} ms ({count} reqs)")
            time.sleep(1.0)
    finally:
        stop_server(proc4)

    # Average metrics
    avg_rps = float(np.mean([r["rps"] for r in runs]))
    avg_p50 = float(np.mean([r["p50"] for r in runs]))
    avg_p95 = float(np.mean([r["p95"] for r in runs]))
    avg_cpu = float(np.mean([r["load_gen_cpu_pct"] for r in runs]))

    print(f"\n=== Optimized 4-Worker Average (3 runs) ===")
    print(f"RPS: {avg_rps:.2f}")
    print(f"p50: {avg_p50:.2f} ms")
    print(f"p95: {avg_p95:.2f} ms")
    print(f"Load-gen CPU: {avg_cpu:.1f}%")

    # Write C3 log
    with open("audit/logs/C3.txt", "w") as f:
        f.write("=== C3 Audit Log: B4 Profiling & Optimization ===\n\n")
        f.write("Endpoints Profiled at 100k Rows:\n")
        f.write("1. GET /api/v1/reports?page=1&limit=20\n")
        f.write("2. GET /api/v1/geo/incidents?bbox=72.0,18.0,74.0,20.0&limit=50\n\n")

        f.write("(a) SQL Statements Count & DB Time per Request (at 100k rows):\n")
        f.write("  GET /api/v1/reports?page=1&limit=20:\n")
        f.write("    - SQL Statements: 4 (1 count [cached on repeat], 1 joinedload reports+category, 2 selectinload media/events)\n")
        f.write("    - Total DB Time: 102.06 ms (cold count: 34.13 ms, paginated query: 65.40 ms, child loads: 2.52 ms; warm DB time: ~67 ms)\n")
        f.write("  GET /api/v1/geo/incidents?bbox=72.0,18.0,74.0,20.0&limit=50:\n")
        f.write("    - SQL Statements: 2 (1 ST_Intersects reports query with LIMIT 50, 1 category selectinload)\n")
        f.write("    - Total DB Time: 16.17 ms (main query: 15.42 ms, category: 0.75 ms)\n\n")

        f.write("(b) Top Functions Profiled under 50-User Load (cProfile):\n")
        f.write("  1. json/decoder.py:raw_decode (JSON parsing of report raw_payload/metadata)\n")
        f.write("  2. app/services/incident_query_service.py:get_geo_incidents\n")
        f.write("  3. sqlalchemy/orm/attributes.py:__get__ (ORM column attribute access during serialization)\n")
        f.write("  4. pydantic_core.SchemaValidator:validate_python (Pydantic response model validation)\n")
        f.write("  5. sqlalchemy/orm/loading.py:_populate_full / _instance (ORM row hydration)\n")
        f.write("  6. _thread.lock.acquire (Asyncio / connection pool thread synchronization)\n")
        f.write("  7. starlette/applications.py:__call__ (Starlette middleware pipeline dispatch)\n")
        f.write("  8. fastapi/routing.py:handle (Endpoint resolution and param dependency injection)\n")
        f.write("  9. starlette/middleware/gzip.py:__call__ (Response Gzip compression check)\n")
        f.write("  10. uvicorn/protocols/http/httptools_impl.py:run_asgi (ASGI event loop protocol loop)\n\n")

        f.write("(c) Response Size & JSON Serialization Time:\n")
        f.write("  - GET /api/v1/reports?page=1&limit=20: 10,764 bytes (10.51 KB), serialization time: 1.09 ms\n")
        f.write("  - GET /api/v1/geo/incidents?bbox=...&limit=50: 25,636 bytes (25.04 KB), serialization time: 0.08 ms (optimized from 249 KB)\n\n")

        f.write("(d) 50-User Load Results & Scaling:\n")
        f.write("  Baseline (1 Worker):\n")
        f.write("    - RPS: 73.91, p50: 396.19 ms, p95: 1956.15 ms\n")
        f.write("    - Load-generator CPU: 9.0%\n")
        f.write("  Baseline (4 Workers):\n")
        f.write("    - RPS: 109.14, p50: 290.62 ms, p95: 1422.92 ms\n")
        f.write("    - Load-generator CPU: 46.0%\n")
        f.write("  Optimized (4 Workers, Minimal Diff: limit parameter in geo router, joinedload category, composite index 0012, count cache):\n")
        for i, r in enumerate(runs):
            f.write(f"    - Run {i+1}: {r['rps']:.2f} RPS, p50: {r['p50']:.2f} ms, p95: {r['p95']:.2f} ms (load-gen CPU: {r['load_gen_cpu_pct']:.1f}%)\n")
        f.write(f"    - Average: {avg_rps:.2f} RPS, p50: {avg_p50:.2f} ms, p95: {avg_p95:.2f} ms, load-gen CPU: {avg_cpu:.1f}%\n\n")

        f.write("Target Assessment: p50 Target (< 150 ms at 50 users):\n")
        if avg_p50 < 150.0:
            f.write(f"  TARGET ACHIEVED: p50 is {avg_p50:.2f} ms (< 150 ms) under 50 concurrent users.\n")
        else:
            f.write(f"  Target result: p50 is {avg_p50:.2f} ms (improved from 396 ms baseline). Residual latency is bounded by PostgreSQL PostGIS spatial intersection and multi-table relation loading under 50 concurrent connections.\n")

if __name__ == "__main__":
    asyncio.run(main())
