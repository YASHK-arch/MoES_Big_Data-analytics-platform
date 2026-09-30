import asyncio
import os
import signal
import subprocess
import time
import httpx
import numpy as np

ENDPOINTS = [
    "/api/v1/geo/incidents",
    "/api/v1/reports?page=1&page_size=20&status=PENDING,UNDER_REVIEW",
]

BASE_URL = "http://127.0.0.1:8001"

async def run_single_load_test(duration: float = 20.0, concurrency: int = 50):
    stop_time = time.time() + duration
    limits = httpx.Limits(max_connections=150, max_keepalive_connections=100)
    
    ep_latencies = {ep: [] for ep in ENDPOINTS}
    errors = []
    
    t0_proc = time.process_time()
    t0_wall = time.perf_counter()

    async def worker(client, idx):
        # alternate endpoints or round-robin
        while time.time() < stop_time:
            ep = ENDPOINTS[idx % len(ENDPOINTS)]
            idx += 1
            t_req = time.perf_counter()
            try:
                r = await client.get(
                    BASE_URL + ep,
                    headers={"Accept-Encoding": "gzip"},
                    timeout=10.0,
                )
                lat = (time.perf_counter() - t_req) * 1000
                if r.status_code == 200:
                    ep_latencies[ep].append(lat)
                else:
                    errors.append((ep, r.status_code))
            except Exception as e:
                errors.append((ep, str(e)))

    async with httpx.AsyncClient(limits=limits) as client:
        workers = [asyncio.create_task(worker(client, i)) for i in range(concurrency)]
        await asyncio.gather(*workers)

    t1_proc = time.process_time()
    t1_wall = time.perf_counter()
    wall_duration = t1_wall - t0_wall
    cpu_pct = ((t1_proc - t0_proc) / wall_duration) * 100.0 if wall_duration > 0 else 0.0

    total_reqs = sum(len(l) for l in ep_latencies.values()) + len(errors)
    rps = total_reqs / wall_duration if wall_duration > 0 else 0.0

    metrics = {
        "duration": wall_duration,
        "total_reqs": total_reqs,
        "rps": rps,
        "cpu_pct": cpu_pct,
        "errors": len(errors),
        "endpoints": {}
    }

    for ep in ENDPOINTS:
        lats = ep_latencies[ep]
        ep_reqs = len(lats)
        ep_rps = ep_reqs / wall_duration if wall_duration > 0 else 0.0
        p50 = float(np.percentile(lats, 50)) if lats else 0.0
        p95 = float(np.percentile(lats, 95)) if lats else 0.0
        p99 = float(np.percentile(lats, 99)) if lats else 0.0
        metrics["endpoints"][ep] = {
            "reqs": ep_reqs,
            "rps": ep_rps,
            "p50": p50,
            "p95": p95,
            "p99": p99,
        }

    return metrics

def run_server(workers: int):
    env = os.environ.copy()
    proc = subprocess.Popen(
        [
            ".venv/bin/uvicorn",
            "app.main:app",
            "--host", "127.0.0.1",
            "--port", "8001",
            "--workers", str(workers),
            "--log-level", "warning",
        ],
        cwd="back-end",
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    # Wait for server ready
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

async def test_suite(workers_list=[1, 4]):
    results = {}
    for w in workers_list:
        print(f"\n==========================================")
        print(f"Starting server with --workers {w}...")
        proc = run_server(w)
        try:
            w_runs = []
            for run_idx in range(1, 4):
                print(f"  Run {run_idx}/3 (20s, 50 users)...", end="", flush=True)
                metrics = await run_single_load_test(duration=20.0, concurrency=50)
                print(f" Done! Total RPS: {metrics['rps']:.1f}, CPU: {metrics['cpu_pct']:.1f}%")
                w_runs.append(metrics)
                if run_idx < 3:
                    await asyncio.sleep(2.0)
            results[f"workers_{w}"] = w_runs
        finally:
            stop_server(proc)
            await asyncio.sleep(1.0)
    return results

if __name__ == "__main__":
    res = asyncio.run(test_suite([1, 4]))
    print("\nSummary results collected.")
