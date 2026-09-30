import asyncio
import os
import signal
import subprocess
import time
import httpx
import numpy as np
import sys
sys.path.insert(0, "back-end")
from app.core.redis import AsyncRedisClient

async def test_pool_rtt(pool_size: int, concurrency: int = 50, num_requests: int = 1000):
    client = AsyncRedisClient("redis://localhost:6379/5", pool_size=pool_size)
    await client.connect()
    # prime key
    await client.set("benchmark:rtt", "test_value_123")
    
    latencies = []
    reqs_per_worker = max(1, num_requests // concurrency)

    async def worker():
        for _ in range(reqs_per_worker):
            t0 = time.perf_counter()
            val = await client.get("benchmark:rtt")
            lat = (time.perf_counter() - t0) * 1000
            if val == "test_value_123":
                latencies.append(lat)

    tasks = [asyncio.create_task(worker()) for _ in range(concurrency)]
    await asyncio.gather(*tasks)
    await client.close()

    p50 = float(np.percentile(latencies, 50)) if latencies else 0.0
    p95 = float(np.percentile(latencies, 95)) if latencies else 0.0
    p99 = float(np.percentile(latencies, 99)) if latencies else 0.0
    return len(latencies), p50, p95, p99

async def verify_db5_isolation():
    client_db5 = AsyncRedisClient("redis://localhost:6379/5", pool_size=4)
    client_db0 = AsyncRedisClient("redis://localhost:6379/0", pool_size=4)
    await client_db5.connect()
    await client_db0.connect()

    test_key = "audit:f1_check:key"
    await client_db5.set(test_key, "f1_db5_confirmed")
    
    val_in_5 = await client_db5.get(test_key)
    val_in_0 = await client_db0.get(test_key)
    
    await client_db5.delete(test_key)
    await client_db5.close()
    await client_db0.close()
    
    return val_in_5 == "f1_db5_confirmed" and val_in_0 is None

async def test_redis_restart_recovery():
    print("\nStarting uvicorn server with Redis-dependent API...")
    env = os.environ.copy()
    proc = subprocess.Popen(
        [".venv/bin/uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8001", "--log-level", "warning"],
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

    print("Verifying API initial response...")
    r_initial = httpx.get("http://127.0.0.1:8001/api/v1/dashboard/summary", timeout=5.0)
    assert r_initial.status_code == 200, f"Initial call failed: {r_initial.status_code}"

    print("Restarting docker container weather_redis...")
    t0_restart = time.perf_counter()
    subprocess.run(["docker", "restart", "weather_redis"], check=True, stdout=subprocess.DEVNULL)
    t_restart_done = time.perf_counter()
    print(f"Docker restart completed in {t_restart_done - t0_restart:.2f} s")

    # Poll API until recovery without restarting the API process
    t0_probe = time.perf_counter()
    recovered = False
    recovery_time = 0.0
    attempts = 0
    while time.perf_counter() - t0_probe < 15.0:
        attempts += 1
        try:
            r = httpx.get("http://127.0.0.1:8001/api/v1/dashboard/summary", timeout=1.0)
            if r.status_code == 200:
                recovery_time = time.perf_counter() - t0_probe
                recovered = True
                break
        except Exception:
            pass
        await asyncio.sleep(0.2)

    # Clean up uvicorn
    try:
        os.kill(proc.pid, signal.SIGTERM)
        proc.wait(timeout=5)
    except Exception:
        try:
            os.kill(proc.pid, signal.SIGKILL)
        except Exception:
            pass

    return recovered, recovery_time, attempts

async def main():
    print("=== E4.1: DB 5 Isolation & SELECT <db> Check ===")
    f1_verified = await verify_db5_isolation()
    print(f"DB 5 isolation verified (F1 holds): {f1_verified}")

    print("\n=== E4.2: Redis Pool RTT at Concurrency 50 for pool sizes 4, 8, 16 ===")
    rtt_results = {}
    for ps in [4, 8, 16]:
        reqs, p50, p95, p99 = await test_pool_rtt(pool_size=ps, concurrency=50, num_requests=1000)
        rtt_results[ps] = {"reqs": reqs, "p50": p50, "p95": p95, "p99": p99}
        print(f"Pool size {ps:2d}: {reqs} reqs | p50={p50:.2f} ms | p95={p95:.2f} ms | p99={p99:.2f} ms")

    print("\n=== E4.3: Redis Restart & Auto-reconnection Test ===")
    recovered, rec_time, attempts = await test_redis_restart_recovery()
    print(f"API auto-recovered without restart: {recovered}")
    print(f"Recovery time: {rec_time:.2f} s ({attempts} attempts)")

    with open("audit/logs/E4.txt", "w") as f:
        f.write("=== E4 Redis Pool Audit ===\n")
        f.write("1. Pool Size & Queue Behavior:\n")
        f.write("   - Default Pool Size: 8\n")
        f.write("   - Busy Behavior: asyncio.Queue(maxsize=pool_size) queues callers via `await self._pool.get()` (no errors thrown)\n")
        f.write(f"   - DB 5 Selection (F1): Verified={f1_verified} (each pooled connection executes SELECT <db> upon connection)\n\n")
        f.write("2. RTT at Concurrency 50:\n")
        for ps, r in rtt_results.items():
            f.write(f"   - Pool {ps:2d}: p50={r['p50']:.2f} ms, p95={r['p95']:.2f} ms, p99={r['p99']:.2f} ms\n")
        f.write(f"\n3. Redis Restart Recovery:\n")
        f.write(f"   - Auto-reconnect without API restart: {recovered}\n")
        f.write(f"   - Recovery time: {rec_time:.2f} s\n")

if __name__ == "__main__":
    asyncio.run(main())
