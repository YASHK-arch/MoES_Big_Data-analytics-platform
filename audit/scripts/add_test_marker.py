"""Add is_test_fixture marker to evidence_items in weather_platform_audit and weather_platform."""

import asyncio
import asyncpg

DATABASES = ["weather_platform_audit", "weather_platform", "weather_platform_test"]

async def main():
    for db in DATABASES:
        try:
            conn = await asyncpg.connect(f"postgresql://postgres:postgres@localhost:5432/{db}")
            # 1. Add column if not exists
            await conn.execute("""
                ALTER TABLE evidence_items 
                ADD COLUMN IF NOT EXISTS is_test_fixture BOOLEAN NOT NULL DEFAULT FALSE;
            """)
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS ix_evidence_items_is_test_fixture 
                ON evidence_items(is_test_fixture);
            """)

            # 2. Mark test fixtures
            updated = await conn.execute("""
                UPDATE evidence_items
                SET is_test_fixture = TRUE
                WHERE publisher_domain IN ('news.example.com', 'example.com')
                   OR title LIKE 'Test%';
            """)

            # 3. Count
            marked_count = await conn.fetchval("""
                SELECT count(*) FROM evidence_items WHERE is_test_fixture = TRUE;
            """)
            total_count = await conn.fetchval("""
                SELECT count(*) FROM evidence_items;
            """)
            print(f"[{db}] Marked {marked_count} / {total_count} evidence items as is_test_fixture=TRUE (Command: {updated})")
            await conn.close()
        except Exception as e:
            print(f"[{db}] Error: {e}")

if __name__ == "__main__":
    asyncio.run(main())
