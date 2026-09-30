"""audit/scripts/c2_precision_table.py — Generate human-checkable precision table and implausible pairs."""

import asyncio
import os
import random
import sys
from collections import defaultdict
from pathlib import Path

BACKEND_DIR = Path('/Users/akshatjain/Documents/SIH/back-end')
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from app.core.config import settings
from app.intelligence.evidence_candidate_generator import evidence_candidate_generator
from app.intelligence.evidence_scorer import evidence_scorer, EvidenceRelationship
from app.models.category import EventCategory
from app.models.evidence import EvidenceItem
from app.models.report import WeatherReport
from app.models.source import Source

DB_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@localhost:5432/weather_platform"
)

async def main():
    engine = create_async_engine(DB_URL, echo=False)
    session_maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async with session_maker() as session:
        # Load 200 persisted incidents
        stmt = (
            select(WeatherReport)
            .where(
                WeatherReport.occurred_at.is_not(None),
                WeatherReport.title.not_like("Crash test%"),
            )
            .order_by(WeatherReport.occurred_at.desc())
            .limit(200)
        )
        reports = list((await session.execute(stmt)).scalars().all())

        all_pairs = []
        implausible_pairs = []

        for rep in reports:
            time_min = rep.occurred_at - evidence_candidate_generator.max_window
            time_max = rep.occurred_at + evidence_candidate_generator.max_window
            ev_stmt = (
                select(EvidenceItem)
                .where(EvidenceItem.published_at >= time_min, EvidenceItem.published_at <= time_max)
                .limit(evidence_candidate_generator.default_limit)
            )
            candidate_evidence = list((await session.execute(ev_stmt)).scalars().all())

            cat_code = 'OTHER'
            if rep.category_id:
                cat_stmt = select(EventCategory.category_code).where(EventCategory.id == rep.category_id)
                cat_res = await session.execute(cat_stmt)
                cat_val = cat_res.scalar_one_or_none()
                if cat_val:
                    cat_code = cat_val
            elif rep.reported_category:
                cat_code = rep.reported_category.upper()

            inc_city = rep.location_name or "Unknown"

            for ev in candidate_evidence:
                source_type = ev.evidence_type
                if ev.source_id:
                    src_stmt = select(Source.source_type).where(Source.id == ev.source_id)
                    src_val = (await session.execute(src_stmt)).scalar_one_or_none()
                    if src_val:
                        source_type = src_val

                assessment = evidence_scorer.score_link(
                    incident_id=rep.id, evidence_id=ev.id,
                    incident_title=rep.title, incident_desc=rep.description,
                    incident_cat=cat_code, incident_lat=rep.latitude, incident_lon=rep.longitude,
                    incident_time=rep.occurred_at, incident_loc_name=rep.location_name,
                    evidence_title=ev.title, evidence_snippet=ev.text_snippet,
                    evidence_source_type=source_type, evidence_pub_time=ev.published_at or ev.captured_at,
                    evidence_url=ev.url, evidence_domain=ev.publisher_domain,
                )

                if assessment.overall_score >= 0.50 and assessment.relationship_type != EvidenceRelationship.IRRELEVANT:
                    # Extract time gap and distance
                    time_gap_h = round(abs((ev.published_at - rep.occurred_at).total_seconds()) / 3600.0, 1) if ev.published_at and rep.occurred_at else 0.0
                    evi_city = ev.publisher_domain or "Web"
                    # Distance if coords exist
                    dist_km = "N/A"
                    signals = assessment.signals
                    if signals.spatial_distance_meters is not None:
                        dist_km = f"{signals.spatial_distance_meters / 1000.0:.1f}"

                    all_pairs.append({
                        "inc_title": rep.title[:35],
                        "inc_city": inc_city[:15],
                        "inc_cat": cat_code[:12],
                        "evi_title": ev.title[:35],
                        "evi_city": evi_city[:15],
                        "evi_type": ev.evidence_type[:12],
                        "score": f"{assessment.overall_score:.4f}",
                        "time_gap_h": f"{time_gap_h}h",
                        "dist_km": dist_km,
                    })

                # Programmatic plausibility check
                # A link is judged implausible if locations contradict or categories are completely mismatched
                signals = assessment.signals
                if assessment.overall_score >= 0.45:
                    failing_components = []
                    # Check geographic mismatch (spatial_score < 0.2 means far outside radius)
                    if signals.spatial_score < 0.2 and signals.spatial_distance_meters is not None:
                        dist_show = signals.spatial_distance_meters / 1000.0
                        failing_components.append(f"spatial_score={signals.spatial_score:.2f} (<0.20, dist={dist_show:.0f}km)")
                    if signals.temporal_score < 0.3:
                        failing_components.append(f"temporal_score={signals.temporal_score:.2f} (<0.30)")
                    if signals.semantic_similarity < 0.35:
                        failing_components.append(f"semantic_similarity={signals.semantic_similarity:.2f} (<0.35)")

                    if failing_components:
                        implausible_pairs.append({
                            "incident": f'"{rep.title[:30]}" ({inc_city})',
                            "evidence": f'"{ev.title[:30]}" ({ev.publisher_domain or "Unknown"})',
                            "score": f"{assessment.overall_score:.4f}",
                            "role": assessment.relationship_type.value,
                            "failing_rule": ", ".join(failing_components),
                        })

        await engine.dispose()

        # Random sample 20 links at >= 0.50
        random.seed(42)
        sample_20 = random.sample(all_pairs, min(20, len(all_pairs)))

        print("=== 20 Random Links from Final Set at Threshold 0.50 ===")
        print("| # | Incident Title | City | Cat | Evidence Title | Evi Source | Type | Score | Gap | Dist |")
        print("|---|---|---|---|---|---|---|---|---|---|")
        for i, p in enumerate(sample_20, 1):
            print(f"| {i} | {p['inc_title']} | {p['inc_city']} | {p['inc_cat']} | {p['evi_title']} | {p['evi_city']} | {p['evi_type']} | {p['score']} | {p['time_gap_h']} | {p['dist_km']} |")

        print("\n=== 10 Sample Pairs Judged Implausible by Programmatic Checker ===")
        sample_10 = random.sample(implausible_pairs, min(10, len(implausible_pairs)))
        for i, p in enumerate(sample_10, 1):
            print(f"Pair {i}:")
            print(f"  Incident: {p['incident']}")
            print(f"  Evidence: {p['evidence']}")
            print(f"  Score: {p['score']} | Role: {p['role']}")
            print(f"  Failing Rule Component: {p['failing_rule']}")

        print(f"\nConfig check: settings.EVIDENCE_RELATED_THRESHOLD = {settings.EVIDENCE_RELATED_THRESHOLD}")

if __name__ == "__main__":
    asyncio.run(main())
