import asyncio
import io
import random
import time
import uuid
from datetime import datetime, timedelta, timezone
import asyncpg

DB_URL = "postgresql://postgres:postgres@localhost:5432/weather_platform_audit"

# 4 Standard Queries from B3
Q1 = """
SELECT 
    count(weather_reports.id) AS total_incidents,
    count(CASE WHEN weather_reports.verification_status = 'VERIFIED' THEN 1 END) AS verified_incidents,
    count(CASE WHEN weather_reports.verification_status = 'PENDING' THEN 1 END) AS pending_incidents,
    count(CASE WHEN weather_reports.verification_status = 'REJECTED' THEN 1 END) AS rejected_incidents,
    count(CASE WHEN weather_reports.severity = 'SEVERE' THEN 1 END) AS severe_incidents,
    avg(weather_reports.credibility_score) AS avg_credibility_score
FROM weather_reports;
"""

Q2 = """
SELECT weather_reports.id, weather_reports.tracking_id, weather_reports.severity, weather_reports.occurred_at
FROM weather_reports
WHERE weather_reports.reported_category = 'FLOOD_WATERLOGGING'
  AND weather_reports.occurred_at >= NOW() - INTERVAL '30 days'
ORDER BY weather_reports.occurred_at DESC
LIMIT 20;
"""

Q3 = """
SELECT weather_reports.id, weather_reports.tracking_id, weather_reports.occurred_at
FROM weather_reports
ORDER BY weather_reports.occurred_at DESC
OFFSET 10000
LIMIT 20;
"""

Q4 = """
SELECT weather_reports.id, weather_reports.tracking_id, weather_reports.latitude, weather_reports.longitude
FROM weather_reports
WHERE weather_reports.geom && ST_MakeEnvelope(72.0, 18.0, 73.0, 19.0, 4326)
LIMIT 100;
"""

async def run_e5_audit():
    conn = await asyncpg.connect(DB_URL)
    try:
        print("Resetting pg statistics...")
        await conn.execute("SELECT pg_stat_reset();")
        await asyncio.sleep(0.5)

        print("Executing 4 standard queries once each...")
        await conn.execute(Q1)
        await conn.execute(Q2)
        await conn.execute(Q3)
        await conn.execute(Q4)
        await asyncio.sleep(0.5)

        print("\nQuerying index stats on weather_reports...")
        query = """
        SELECT
            i.relname AS index_name,
            pg_size_pretty(pg_relation_size(i.oid)) AS pretty_size,
            pg_relation_size(i.oid) AS raw_bytes,
            s.idx_scan,
            s.idx_tup_read,
            s.idx_tup_fetch,
            pg_get_indexdef(i.oid) AS index_def
        FROM pg_class t
        JOIN pg_index x ON t.oid = x.indrelid
        JOIN pg_class i ON i.oid = x.indexrelid
        LEFT JOIN pg_stat_user_indexes s ON s.indexrelid = i.oid
        WHERE t.relname = 'weather_reports'
        ORDER BY i.relname;
        """
        rows = await conn.fetch(query)

        print(f"\nFound {len(rows)} indexes on weather_reports:")
        total_idx_bytes = sum(r["raw_bytes"] for r in rows)
        
        index_data = []
        for r in rows:
            # extract columns from index_def
            idx_def = r["index_def"]
            cols = idx_def[idx_def.find("(")+1:idx_def.rfind(")")]
            index_data.append({
                "name": r["index_name"],
                "columns": cols,
                "pretty_size": r["pretty_size"],
                "raw_bytes": r["raw_bytes"],
                "idx_scan": r["idx_scan"] or 0,
                "def": idx_def,
            })
            print(f"  - {r['index_name']}: {cols} | Size: {r['pretty_size']} | idx_scan: {r['idx_scan']}")

        # 20k COPY throughput test
        print("\nPreparing 20,000 synthetic rows for COPY throughput test...")
        cat_id = await conn.fetchval("SELECT id FROM event_categories LIMIT 1;")
        src_id = await conn.fetchval("SELECT id FROM sources LIMIT 1;")
        
        buf = io.BytesIO()
        now = datetime.now(timezone.utc)
        for i in range(20000):
            rep_id = uuid.uuid4()
            tracking_id = f"RPT-E5-{i:06d}"
            lat = 19.0760
            lon = 72.8777
            occurred = now - timedelta(hours=i % 240)
            point_wkt = f"SRID=4326;POINT({lon} {lat})"
            line = f"{rep_id}\t{tracking_id}\t{src_id}\t{cat_id}\tFLOOD_WATERLOGGING\tMODERATE\tE5 Test\tTest desc\tMumbai\t{point_wkt}\t{lat}\t{lon}\t{occurred.isoformat()}\tCOMPLETED\tVERIFIED\t0.75\t{occurred.isoformat()}\t{occurred.isoformat()}\n"
            buf.write(line.encode("utf-8"))
        buf.seek(0)

        cols = [
            "id", "tracking_id", "source_id", "category_id", "reported_category",
            "severity", "title", "description", "location_name", "geom",
            "latitude", "longitude", "occurred_at", "processing_status",
            "verification_status", "credibility_score", "created_at", "updated_at"
        ]

        print("Measuring COPY throughput...")
        async with conn.transaction():
            t_copy_0 = time.perf_counter()
            await conn.copy_to_table("weather_reports", source=buf, columns=cols)
            t_copy_1 = time.perf_counter()
            # Rollback to avoid polluting the audit dataset
            raise asyncpg.exceptions.PostgresError("TEST_ROLLBACK")
    except asyncpg.exceptions.PostgresError as e:
        if str(e) == "TEST_ROLLBACK":
            pass
        else:
            raise
    finally:
        await conn.close()

    duration_copy = t_copy_1 - t_copy_0
    rows_per_sec = 20000 / duration_copy
    print(f"\nCOPY 20k rows took {duration_copy:.3f} s ({rows_per_sec:.1f} rows/sec)")

    with open("audit/logs/E5.txt", "w") as f:
        f.write(f"Total Indexes on weather_reports: {len(index_data)}\n")
        f.write(f"Total Index Size: {total_idx_bytes / (1024*1024):.2f} MB\n\n")
        f.write(f"COPY Ingest Throughput (20,000 rows): {duration_copy:.3f} s ({rows_per_sec:.1f} rows/sec)\n\n")
        f.write(f"{'Index Name':<40} {'Size':<10} {'idx_scan':<10} {'Columns':<50}\n")
        f.write("-" * 115 + "\n")
        for idx in index_data:
            f.write(f"{idx['name']:<40} {idx['pretty_size']:<10} {idx['idx_scan']:<10} {idx['columns']:<50}\n")

if __name__ == "__main__":
    asyncio.run(run_e5_audit())
