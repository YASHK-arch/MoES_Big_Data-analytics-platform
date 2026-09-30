import asyncio
import os
import signal
import subprocess
import sys
import time
import httpx
import numpy as np

ENDPOINTS = [
    "/api/v1/geo/incidents",
    "/api/v1/reports?page=1&page_size=20&status=PENDING,UNDER_REVIEW",
]
BASE_URL = "http://127.0.0.1:8001"

async def run_load(duration=20.0, concurrency=50):
    stop_time = time.time() + duration
    limits = httpx.Limits(max_connections=150, max_keepalive_connections=100)
    ep_latencies = {ep: [] for ep in ENDPOINTS}
    errors = []

    async def worker(client, idx):
        while time.time() < stop_time:
            ep = ENDPOINTS[idx % len(ENDPOINTS)]
            idx += 1
            t_req = time.perf_counter()
            try:
                r = await client.get(BASE_URL + ep, headers={"Accept-Encoding": "gzip"}, timeout=10.0)
                lat = (time.perf_counter() - t_req) * 1000.0
                if r.status_code == 200:
                    ep_latencies[ep].append(lat)
                else:
                    errors.append((ep, r.status_code))
            except Exception as e:
                errors.append((ep, str(e)))

    async with httpx.AsyncClient(limits=limits) as client:
        workers = [asyncio.create_task(worker(client, i)) for i in range(concurrency)]
        await asyncio.gather(*workers)

    wall = duration
    total = sum(len(l) for l in ep_latencies.values()) + len(errors)
    res = {
        "wall": wall,
        "total_reqs": total,
        "total_rps": total / wall,
        "errors": len(errors),
        "endpoints": {},
    }
    for ep in ENDPOINTS:
        lats = ep_latencies[ep]
        res["endpoints"][ep] = {
            "reqs": len(lats),
            "rps": len(lats) / wall,
            "p50": float(np.percentile(lats, 50)) if lats else 0.0,
            "p95": float(np.percentile(lats, 95)) if lats else 0.0,
        }
    return res

def start_server(workers, cache_ttl):
    env = os.environ.copy()
    env["DATABASE_URL"] = "postgresql+asyncpg://postgres:postgres@localhost:5432/weather_platform_audit"
    env["REDIS_URL"] = "redis://localhost:6379/5"
    env["DASHBOARD_CACHE_TTL_SECONDS"] = str(cache_ttl)
    proc = subprocess.Popen(
        [
            ".venv/bin/uvicorn",
            "app.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            "8001",
            "--workers",
            str(workers),
            "--log-level",
            "warning",
        ],
        cwd="back-end",
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    for _ in range(30):
        try:
            r = httpx.get("http://127.0.0.1:8001/api/v1/health", timeout=1.0)
            if r.status_code == 200:
                break
        except Exception:
            time.sleep(0.5)
    return proc

def stop_server(proc):
    try:
        os.kill(proc.pid, signal.SIGTERM)
        proc.wait(timeout=5)
    except Exception:
        try:
            os.kill(proc.pid, signal.SIGKILL)
        except Exception:
            pass

async def main():
    configs = [
        ("workers_1_cache_on", 1, 10),
        ("workers_1_cache_off", 1, 0),
        ("workers_4_cache_on", 4, 10),
        ("workers_4_cache_off", 4, 0),
    ]

    all_results = {}

    for name, workers, cache_ttl in configs:
        print(f"\n==========================================")
        print(f"Starting {name}: workers={workers}, cache_ttl={cache_ttl}")
        print(f"==========================================")
        proc = start_server(workers, cache_ttl)
        runs = []
        try:
            # Warm up
            print("Warming up server (5s)...")
            await run_load(duration=5.0, concurrency=10)

            for run_idx in range(1, 4):
                print(f"  Run {run_idx}/3 (20s, 50 users)...")
                res = await run_load(duration=20.0, concurrency=50)
                runs.append(res)
                print(f"    Total RPS: {res['total_rps']:.1f}")
                for ep, d in res["endpoints"].items():
                    print(f"      {ep}: RPS={d['rps']:.1f}, p50={d['p50']:.1f}ms, p95={d['p95']:.1f}ms")
                if run_idx < 3:
                    await asyncio.sleep(2.0)
        finally:
            stop_server(proc)
            time.sleep(1.0)

        all_results[name] = runs

    # Summary table
    print("\n\n==================== SUMMARY ====================")
    for name, runs in all_results.items():
        print(f"\nConfiguration: {name}")
        for ep in ENDPOINTS:
            rpss = [r["endpoints"][ep]["rps"] for r in runs]
            p50s = [r["endpoints"][ep]["p50"] for r in runs]
            p95s = [r["endpoints"][ep]["p95"] for r in runs]
            print(f"  {ep}:")
            print(f"    RPS: median={np.median(rpss):.1f} (runs: {[round(x,1) for x in rpss]})")
            print(f"    p50: median={np.median(p50s):.1f} ms (runs: {[round(x,1) for x in p50s]})")
            print(f"    p95: median={np.median(p95s):.1f} ms (runs: {[round(x,1) for x in p95s]})")

if __name__ == "__main__":
    asyncio.run(main())
