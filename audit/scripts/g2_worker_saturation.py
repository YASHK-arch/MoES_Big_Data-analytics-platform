import asyncio
import os
import signal
import subprocess
import time
import asyncpg
import httpx
import numpy as np

DB_URL = "postgresql://postgres:postgres@localhost:5432/weather_platform_audit"
ENDPOINTS = [
    "/api/v1/geo/incidents",
    "/api/v1/reports?page=1&page_size=20&status=PENDING,UNDER_REVIEW",
]
BASE_URL = "http://127.0.0.1:8001"

def get_process_cpu_and_pids(name_pattern):
    try:
        out = subprocess.check_output(["ps", "-A", "-o", "%cpu,pid,command"], text=True)
        cpus = []
        for line in out.splitlines():
            if name_pattern in line and "grep" not in line and "g2_worker_saturation" not in line:
                parts = line.strip().split(None, 2)
                if len(parts) >= 2:
                    try:
                        cpus.append(float(parts[0]))
                    except ValueError:
                        pass
        return sum(cpus)
    except Exception:
        return 0.0

async def sample_postgres_activity(conn):
    rows = await conn.fetch("""
        SELECT count(*) FILTER (WHERE state = 'active') AS active_count,
               count(*) FILTER (WHERE wait_event IS NOT NULL AND state = 'active') AS waiting_count
        FROM pg_stat_activity
        WHERE datname = 'weather_platform_audit' AND pid != pg_backend_pid();
    """)
    return rows[0]["active_count"] or 0, rows[0]["waiting_count"] or 0

async def run_load_with_sampling(duration=15.0, concurrency=50):
    stop_time = time.time() + duration
    limits = httpx.Limits(max_connections=150, max_keepalive_connections=100)
    
    conn = await asyncpg.connect(DB_URL)
    pg_active_samples = []
    pg_waiting_samples = []
    pg_cpu_samples = []
    api_cpu_samples = []

    async def sampler():
        while time.time() < stop_time:
            act, wait = await sample_postgres_activity(conn)
            pg_active_samples.append(act)
            pg_waiting_samples.append(wait)
            pg_cpu_samples.append(get_process_cpu_and_pids("postgres"))
            api_cpu_samples.append(get_process_cpu_and_pids("uvicorn"))
            await asyncio.sleep(0.5)

    async def worker(client, idx):
        while time.time() < stop_time:
            ep = ENDPOINTS[idx % len(ENDPOINTS)]
            idx += 1
            try:
                await client.get(BASE_URL + ep, headers={"Accept-Encoding": "gzip"}, timeout=10.0)
            except Exception:
                pass

    sampler_task = asyncio.create_task(sampler())
    async with httpx.AsyncClient(limits=limits) as client:
        workers = [asyncio.create_task(worker(client, i)) for i in range(concurrency)]
        await asyncio.gather(*workers)
    await sampler_task
    await conn.close()

    return {
        "pg_active_avg": np.mean(pg_active_samples) if pg_active_samples else 0.0,
        "pg_active_max": max(pg_active_samples) if pg_active_samples else 0,
        "pg_waiting_avg": np.mean(pg_waiting_samples) if pg_waiting_samples else 0.0,
        "pg_waiting_max": max(pg_waiting_samples) if pg_waiting_samples else 0,
        "pg_cpu_avg": np.mean(pg_cpu_samples) if pg_cpu_samples else 0.0,
        "pg_cpu_max": max(pg_cpu_samples) if pg_cpu_samples else 0.0,
        "api_cpu_avg": np.mean(api_cpu_samples) if api_cpu_samples else 0.0,
        "api_cpu_max": max(api_cpu_samples) if api_cpu_samples else 0.0,
    }

def start_server(workers):
    env = os.environ.copy()
    proc = subprocess.Popen(
        [".venv/bin/uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8001", "--workers", str(workers), "--log-level", "warning"],
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
    results = {}
    for w in [1, 4]:
        print(f"\nSampling load for --workers {w}...")
        proc = start_server(w)
        try:
            # Let warm up 2s
            await asyncio.sleep(2)
            metrics = await run_load_with_sampling(duration=15.0, concurrency=50)
            results[f"workers_{w}"] = metrics
            print(f"Workers {w} Results:")
            print(f"  Postgres Active DB Conns: avg={metrics['pg_active_avg']:.1f}, max={metrics['pg_active_max']}")
            print(f"  Postgres Waiting Conns: avg={metrics['pg_waiting_avg']:.1f}, max={metrics['pg_waiting_max']}")
            print(f"  Postgres CPU%: avg={metrics['pg_cpu_avg']:.1f}%, max={metrics['pg_cpu_max']:.1f}%")
            print(f"  API Process CPU%: avg={metrics['api_cpu_avg']:.1f}%, max={metrics['api_cpu_max']:.1f}%")
        finally:
            stop_server(proc)
            time.sleep(1)

    with open("audit/logs/G2_saturation.txt", "w") as f:
        f.write("=== G2 (d) Why 4 Workers Did Not Beat 1: Resource Saturation Profile ===\n\n")
        for w, m in results.items():
            f.write(f"--- {w} ---\n")
            f.write(f"Postgres Active Conns: avg={m['pg_active_avg']:.1f}, max={m['pg_active_max']}\n")
            f.write(f"Postgres Waiting Conns: avg={m['pg_waiting_avg']:.1f}, max={m['pg_waiting_max']}\n")
            f.write(f"Postgres CPU%: avg={m['pg_cpu_avg']:.1f}%, max={m['pg_cpu_max']:.1f}%\n")
            f.write(f"API CPU%: avg={m['api_cpu_avg']:.1f}%, max={m['api_cpu_max']:.1f}%\n\n")

if __name__ == "__main__":
    asyncio.run(main())
