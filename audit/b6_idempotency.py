import asyncio, uuid
from datetime import datetime, timezone
from sqlalchemy import select, func
from app.db.session import async_session_factory
from app.ingestion.schemas import NormalizedIngestionEvent
from app.models.report import WeatherReport
from app.services.report_service import report_service

async def main():
    events = []
    batch_uid = uuid.uuid4().hex[:8]
    now = datetime.now(timezone.utc)
    for i in range(50):
        events.append(NormalizedIngestionEvent(
            source_code="IMD_NOWCAST",
            external_id=f"IDEMP-{batch_uid}-{i:03d}",
            category="HEAVY_RAINFALL",
            severity="HIGH",
            title=f"Idempotency Test Event {i}",
            description="Testing idempotent ingestion path",
            latitude=19.0760,
            longitude=72.8777,
            occurred_at=now,
            location_name="Mumbai",
            raw_payload={"test_batch": batch_uid, "idx": i},
        ))

    # Pass 1
    async with async_session_factory() as session:
        for ev in events:
            await report_service.ingest_normalized_event(session, ev)
        await session.commit()

        count_after_pass1 = (await session.execute(select(func.count(WeatherReport.id)))).scalar_one()

    # Pass 2 (exact same events)
    async with async_session_factory() as session:
        for ev in events:
            await report_service.ingest_normalized_event(session, ev)
        await session.commit()

        count_after_pass2 = (await session.execute(select(func.count(WeatherReport.id)))).scalar_one()

    diff = count_after_pass2 - count_after_pass1
    print(f"Pass 1 count: {count_after_pass1}")
    print(f"Pass 2 count: {count_after_pass2}")
    print(f"Row count difference: {diff} (expected 0)")

    with open("audit/logs/B6.txt", "w") as f:
        f.write(f"Pass 1 count: {count_after_pass1}\nPass 2 count: {count_after_pass2}\nDifference: {diff}\n")

if __name__ == "__main__":
    asyncio.run(main())
