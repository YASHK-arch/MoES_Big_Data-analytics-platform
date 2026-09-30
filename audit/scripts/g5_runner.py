import asyncio
import io
import os
import random
import signal
import subprocess
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent / "back-end"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import asyncpg
import httpx
import numpy as np

DB_URL = "postgresql://postgres:postgres@localhost:5432/weather_platform_audit"
BASE_URL = "http://127.0.0.1:8001"
LOG_FILE = "audit/logs/G5_indexes.txt"

ENDPOINTS = [
    "/api/v1/geo/incidents",
    "/api/v1/reports?page=1&page_size=20&status=PENDING,UNDER_REVIEW",
    "/api/v1/dashboard/summary",
    "/api/v1/incidents",
]

def log(msg=""):
    print(msg)
    with open(LOG_FILE, "a") as f:
        f.write(msg + "\n")

async def run_50_user_load(duration=20.0, concurrency=50):
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
        "total_reqs": total,
        "total_rps": total / wall,
        "errors": len(errors),
    }
    for ep in ENDPOINTS:
        lats = ep_latencies[ep]
        res[ep] = {
            "reqs": len(lats),
            "rps": len(lats) / wall,
            "p50": float(np.percentile(lats, 50)) if lats else 0.0,
            "p95": float(np.percentile(lats, 95)) if lats else 0.0,
        }
    return res

async def get_index_scans(conn):
    rows = await conn.fetch("""
        SELECT indexrelname, idx_scan, idx_tup_read, idx_tup_fetch
        FROM pg_stat_user_indexes
        WHERE relname = 'weather_reports'
        ORDER BY idx_scan DESC;
    """)
    return {r["indexrelname"]: r["idx_scan"] for r in rows}

def generate_20k_buffer(cat_id, src_id):
    random.seed(12345)
    buf = io.BytesIO()
    now = datetime(2026, 8, 29, 12, 0, tzinfo=timezone.utc)
    for i in range(20000):
        rep_id = uuid.uuid4()
        tracking_id = f"RPT-BENCH-{rep_id.hex[:12].upper()}"
        lat = 19.0 + (i % 100) * 0.01
        lon = 72.8 + (i % 100) * 0.01
        occ = (now - timedelta(hours=i % 100)).isoformat()
        point_wkt = f"SRID=4326;POINT({lon} {lat})"
        line = f"{rep_id}\t{tracking_id}\t{src_id}\t{cat_id}\tFLOOD_WATERLOGGING\tMODERATE\tBench Title {i}\tBench Desc {i}\tMumbai\t{point_wkt}\t{lat}\t{lon}\t{occ}\tCOMPLETED\tVERIFIED\t0.7500\t{occ}\t{occ}\n"
        buf.write(line.encode("utf-8"))
    buf.seek(0)
    return buf.getvalue()

def start_server():
    env = os.environ.copy()
    env["DATABASE_URL"] = "postgresql+asyncpg://postgres:postgres@localhost:5432/weather_platform_audit"
    env["REDIS_URL"] = "redis://localhost:6379/5"
    env["DASHBOARD_CACHE_TTL_SECONDS"] = "10"
    proc = subprocess.Popen(
        [
            ".venv/bin/uvicorn",
            "app.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            "8001",
            "--workers",
            "1",
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

async def measure_copy_3x(conn, data_bytes):
    times = []
    cols = [
        "id", "tracking_id", "source_id", "category_id", "reported_category",
        "severity", "title", "description", "location_name", "geom",
        "latitude", "longitude", "occurred_at", "processing_status",
        "verification_status", "credibility_score", "created_at", "updated_at"
    ]
    for run in range(1, 4):
        # Use transaction with rollback so DB doesn't retain 20k rows and state is identical
        tr = conn.transaction()
        await tr.start()
        try:
            buf = io.BytesIO(data_bytes)
            t0 = time.perf_counter()
            await conn.copy_to_table("weather_reports", source=buf, columns=cols)
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            times.append(elapsed_ms)
        finally:
            await tr.rollback()
    return times

async def main():
    os.makedirs("audit/logs", exist_ok=True)
    with open(LOG_FILE, "w") as f:
        f.write("=== G5 INDEXES AUDIT AND OPTIMIZATION ===\n\n")

    conn = await asyncpg.connect(DB_URL)
    proc = start_server()
    try:
        scans_before = await get_index_scans(conn)

        log("Running 50-user load across 4 endpoints (20s)...")
        load_res = await run_50_user_load(duration=20.0, concurrency=50)
        log(f"Load completed: Total RPS={load_res['total_rps']:.1f}, Errors={load_res['errors']}")
        for ep in ENDPOINTS:
            d = load_res[ep]
            log(f"  {ep}: RPS={d['rps']:.1f}, p50={d['p50']:.1f}ms, p95={d['p95']:.1f}ms")

        scans_after = await get_index_scans(conn)
        log("\n--- Index Scans (idx_scan delta during 50-user load) ---")
        for idx_name, scan_count in sorted(scans_after.items(), key=lambda x: x[1], reverse=True):
            delta = scan_count - scans_before.get(idx_name, 0)
            log(f"  {idx_name:40s}: total={scan_count:6d} | delta={delta:6d}")

        # Check column orders
        log("\n--- Column Order of Covering vs Dashboard Summary Indexes ---")
        idx_defs = await conn.fetch("""
            SELECT indexname, indexdef
            FROM pg_indexes
            WHERE tablename = 'weather_reports'
              AND indexname IN ('idx_weather_reports_summary_cov', 'idx_weather_reports_dashboard_summary');
        """)
        for r in idx_defs:
            log(f"  {r['indexname']}:\n    {r['indexdef']}")

        # 20k COPY benchmark before migration
        cat_id = await conn.fetchval("SELECT id FROM event_categories LIMIT 1;")
        src_id = await conn.fetchval("SELECT id FROM sources LIMIT 1;")
        data_bytes = generate_20k_buffer(cat_id, src_id)

        log("\n--- Measuring 20k COPY Before Migration (3 runs) ---")
        times_before = await measure_copy_3x(conn, data_bytes)
        log(f"  Times: {[round(t, 2) for t in times_before]} ms")
        log(f"  Median: {np.median(times_before):.2f} ms")

        # Now apply migration 0013
        log("\n--- Applying Migration 0013 (dropping duplicate indexes) ---")
        alembic_env = os.environ.copy()
        alembic_env["DATABASE_URL"] = "postgresql+asyncpg://postgres:postgres@localhost:5432/weather_platform_audit"
        res_up = subprocess.run([".venv/bin/alembic", "upgrade", "head"], cwd="back-end", env=alembic_env, capture_output=True, text=True)
        log(f"Alembic upgrade output:\n{res_up.stdout}\n{res_up.stderr}")

        # 20k COPY benchmark after migration
        log("\n--- Measuring 20k COPY After Migration 0013 (3 runs) ---")
        times_after = await measure_copy_3x(conn, data_bytes)
        log(f"  Times: {[round(t, 2) for t in times_after]} ms")
        log(f"  Median: {np.median(times_after):.2f} ms")
        speedup = ((np.median(times_before) - np.median(times_after)) / np.median(times_before)) * 100.0
        log(f"  COPY Improvement: {speedup:+.2f}%")

        # Proposed drops table (not applied)
        log("\n--- Proposed Drops Table (NOT Applied - For Future Evaluation) ---")
        log(f"{'Index Name':42s} | {'Size':10s} | {'Reason / Redundancy'}")
        log("-" * 80)
        log(f"{'ix_weather_reports_verification_status':42s} | {'768 kB':10s} | Prefix covered by idx_weather_reports_status_time & idx_weather_reports_summary_cov")
        log(f"{'ix_weather_reports_occurred_at':42s} | {'3,048 kB':10s} | Prefix covered by idx_weather_reports_occ_created")
        log(f"{'ix_weather_reports_created_at':42s} | {'3,048 kB':10s} | 0 scans; sorting uses occurred_at or composite occ_created")
        log(f"{'idx_weather_reports_dashboard_summary':42s} | {'5,816 kB':10s} | Superseded by idx_weather_reports_summary_cov for summary aggregation")

    finally:
        stop_server(proc)
        await conn.close()

if __name__ == "__main__":
    asyncio.run(main())
