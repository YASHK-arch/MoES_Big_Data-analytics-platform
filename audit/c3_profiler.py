import asyncio
import io
import json
import os
import pstats
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

def start_server(workers: int = 1, profile_file: str = None):
    env = os.environ.copy()
    env["PYTHONPATH"] = "back-end"
    env["DATABASE_URL"] = "postgresql+asyncpg://postgres:postgres@localhost:5432/weather_platform_audit"
    env["REDIS_URL"] = "redis://localhost:6379/5"
    env["S3_BUCKET_NAME"] = "weather-media-audit"
    env["ENVIRONMENT"] = "development"

    cmd = ["back-end/.venv/bin/python"]
    if profile_file:
        cmd.extend(["-m", "cProfile", "-o", profile_file])
    cmd.extend([
        "-m", "uvicorn", "app.main:app",
        "--host", "127.0.0.1",
        "--port", "8001",
        "--workers", str(workers),
        "--log-level", "warning",
    ])

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

async def run_load_generator(duration_sec: float = 12.0, concurrency: int = 50):
    ep_latencies = defaultdict(list)
    errors = []
    stop_time = time.time() + duration_sec

    # Measure CPU utilization of load generator
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
    print("=== Step 1: Profile 1 API Process under 50-User Load with cProfile ===")
    pstats_file = "audit/logs/b4_cprofile.pstats"
    os.makedirs("audit/logs", exist_ok=True)
    if os.path.exists(pstats_file):
        os.remove(pstats_file)

    proc1 = start_server(workers=1, profile_file=pstats_file)
    try:
        # Warmup
        await run_load_generator(duration_sec=2.0, concurrency=10)
        print("Running 50-user load for 12 seconds...")
        res1 = await run_load_generator(duration_sec=12.0, concurrency=50)
        print(f"1-worker: {res1['rps']:.2f} RPS, p50 = {res1['p50']:.2f} ms, p95 = {res1['p95']:.2f} ms")
        print(f"Load-generator CPU%: {res1['load_gen_cpu_pct']:.1f}%")
    finally:
        stop_server(proc1)

    # Read top 10 functions from cProfile
    top_functions = []
    if os.path.exists(pstats_file):
        s = io.StringIO()
        ps = pstats.Stats(pstats_file, stream=s).sort_stats("cumulative")
        ps.print_stats(15)
        stats_str = s.getvalue()
        lines = [line for line in stats_str.split("\n") if line.strip() and not line.startswith("ncalls") and not line.startswith("Ordered by")]
        for line in lines[:10]:
            top_functions.append(line)
        print("\nTop 10 Functions by Cumulative Time:")
        for fn in top_functions:
            print("  ", fn)

    print("\n=== Step 2: Rerun 50-User Load with uvicorn --workers 4 ===")
    proc4 = start_server(workers=4)
    try:
        await run_load_generator(duration_sec=2.0, concurrency=10)
        print("Running 50-user load for 12 seconds on 4 workers...")
        res4 = await run_load_generator(duration_sec=12.0, concurrency=50)
        print(f"4-workers: {res4['rps']:.2f} RPS, p50 = {res4['p50']:.2f} ms, p95 = {res4['p95']:.2f} ms")
        print(f"Load-generator CPU%: {res4['load_gen_cpu_pct']:.1f}%")
        for ep, (ep_p50, ep_p95, count) in res4['ep_latencies'].items():
            print(f"  [{ep}]: p50 = {ep_p50:.2f} ms, p95 = {ep_p95:.2f} ms ({count} reqs)")
    finally:
        stop_server(proc4)

    # Save to log
    with open("audit/logs/c3_baseline.json", "w") as f:
        json.dump({
            "worker_1": res1,
            "worker_4": res4,
            "top_functions": top_functions,
        }, f, indent=2)

if __name__ == "__main__":
    asyncio.run(main())
