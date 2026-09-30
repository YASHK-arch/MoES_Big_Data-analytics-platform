import asyncio
import gzip
import http.client
import json
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

async def run_load(duration=20.0, concurrency=50):
    stop_time = time.time() + duration
    limits = httpx.Limits(max_connections=150, max_keepalive_connections=100)
    ep_latencies = {ep: [] for ep in ENDPOINTS}
    errors = []
    
    t0_proc = time.process_time()
    t0_wall = time.perf_counter()

    async def worker(client, idx):
        while time.time() < stop_time:
            ep = ENDPOINTS[idx % len(ENDPOINTS)]
            idx += 1
            t_req = time.perf_counter()
            try:
                r = await client.get(BASE_URL + ep, headers={"Accept-Encoding": "gzip"}, timeout=10.0)
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
    wall = t1_wall - t0_wall
    cpu_pct = ((t1_proc - t0_proc) / wall) * 100.0 if wall > 0 else 0.0
    total = sum(len(l) for l in ep_latencies.values()) + len(errors)
    
    res = {
        "duration": wall,
        "total_reqs": total,
        "total_rps": total / wall,
        "cpu_pct": cpu_pct,
        "errors": len(errors),
        "endpoints": {}
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

def start_server(workers):
    proc = subprocess.Popen(
        [".venv/bin/uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8001", "--workers", str(workers), "--log-level", "warning"],
        cwd="back-end",
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

async def main(tag="baseline"):
    # 1. Measure raw and gzip size
    proc1 = start_server(1)
    conn = http.client.HTTPConnection("127.0.0.1", 8001)
    conn.request("GET", "/api/v1/geo/incidents", headers={"Accept-Encoding": "gzip"})
    resp = conn.getresponse()
    gzip_bytes = resp.read()
    raw_bytes = gzip.decompress(gzip_bytes)
    print(f"{tag.upper()} GEO PAYLOAD: Raw: {len(raw_bytes)} bytes | Gzip: {len(gzip_bytes)} bytes")
    stop_server(proc1)
    time.sleep(1)

    all_data = {"tag": tag, "payload": {"raw": len(raw_bytes), "gzip": len(gzip_bytes)}}

    for w in [1, 4]:
        print(f"\n--- Testing Workers {w} ---")
        p = start_server(w)
        runs = []
        try:
            for r in range(1, 4):
                print(f"Run {r}/3...", flush=True)
                metrics = await run_load(20.0, 50)
                runs.append(metrics)
                print(f"  Total RPS: {metrics['total_rps']:.1f} | CPU: {metrics['cpu_pct']:.1f}%")
                for ep, m in metrics["endpoints"].items():
                    print(f"    {ep}: RPS={m['rps']:.1f}, p50={m['p50']:.1f}ms, p95={m['p95']:.1f}ms")
                time.sleep(1)
        finally:
            stop_server(p)
            time.sleep(1)
        all_data[f"workers_{w}"] = runs

    filename = f"audit/logs/e3_{tag}_runs.json"
    with open(filename, "w") as f:
        json.dump(all_data, f, indent=2)
    print(f"\nSaved {tag} runs to {filename}")

if __name__ == "__main__":
    import sys
    tag = sys.argv[1] if len(sys.argv) > 1 else "baseline"
    asyncio.run(main(tag))
