import asyncio, time, random, numpy as np, httpx
from collections import defaultdict

BASE_URL = "http://127.0.0.1:8001"
ENDPOINTS = [
    "/api/v1/reports?page=1&limit=20",
    "/api/v1/geo/incidents?bbox=72.0,18.0,74.0,20.0&limit=50",
]

async def worker(client, stop_time, ep_latencies, errors):
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
        except Exception:
            errors.append((ep, "timeout/exc"))

async def main():
    duration = 20.0
    ep_latencies = defaultdict(list)
    errors = []
    stop_time = time.time() + duration

    limits = httpx.Limits(max_connections=100, max_keepalive_connections=50)
    async with httpx.AsyncClient(timeout=10.0, limits=limits) as client:
        workers = [asyncio.create_task(worker(client, stop_time, ep_latencies, errors)) for _ in range(50)]
        await asyncio.gather(*workers)

    all_latencies = []
    for ep, lats in ep_latencies.items():
        all_latencies.extend(lats)

    total_reqs = len(all_latencies) + len(errors)
    rps = total_reqs / duration
    error_rate = (len(errors) / total_reqs * 100.0) if total_reqs else 0.0
    p50 = np.percentile(all_latencies, 50) if all_latencies else 0.0
    p95 = np.percentile(all_latencies, 95) if all_latencies else 0.0

    print("=== Overall B4 ===")
    print(f"Total Requests: {total_reqs}")
    print(f"RPS: {rps:.2f}")
    print(f"p50: {p50:.2f} ms")
    print(f"p95: {p95:.2f} ms")
    print(f"Error Rate: {error_rate:.2f}% ({len(errors)} errors)")

    print("\n=== Per Endpoint Metrics ===")
    per_endpoint_text = []
    for ep in ENDPOINTS:
        lats = ep_latencies.get(ep, [])
        ep_reqs = len(lats)
        ep_rps = ep_reqs / duration
        ep_p50 = np.percentile(lats, 50) if lats else 0.0
        ep_p95 = np.percentile(lats, 95) if lats else 0.0
        line = f"[{ep}] Reqs: {ep_reqs}, RPS: {ep_rps:.2f}, p50: {ep_p50:.2f} ms, p95: {ep_p95:.2f} ms"
        print(line)
        per_endpoint_text.append(line)

    with open("audit/logs/B4.txt", "w") as f:
        f.write(f"Total Requests: {total_reqs}\nRPS: {rps:.2f}\np50: {p50:.2f} ms\np95: {p95:.2f} ms\nError Rate: {error_rate:.2f}%\nErrors: {len(errors)}\n\n")
        f.write("\n".join(per_endpoint_text) + "\n")

if __name__ == "__main__":
    asyncio.run(main())
