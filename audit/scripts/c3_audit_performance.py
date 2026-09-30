"""audit/scripts/c3_audit_performance.py — Benchmark unfiltered incident list (page 1 and page 500) on audit DB."""

import asyncio
import re
import sys
import time
from pathlib import Path

BACKEND_DIR = Path('/Users/akshatjain/Documents/SIH/back-end')
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import asyncpg
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from app.services.incident_query_service import incident_query_service

AUDIT_DB_ASYNC_URL = "postgresql+asyncpg://postgres:postgres@localhost:5432/weather_platform_audit"
AUDIT_DB_PG_URL = "postgresql://postgres:postgres@localhost:5432/weather_platform_audit"

async def run_benchmark():
    print("=" * 60)
    print("C3 BENCHMARK: UNFILTERED INCIDENT LIST ON AUDIT DB")
    print("=" * 60)
    
    # 1. SQL EXPLAIN (ANALYZE, BUFFERS)
    conn = await asyncpg.connect(AUDIT_DB_PG_URL)
    row_count = await conn.fetchval("SELECT count(*) FROM weather_reports")
    print(f"Total rows in weather_reports (audit DB): {row_count}")

    q_p1 = """
    EXPLAIN (ANALYZE, BUFFERS)
    SELECT id, tracking_id, title, occurred_at, created_at, severity, verification_status, credibility_score
    FROM weather_reports
    ORDER BY occurred_at DESC, id DESC
    LIMIT 20;
    """

    q_p500 = """
    EXPLAIN (ANALYZE, BUFFERS)
    SELECT id, tracking_id, title, occurred_at, created_at, severity, verification_status, credibility_score
    FROM weather_reports
    ORDER BY occurred_at DESC, id DESC
    OFFSET 9980 LIMIT 20;
    """

    print("\n1. Pure PostgreSQL EXPLAIN ANALYZE Execution Times (3 runs each):")
    sql_p1_times = []
    for i in range(3):
        rows = await conn.fetch(q_p1)
        plan = "\n".join([r[0] for r in rows])
        m = re.search(r"Execution Time:\s+([\d\.]+)\s+ms", plan)
        t = float(m.group(1)) if m else 0.0
        sql_p1_times.append(t)
        print(f"   Page 1, Run {i+1}: {t:.3f} ms")

    sql_p500_times = []
    for i in range(3):
        rows = await conn.fetch(q_p500)
        plan = "\n".join([r[0] for r in rows])
        m = re.search(r"Execution Time:\s+([\d\.]+)\s+ms", plan)
        t = float(m.group(1)) if m else 0.0
        sql_p500_times.append(t)
        print(f"   Page 500, Run {i+1}: {t:.3f} ms")

    await conn.close()

    # 2. Application Service Layer (list_incidents with serialization & count)
    print("\n2. Service Layer (incident_query_service.list_incidents) (3 runs each):")
    engine = create_async_engine(AUDIT_DB_ASYNC_URL, echo=False)
    session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    app_p1_times = []
    for i in range(3):
        t0 = time.perf_counter()
        async with session_maker() as session:
            summaries, total, pages, has_next, has_prev = await incident_query_service.list_incidents(
                session=session,
                page=1,
                page_size=20,
            )
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        app_p1_times.append(elapsed_ms)
        print(f"   Page 1, Run {i+1}: {elapsed_ms:.2f} ms (returned {len(summaries)} items, total={total})")

    app_p500_times = []
    for i in range(3):
        t0 = time.perf_counter()
        async with session_maker() as session:
            summaries, total, pages, has_next, has_prev = await incident_query_service.list_incidents(
                session=session,
                page=500,
                page_size=20,
            )
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        app_p500_times.append(elapsed_ms)
        print(f"   Page 500, Run {i+1}: {elapsed_ms:.2f} ms (returned {len(summaries)} items, total={total})")

    await engine.dispose()

    print("\n" + "=" * 60)
    print("SUMMARY METRICS:")
    print(f"  SQL Page 1:   {[round(t, 2) for t in sql_p1_times]} ms | avg = {sum(sql_p1_times)/3:.2f} ms")
    print(f"  SQL Page 500: {[round(t, 2) for t in sql_p500_times]} ms | avg = {sum(sql_p500_times)/3:.2f} ms")
    print(f"  App Page 1:   {[round(t, 2) for t in app_p1_times]} ms | avg = {sum(app_p1_times)/3:.2f} ms")
    print(f"  App Page 500: {[round(t, 2) for t in app_p500_times]} ms | avg = {sum(app_p500_times)/3:.2f} ms")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(run_benchmark())
