import asyncio, time, random, uuid, io
from datetime import datetime, timedelta, timezone
import asyncpg

DB_URL = "postgresql://postgres:postgres@localhost:5432/weather_platform_audit"

CATEGORIES = ["FLOOD_WATERLOGGING", "HEAVY_RAINFALL", "THUNDERSTORM_LIGHTNING", "CYCLONE_GALE", "HEATWAVE", "HAILSTORM", "LANDSLIDE", "OTHER"]
SEVERITIES = ["LOW", "MODERATE", "HIGH", "SEVERE"]
STATUSES = ["VERIFIED", "REJECTED", "PENDING", "UNDER_REVIEW"]

async def main():
    conn = await asyncpg.connect(DB_URL)
    t0 = time.time()
    try:
        cat_id = await conn.fetchval("SELECT id FROM event_categories LIMIT 1;")
        if not cat_id:
            cat_id = await conn.fetchval("""
                INSERT INTO event_categories (id, category_code, title, severity_default, color_hex, icon_name)
                VALUES ($1, 'FLOOD_WATERLOGGING', 'Flooding & Waterlogging', 'MODERATE', '#3B82F6', 'droplets')
                RETURNING id;
            """, uuid.uuid4())

        src_id = await conn.fetchval("SELECT id FROM sources LIMIT 1;")
        if not src_id:
            src_id = await conn.fetchval("""
                INSERT INTO sources (id, source_code, name, source_type, base_trust_score, is_active)
                VALUES ($1, 'CITIZEN', 'Citizen Intake', 'CITIZEN', 0.6, true)
                RETURNING id;
            """, uuid.uuid4())

        now = datetime.now(timezone.utc)
        six_months_ago = now - timedelta(days=180)
        time_span_seconds = int((now - six_months_ago).total_seconds())

        print("Generating 100,000 synthetic weather reports...")
        
        buf = io.BytesIO()
        for i in range(100000):
            rep_id = uuid.uuid4()
            tracking_id = f"RPT-SEED-{i:06d}"
            lat = round(random.uniform(8.5, 35.0), 6)
            lon = round(random.uniform(69.0, 95.0), 6)
            occurred = six_months_ago + timedelta(seconds=random.randint(0, time_span_seconds))
            cat = random.choice(CATEGORIES)
            sev = random.choice(SEVERITIES)
            ver = random.choice(STATUSES)
            score = round(random.uniform(0.3, 0.95), 4)
            title = f"Synthetic {cat} Event {i}"
            desc = f"Synthetic weather report #{i} recorded in audit benchmark."
            loc = f"City_{i % 500}"
            point_wkt = f"SRID=4326;POINT({lon} {lat})"
            
            line = f"{rep_id}\t{tracking_id}\t{src_id}\t{cat_id}\t{cat}\t{sev}\t{title}\t{desc}\t{loc}\t{point_wkt}\t{lat}\t{lon}\t{occurred.isoformat()}\tCOMPLETED\t{ver}\t{score}\t{occurred.isoformat()}\t{occurred.isoformat()}\n"
            buf.write(line.encode("utf-8"))

        buf.seek(0)
        print("COPYing weather_reports to database...")
        copy_res = await conn.copy_to_table(
            "weather_reports",
            source=buf,
            columns=[
                "id", "tracking_id", "source_id", "category_id", "reported_category",
                "severity", "title", "description", "location_name", "geom",
                "latitude", "longitude", "occurred_at", "processing_status",
                "verification_status", "credibility_score", "created_at", "updated_at"
            ]
        )
        print(f"Report copy finished: {copy_res}")

        print("Generating 10,000 synthetic observations...")
        obs_buf = io.BytesIO()
        for i in range(10000):
            obs_id = uuid.uuid4()
            ext_id = f"OBS-SEED-{i:05d}"
            lat = round(random.uniform(8.5, 35.0), 6)
            lon = round(random.uniform(69.0, 95.0), 6)
            point_wkt = f"SRID=4326;POINT({lon} {lat})"
            occurred = six_months_ago + timedelta(seconds=random.randint(0, time_span_seconds))
            line = f"{obs_id}\t{src_id}\t{ext_id}\tSTATION_{i%100}\tStation {i%100}\t{point_wkt}\t{occurred.isoformat()}\t28.5\t65.0\t12.4\t0.0\t15.0\t180\t1012.0\t{{}}\t{occurred.isoformat()}\n"
            obs_buf.write(line.encode("utf-8"))
        obs_buf.seek(0)
        await conn.copy_to_table(
            "weather_observations",
            source=obs_buf,
            columns=[
                "id", "source_id", "external_id", "station_code", "station_name", "geom",
                "observed_at", "temperature_c", "humidity_pct", "rainfall_mm", "water_level_m",
                "wind_speed_kmh", "wind_direction_deg", "pressure_hpa", "raw_metrics", "created_at"
            ]
        )

        print("Generating 10,000 synthetic evidence items...")
        evi_buf = io.BytesIO()
        for i in range(10000):
            evi_id = uuid.uuid4()
            ext_id = f"EVI-SEED-{i:05d}"
            occurred = six_months_ago + timedelta(seconds=random.randint(0, time_span_seconds))
            line = f"{evi_id}\t{src_id}\t{ext_id}\tNEWS_ARTICLE\tEvidence Headline {i}\thttps://news.example.com/{i}\texample.com\tEnglish\t{occurred.isoformat()}\t{occurred.isoformat()}\tSnippet text {i}\t{{}}\t{occurred.isoformat()}\n"
            evi_buf.write(line.encode("utf-8"))
        evi_buf.seek(0)
        await conn.copy_to_table(
            "evidence_items",
            source=evi_buf,
            columns=[
                "id", "source_id", "external_id", "evidence_type", "title", "url",
                "publisher_domain", "language", "published_at", "captured_at",
                "text_snippet", "raw_payload", "created_at"
            ]
        )

        print("Running VACUUM ANALYZE...")
        await conn.execute("VACUUM ANALYZE weather_reports;")
        await conn.execute("VACUUM ANALYZE weather_observations;")
        await conn.execute("VACUUM ANALYZE evidence_items;")

        total_time = time.time() - t0
        count = await conn.fetchval("SELECT count(*) FROM weather_reports;")
        print(f"Total rows seeded: {count}")
        print(f"Seed time: {total_time:.2f}s")
        with open("audit/logs/B2.txt", "w") as f:
            f.write(f"Total weather_reports: {count}\nSeed time: {total_time:.2f}s\n")
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(main())
