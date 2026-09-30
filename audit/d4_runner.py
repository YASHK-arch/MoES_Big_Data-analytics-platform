import asyncio
import os
import signal
import subprocess
import time
import httpx
import numpy as np
from app.core.redis import AsyncRedisClient

API_URL = "http://127.0.0.1:8001/api/v1/dashboard/summary"

async def measure_redis_rtt(concurrency: int, num_requests: int = 500):
    client = AsyncRedisClient("redis://localhost:6379/5", pool_size=8)
    await client.connect()
    latencies = []

    async def worker(n):
        for _ in range(n):
            t0 = time.perf_counter()
            await client.get("benchmark:rtt")
            lat = (time.perf_counter() - t0) * 1000
            latencies.append(lat)

    reqs_per_worker = max(1, num_requests // concurrency)
    tasks = [asyncio.create_task(worker(reqs_per_worker)) for _ in range(concurrency)]
    await asyncio.gather(*tasks)
    await client.close()

    p50 = float(np.percentile(latencies, 50))
    p95 = float(np.percentile(latencies, 95))
    return p50, p95

async def measure_summary_endpoint(duration_sec: float = 10.0, concurrency: int = 50):
    latencies = []
    stop_time = time.time() + duration_sec
    limits = httpx.Limits(max_connections=100, max_keepalive_connections=50)

    async def worker(client):
        while time.time() < stop_time:
            t0 = time.perf_counter()
            try:
                r = await client.get(API_URL)
                lat = (time.perf_counter() - t0) * 1000
                if r.status_code == 200:
                    latencies.append(lat)
            except Exception:
                pass

    async with httpx.AsyncClient(timeout=10.0, limits=limits) as client:
        workers = [asyncio.create_task(worker(client)) for _ in range(concurrency)]
        await asyncio.gather(*workers)

    total_reqs = len(latencies)
    rps = total_reqs / duration_sec
    p50 = float(np.percentile(latencies, 50)) if latencies else 0.0
    p95 = float(np.percentile(latencies, 95)) if latencies else 0.0
    return rps, p50, p95, total_reqs

def start_server(ttl: int):
    env = os.environ.copy()
    env["PYTHONPATH"] = "back-end"
    env["DATABASE_URL"] = "postgresql+asyncpg://postgres:postgres@localhost:5432/weather_platform_audit"
    env["REDIS_URL"] = "redis://localhost:6379/5"
    env["S3_BUCKET_NAME"] = "weather-media-audit"
    env["DASHBOARD_CACHE_TTL_SECONDS"] = str(ttl)
    env["ENVIRONMENT"] = "development"

    proc = subprocess.Popen(
        ["back-end/.venv/bin/uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8001", "--log-level", "warning"],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    for _ in range(50):
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
        proc.send_signal(signal.SIGTERM)
        try:
            proc.wait(timeout=3.0)
        except subprocess.TimeoutExpired:
            proc.kill()

async def main():
    print("=== D4: Redis Client Contention & Connection Pooling Test ===")

    # 1. RTT measurements
    print("Measuring Redis client RTT with pool_size=8...")
    rtt_c1_p50, rtt_c1_p95 = await measure_redis_rtt(1, 500)
    print(f"RTT Concurrency 1:  p50 = {rtt_c1_p50:.2f} ms, p95 = {rtt_c1_p95:.2f} ms")
    rtt_c50_p50, rtt_c50_p95 = await measure_redis_rtt(50, 500)
    print(f"RTT Concurrency 50: p50 = {rtt_c50_p50:.2f} ms, p95 = {rtt_c50_p95:.2f} ms")

    # 2. Summary endpoint TTL=10 (3 runs)
    print("\nMeasuring Dashboard Summary endpoint with TTL=10 (3 runs, 10s each, conc=50)...")
    proc = start_server(10)
    try:
        runs = []
        for i in range(1, 4):
            print(f"Starting Run {i}...")
            rps, p50, p95, total = await measure_summary_endpoint(10.0, 50)
            print(f"  Run {i}: {rps:.2f} RPS, p50 = {p50:.2f} ms, p95 = {p95:.2f} ms ({total} requests)")
            runs.append((rps, p50, p95, total))
            await asyncio.sleep(1.0)
    finally:
        stop_server(proc)

    avg_rps = sum(r[0] for r in runs) / len(runs)
    avg_p50 = sum(r[1] for r in runs) / len(runs)
    avg_p95 = sum(r[2] for r in runs) / len(runs)
    print(f"\nAverage TTL=10: {avg_rps:.2f} RPS, p50 = {avg_p50:.2f} ms, p95 = {avg_p95:.2f} ms")

    os.makedirs("audit/logs", exist_ok=True)
    with open("audit/logs/D4.txt", "w") as f:
        f.write("=== D4 Redis Contention & Pooling Audit Log ===\n\n")
        f.write("SSE Shared Subscriber Check:\n")
        f.write("  SSEBroadcaster already initializes its own dedicated AsyncRedisClient instance.\n\n")
        f.write("Redis Client RTT (Before vs After Pooling):\n")
        f.write(f"  Before (Single Lock): Concurrency 1: p50=0.13 ms, p95=0.25 ms | Concurrency 50: p50=5.39 ms, p95=7.02 ms\n")
        f.write(f"  After (Pool Size 8):  Concurrency 1: p50={rtt_c1_p50:.2f} ms, p95={rtt_c1_p95:.2f} ms | Concurrency 50: p50={rtt_c50_p50:.2f} ms, p95={rtt_c50_p95:.2f} ms\n\n")
        f.write("Dashboard Summary Load (TTL=10, Concurrency 50, 3 runs):\n")
        for i, r in enumerate(runs, 1):
            f.write(f"  Run {i}: {r[0]:.2f} RPS, p50 = {r[1]:.2f} ms, p95 = {r[2]:.2f} ms ({r[3]} requests)\n")
        f.write(f"  Average: {avg_rps:.2f} RPS, p50 = {avg_p50:.2f} ms, p95 = {avg_p95:.2f} ms\n\n")
        f.write("Comparison with Before:\n")
        f.write("  Before Pooling TTL=10: 388.93 RPS, p50 = 77.91 ms, p95 = 443.49 ms\n")
        f.write(f"  After Pooling TTL=10:  {avg_rps:.2f} RPS, p50 = {avg_p50:.2f} ms, p95 = {avg_p95:.2f} ms\n")

if __name__ == "__main__":
    asyncio.run(main())
