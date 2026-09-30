import asyncio, re
import asyncpg

DB_URL = "postgresql://postgres:postgres@localhost:5432/weather_platform_audit"

# 1. Dashboard summary query:
Q1 = """
EXPLAIN (ANALYZE, FORMAT TEXT)
SELECT 
    count(weather_reports.id) AS total_incidents,
    count(CASE WHEN weather_reports.verification_status = 'VERIFIED' THEN 1 END) AS verified_incidents,
    count(CASE WHEN weather_reports.verification_status = 'PENDING' THEN 1 END) AS pending_incidents,
    count(CASE WHEN weather_reports.verification_status = 'REJECTED' THEN 1 END) AS rejected_incidents,
    count(CASE WHEN weather_reports.severity = 'SEVERE' THEN 1 END) AS severe_incidents,
    avg(weather_reports.credibility_score) AS avg_credibility_score
FROM weather_reports;
"""

# 2. Incident list with category + date filter:
Q2 = """
EXPLAIN (ANALYZE, FORMAT TEXT)
SELECT weather_reports.id, weather_reports.tracking_id, weather_reports.severity, weather_reports.occurred_at
FROM weather_reports
WHERE weather_reports.reported_category = 'FLOOD_WATERLOGGING'
  AND weather_reports.occurred_at >= NOW() - INTERVAL '30 days'
ORDER BY weather_reports.occurred_at DESC
LIMIT 20;
"""

# 3. Incident list page 500 (offset 10000, limit 20):
Q3 = """
EXPLAIN (ANALYZE, FORMAT TEXT)
SELECT weather_reports.id, weather_reports.tracking_id, weather_reports.occurred_at
FROM weather_reports
ORDER BY weather_reports.occurred_at DESC
OFFSET 10000
LIMIT 20;
"""

# 4. Geo endpoint with bbox (ST_MakeEnvelope):
Q4 = """
EXPLAIN (ANALYZE, FORMAT TEXT)
SELECT weather_reports.id, weather_reports.tracking_id, weather_reports.latitude, weather_reports.longitude
FROM weather_reports
WHERE weather_reports.geom && ST_MakeEnvelope(72.0, 18.0, 73.0, 19.0, 4326)
LIMIT 100;
"""

async def run_query(conn, name, query):
    rows = await conn.fetch(query)
    plan = "\n".join([r[0] for r in rows])
    
    # parse execution time
    m_time = re.search(r"Execution Time:\s+([\d\.]+)\s+ms", plan)
    exec_time = float(m_time.group(1)) if m_time else 0.0
    
    # check for Seq Scan on weather_reports
    has_seq_scan = bool(re.search(r"Seq Scan on weather_reports", plan, re.IGNORECASE))
    
    print(f"[{name}] Exec Time: {exec_time:.2f} ms | Seq Scan: {'YES' if has_seq_scan else 'NO'}")
    return name, exec_time, has_seq_scan, plan

async def main():
    conn = await asyncpg.connect(DB_URL)
    results = []
    try:
        results.append(await run_query(conn, "Dashboard summary", Q1))
        results.append(await run_query(conn, "Category+Date filter", Q2))
        results.append(await run_query(conn, "Page 500 (offset 10k)", Q3))
        results.append(await run_query(conn, "Geo bbox", Q4))
        
        with open("audit/logs/B3.txt", "w") as f:
            for name, et, ss, plan in results:
                f.write(f"{name}: {et:.2f} ms | Seq Scan: {'YES' if ss else 'NO'}\n")
                f.write(f"--- Plan for {name} ---\n{plan}\n\n")
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(main())
