import asyncio, time, numpy as np, httpx
import asyncpg

DB_URL = "postgresql://postgres:postgres@localhost:5432/weather_platform_audit"
API_URL = "http://127.0.0.1:8001/api/v1/dashboard/summary"

async def monitor_connections(duration, conn_counts):
    conn = await asyncpg.connect(DB_URL)
    start = time.time()
    try:
        while time.time() - start < duration:
            val = await conn.fetchval("SELECT count(*) FROM pg_stat_activity WHERE datname = 'weather_platform_audit';")
            conn_counts.append(val)
            await asyncio.sleep(1.0)
    finally:
        await conn.close()

async def worker(client, stop_time, latencies):
    while time.time() < stop_time:
        t0 = time.perf_counter()
        try:
            r = await client.get(API_URL)
            lat = (time.perf_counter() - t0) * 1000
            if r.status_code == 200:
                latencies.append(lat)
        except Exception:
            pass

async def main():
    duration = 20.0
    conn_counts = []
    latencies = []
    stop_time = time.time() + duration

    monitor_task = asyncio.create_task(monitor_connections(duration, conn_counts))

    limits = httpx.Limits(max_connections=100, max_keepalive_connections=50)
    async with httpx.AsyncClient(timeout=10.0, limits=limits) as client:
        workers = [asyncio.create_task(worker(client, stop_time, latencies)) for _ in range(50)]
        await asyncio.gather(*workers)

    await monitor_task

    total_reqs = len(latencies)
    rps = total_reqs / duration
    p50 = np.percentile(latencies, 50) if latencies else 0
    p95 = np.percentile(latencies, 95) if latencies else 0
    max_conns = max(conn_counts) if conn_counts else 0

    print(f"Max Connections: {max_conns}")
    print(f"Total Requests: {total_reqs}")
    print(f"RPS: {rps:.2f}")
    print(f"p50: {p50:.2f} ms")
    print(f"p95: {p95:.2f} ms")
    print(f"Sampled DB Connections: {conn_counts}")

    with open("audit/logs/B1.txt", "w") as f:
        f.write(f"Max Connections: {max_conns}\nRPS: {rps:.2f}\np50: {p50:.2f} ms\np95: {p95:.2f} ms\nSampled: {conn_counts}\n")

if __name__ == "__main__":
    asyncio.run(main())
