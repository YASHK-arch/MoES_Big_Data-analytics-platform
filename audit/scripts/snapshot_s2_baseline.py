"""Snapshot credibility of 200 incidents to audit/s2_baseline.json.
Uses DB weather_platform_s2.
"""

import asyncio
import json
import os
import sys
from typing import Any, Dict, List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import selectinload

# Add back-end to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../back-end")))

from app.intelligence.credibility_collector import CredibilityCollector
from app.intelligence.credibility_scorer import CredibilityScorer
from app.models.report import WeatherReport

DB_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@localhost:5432/weather_platform_s2",
)


async def main() -> None:
    engine = create_async_engine(DB_URL, echo=False)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    collector = CredibilityCollector()
    scorer = CredibilityScorer()

    records: List[Dict[str, Any]] = []

    async with session_factory() as session:
        stmt = (
            select(WeatherReport)
            .options(
                selectinload(WeatherReport.category),
                selectinload(WeatherReport.media),
            )
            .order_by(WeatherReport.created_at.asc(), WeatherReport.id.asc())
            .limit(200)
        )
        res = await session.execute(stmt)
        reports = list(res.scalars().all())

        print(f"Loaded {len(reports)} reports from {DB_URL}")

        for r in reports:
            inp = await collector.collect_inputs(session, r.id)
            if not inp:
                continue
            breakdown = scorer.score_incident(inp)

            records.append(
                {
                    "id": str(r.id),
                    "category": r.category.category_code if r.category else (r.reported_category or "OTHER"),
                    "credibility_score": breakdown.final_credibility_score,
                    "breakdown": breakdown.model_dump(),
                    "media_count": len(r.media) if r.media else 0,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                }
            )

    output_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../s2_baseline.json"))
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(records, f, indent=2)

    scores = [rec["credibility_score"] for rec in records]
    avg_score = sum(scores) / len(scores) if scores else 0.0

    print(f"Saved {len(records)} incidents to {output_path}")
    print(f"Mean credibility score: {avg_score:.4f}")
    print(f"Min credibility score: {min(scores):.4f}")
    print(f"Max credibility score: {max(scores):.4f}")


if __name__ == "__main__":
    asyncio.run(main())
