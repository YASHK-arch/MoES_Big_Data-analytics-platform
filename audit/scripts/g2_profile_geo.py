import asyncio
import gzip
import json
import sys
import time
sys.path.insert(0, "back-end")

import asyncpg
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from app.services.incident_query_service import incident_query_service

DB_URL = "postgresql+asyncpg://postgres:postgres@localhost:5432/weather_platform_audit"
RAW_PG_URL = "postgresql://postgres:postgres@localhost:5432/weather_platform_audit"

EXPLAIN_QUERY = """
EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT)
SELECT *
FROM weather_reports
WHERE weather_reports.geom IS NOT NULL
ORDER BY weather_reports.occurred_at DESC NULLS LAST, weather_reports.created_at DESC
LIMIT 500;
"""

async def run_g2_breakdown():
    # 1. EXPLAIN (ANALYZE, BUFFERS)
    conn = await asyncpg.connect(RAW_PG_URL)
    rows = await conn.fetch(EXPLAIN_QUERY)
    plan_text = "\n".join([r[0] for r in rows])
    await conn.close()

    # 2. End-to-end breakdown using SQLAlchemy
    engine = create_async_engine(DB_URL, echo=False)
    session_factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

    timings = []
    # Warm up
    async with session_factory() as session:
        await incident_query_service.get_geo_incidents(session=session, limit=500)

    # 3 repetitions
    for _ in range(3):
        t0 = time.perf_counter()
        async with session_factory() as session:
            t_db_0 = time.perf_counter()
            geojson = await incident_query_service.get_geo_incidents(session=session, limit=500)
            t_db_1 = time.perf_counter()

        t_ser_0 = time.perf_counter()
        raw_json_str = geojson.model_dump_json()
        raw_bytes = raw_json_str.encode("utf-8")
        t_ser_1 = time.perf_counter()

        # Measure gzip default (level 9 in python gzip default or compresslevel=6) vs compresslevel=4
        t_gz_curr_0 = time.perf_counter()
        gz_curr = gzip.compress(raw_bytes)
        t_gz_curr_1 = time.perf_counter()

        t_gz_lvl4_0 = time.perf_counter()
        gz_lvl4 = gzip.compress(raw_bytes, compresslevel=4)
        t_gz_lvl4_1 = time.perf_counter()

        t_total = time.perf_counter() - t0

        timings.append({
            "db_ms": (t_db_1 - t_db_0) * 1000,
            "ser_ms": (t_ser_1 - t_ser_0) * 1000,
            "gz_curr_ms": (t_gz_curr_1 - t_gz_curr_0) * 1000,
            "gz_lvl4_ms": (t_gz_lvl4_1 - t_gz_lvl4_0) * 1000,
            "raw_size": len(raw_bytes),
            "gz_curr_size": len(gz_curr),
            "gz_lvl4_size": len(gz_lvl4),
            "total_ms": t_total * 1000,
        })

    await engine.dispose()

    # Averages
    avg = {k: sum(t[k] for t in timings) / len(timings) for k in timings[0]}
    
    print("=== G2 (a) Breakdown (Average of 3 runs) ===")
    print(f"SQL statements: 2 (1 main query + 1 selectinload category query)")
    print(f"DB Query time: {avg['db_ms']:.2f} ms")
    print(f"Pydantic Serialization time: {avg['ser_ms']:.2f} ms")
    print(f"Gzip compression time (current/default): {avg['gz_curr_ms']:.2f} ms")
    print(f"Total time: {avg['total_ms']:.2f} ms")

    print("\n=== G2 (b) Gzip compresslevel 4 vs Current ===")
    print(f"Current Gzip: {avg['gz_curr_ms']:.2f} ms | Size: {avg['gz_curr_size']} bytes ({avg['gz_curr_size']/1024:.1f} KB)")
    print(f"Level 4 Gzip: {avg['gz_lvl4_ms']:.2f} ms | Size: {avg['gz_lvl4_size']} bytes ({avg['gz_lvl4_size']/1024:.1f} KB)")
    print(f"Time savings: {avg['gz_curr_ms'] - avg['gz_lvl4_ms']:.2f} ms ({((avg['gz_curr_ms'] - avg['gz_lvl4_ms'])/avg['gz_curr_ms'])*100:.1f}% faster)")
    print(f"Size diff: {avg['gz_lvl4_size'] - avg['gz_curr_size']} bytes (+{((avg['gz_lvl4_size'] - avg['gz_curr_size'])/avg['gz_curr_size'])*100:.2f}%)")

    with open("audit/logs/G2_profile.txt", "w") as f:
        f.write("=== G2 (a) & (b) Geo Query Breakdown ===\n\n")
        f.write(f"SQL statements: 2 (1 main query + 1 selectinload category query)\n")
        f.write(f"DB time: {avg['db_ms']:.2f} ms\n")
        f.write(f"Serialization time: {avg['ser_ms']:.2f} ms\n")
        f.write(f"Gzip current time: {avg['gz_curr_ms']:.2f} ms (size: {avg['gz_curr_size']} B)\n")
        f.write(f"Gzip level 4 time: {avg['gz_lvl4_ms']:.2f} ms (size: {avg['gz_lvl4_size']} B)\n")
        f.write(f"Total time: {avg['total_ms']:.2f} ms\n\n")
        f.write("=== EXPLAIN (ANALYZE, BUFFERS) ===\n")
        f.write(plan_text + "\n")

if __name__ == "__main__":
    import sys
    sys.path.insert(0, "back-end")
    asyncio.run(run_g2_breakdown())
