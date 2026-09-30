import asyncio, subprocess, httpx, time

STREAM_URL = "http://127.0.0.1:8001/api/v1/events/stream"
REPORT_URL = "http://127.0.0.1:8001/api/v1/reports"

def get_redis_conn_count():
    try:
        out = subprocess.check_output("docker exec weather_redis redis-cli CLIENT LIST | wc -l", shell=True)
        return int(out.decode().strip())
    except Exception:
        return -1

async def sse_client(client_id, stop_event, event_counts):
    event_counts[client_id] = 0
    try:
        async with httpx.AsyncClient(timeout=None) as client:
            async with client.stream("GET", STREAM_URL) as response:
                async for line in response.aiter_lines():
                    if stop_event.is_set():
                        break
                    if line.startswith("event:"):
                        event_counts[client_id] += 1
    except Exception:
        pass

async def create_reports(n=5):
    async with httpx.AsyncClient(timeout=10.0) as client:
        for i in range(n):
            data = {
                'latitude': '19.0760',
                'longitude': '72.8777',
                'category_code': 'FLOOD_WATERLOGGING',
                'severity': 'MODERATE',
                'title': f'SSE Test Report {i}',
                'location_name': 'Mumbai',
            }
            try:
                await client.post(REPORT_URL, data=data)
            except Exception:
                pass
            await asyncio.sleep(0.2)

async def main():
    conn_before = get_redis_conn_count()
    print(f"Redis connections before: {conn_before}")

    stop_event = asyncio.Event()
    event_counts = {}

    # Start 50 SSE clients
    tasks = [asyncio.create_task(sse_client(i, stop_event, event_counts)) for i in range(50)]
    
    # Wait for connections to establish
    await asyncio.sleep(2.0)
    conn_during = get_redis_conn_count()
    print(f"Redis connections during: {conn_during}")

    # Create 5 reports
    print("Creating 5 reports...")
    await create_reports(5)

    # Allow stream delivery
    await asyncio.sleep(4.0)

    # Stop clients
    stop_event.set()
    for t in tasks:
        t.cancel()

    counts = list(event_counts.values())
    min_recv = min(counts) if counts else 0
    max_recv = max(counts) if counts else 0
    avg_recv = sum(counts) / len(counts) if counts else 0

    print(f"Clients count: {len(counts)}")
    print(f"Min events received: {min_recv}")
    print(f"Max events received: {max_recv}")
    print(f"Avg events received: {avg_recv:.1f}")

    with open("audit/logs/B5.txt", "w") as f:
        f.write(f"Redis connections before: {conn_before}\nRedis connections during: {conn_during}\nMin events received: {min_recv}\nMax events received: {max_recv}\n")

if __name__ == "__main__":
    asyncio.run(main())
