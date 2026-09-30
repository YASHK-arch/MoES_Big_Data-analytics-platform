"""audit/scripts/c1_eval.py — Measure credibility impact of weak link cap across 200 incidents."""

import asyncio
import os
import statistics
import sys
from collections import defaultdict
from pathlib import Path

BACKEND_DIR = Path('/Users/akshatjain/Documents/SIH/back-end')
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from app.core.config import settings
from app.intelligence.credibility_collector import credibility_collector, map_source_type_to_family
from app.intelligence.credibility_scorer import credibility_scorer
from app.intelligence.evidence_candidate_generator import evidence_candidate_generator
from app.intelligence.evidence_scorer import evidence_scorer, EvidenceRelationship
from app.intelligence.schemas import DigitalEvidenceGroupInput, SourceFamily
from app.models.category import EventCategory
from app.models.evidence import EvidenceItem
from app.models.report import WeatherReport
from app.models.source import Source

# Thresholds from the code
THRESHOLDS = [0.45, 0.50, 0.65, 0.70, 0.80, 0.82, 0.85, 0.88]

DB_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@localhost:5432/weather_platform_audit"
)

async def get_new_links(db, report, candidate_evidence):
    cat_code = 'OTHER'
    if report.category_id:
        cat_stmt = select(EventCategory.category_code).where(EventCategory.id == report.category_id)
        cat_val = (await db.execute(cat_stmt)).scalar_one_or_none()
        if cat_val:
            cat_code = cat_val
    elif report.reported_category:
        cat_code = report.reported_category.upper()

    assessed = []
    for ev in candidate_evidence:
        source_type = ev.evidence_type
        if ev.source_id:
            src_stmt = select(Source.source_type).where(Source.id == ev.source_id)
            src_val = (await db.execute(src_stmt)).scalar_one_or_none()
            if src_val:
                source_type = src_val

        assessment = evidence_scorer.score_link(
            incident_id=report.id, evidence_id=ev.id,
            incident_title=report.title, incident_desc=report.description,
            incident_cat=cat_code, incident_lat=report.latitude, incident_lon=report.longitude,
            incident_time=report.occurred_at, incident_loc_name=report.location_name,
            evidence_title=ev.title, evidence_snippet=ev.text_snippet,
            evidence_source_type=source_type, evidence_pub_time=ev.published_at or ev.captured_at,
            evidence_url=ev.url, evidence_domain=ev.publisher_domain,
        )
        if assessment.relationship_type != EvidenceRelationship.IRRELEVANT:
            assessed.append((ev.id, assessment))

    assessed.sort(key=lambda x: x[1].overall_score, reverse=True)
    return {ev_id: assess for ev_id, assess in assessed[:10]}

def build_groups(links_map, ev_by_id):
    prov_map = defaultdict(lambda: [0, 0.0, 0.0, SourceFamily.NEWS, False, None])
    for ev_id, a in links_map.items():
        ev = ev_by_id.get(ev_id)
        if not ev:
            continue
        rel_type = a.relationship_type.value
        if a.relationship_type == EvidenceRelationship.SUPPORTING:
            role_w = 1.00
        elif a.relationship_type == EvidenceRelationship.RELATED:
            role_w = 0.35
        elif a.relationship_type == EvidenceRelationship.CONTEXTUAL:
            role_w = 0.20
        else:
            role_w = 0.00
        fam = map_source_type_to_family(ev.evidence_type)
        pkey = f'domain_{ev.publisher_domain.lower()}' if ev.publisher_domain else f'evi_{ev.id}'
        prov_map[pkey][0] += 1
        prov_map[pkey][1] = max(prov_map[pkey][1], a.overall_score)
        if role_w > prov_map[pkey][2] or prov_map[pkey][5] is None:
            prov_map[pkey][5] = rel_type
        prov_map[pkey][2] = max(prov_map[pkey][2], role_w)
        prov_map[pkey][3] = fam

    return [
        DigitalEvidenceGroupInput(
            provenance_key=k, article_count=v[0], max_confidence=v[1],
            role_weight=v[2], source_family=v[3], is_derived_lineage=v[4],
            relationship_type=v[5],
        ) for k, v in prov_map.items() if v[2] > 0.0
    ]

def apply_weak_link_cap(s_strong: float, s_full: float) -> float:
    """Cap contribution of weak links: max delta 0.03, and never cross any threshold."""
    if s_full <= s_strong:
        return s_full
    capped = s_strong + 0.03
    # Check if capped crosses any threshold above s_strong
    next_thresholds = [t for t in THRESHOLDS if t > s_strong]
    if next_thresholds:
        t_next = min(next_thresholds)
        if capped >= t_next:
            capped = t_next - 0.0001
    return round(min(s_full, capped), 4)

async def main():
    engine = create_async_engine(DB_URL, echo=False)
    session_maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async with session_maker() as session:
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
        print(f"Loaded {len(reports)} incidents from audit DB.")

        deltas_before = []
        deltas_after = []
        weak_deltas_before = []
        weak_deltas_after = []
        crossings_before = {t: 0 for t in THRESHOLDS}
        crossings_after = {t: 0 for t in THRESHOLDS}
        crossings_weak_before = {t: 0 for t in THRESHOLDS}
        crossings_weak_after = {t: 0 for t in THRESHOLDS}

        for rep in reports:
            time_min = rep.occurred_at - evidence_candidate_generator.max_window
            time_max = rep.occurred_at + evidence_candidate_generator.max_window
            ev_stmt = (
                select(EvidenceItem)
                .where(EvidenceItem.published_at >= time_min, EvidenceItem.published_at <= time_max)
                .limit(evidence_candidate_generator.default_limit)
            )
            candidate_evidence = list((await session.execute(ev_stmt)).scalars().all())
            ev_by_id = {ev.id: ev for ev in candidate_evidence}

            links = await get_new_links(session, rep, candidate_evidence)
            raw_inputs = await credibility_collector.collect_inputs(db=session, incident_id=rep.id)

            # Baseline: no links (no digital evidence)
            inp_base = raw_inputs.model_copy(deep=True)
            inp_base.evidence_groups = []
            s_base = credibility_scorer.score_incident(inp_base).final_credibility_score

            # Full: all links before cap (raw uncapped)
            groups_all = build_groups(links, ev_by_id)

            # Strong-only baseline:
            groups_strong = [g for g in groups_all if not credibility_scorer._is_weak_group(g)]
            inp_strong = raw_inputs.model_copy(deep=True)
            inp_strong.evidence_groups = groups_strong
            s_strong = credibility_scorer._compute_raw_signals(inp_strong).final_credibility_score
            inp_full = raw_inputs.model_copy(deep=True)
            inp_full.evidence_groups = groups_all
            s_full_uncapped = credibility_scorer._compute_raw_signals(inp_full).final_credibility_score

            # Capped score directly from credibility_scorer.score_incident
            s_capped = credibility_scorer.score_incident(inp_full).final_credibility_score

            d_before = abs(s_full_uncapped - s_base)
            d_after = abs(s_capped - s_base)

            deltas_before.append(d_before)
            deltas_after.append(d_after)

            d_weak_before = max(0.0, s_full_uncapped - s_strong)
            d_weak_after = max(0.0, s_capped - s_strong)
            weak_deltas_before.append(d_weak_before)
            weak_deltas_after.append(d_weak_after)

            for t in THRESHOLDS:
                if s_base < t <= s_full_uncapped:
                    crossings_before[t] += 1
                if s_base < t <= s_capped:
                    crossings_after[t] += 1
                if s_strong < t <= s_full_uncapped:
                    crossings_weak_before[t] += 1
                if s_strong < t <= s_capped:
                    crossings_weak_after[t] += 1

        await engine.dispose()

        p95_b = sorted(deltas_before)[int(len(deltas_before) * 0.95)]
        p95_a = sorted(deltas_after)[int(len(deltas_after) * 0.95)]
        p95_wb = sorted(weak_deltas_before)[int(len(weak_deltas_before) * 0.95)]
        p95_wa = sorted(weak_deltas_after)[int(len(weak_deltas_after) * 0.95)]

        print("\n=== MEASUREMENT RESULTS (200 Incidents vs No-Links Baseline) ===")
        print(f"BEFORE CAP:")
        print(f"  Mean absolute delta: {statistics.mean(deltas_before):.4f}")
        print(f"  p50 absolute delta:  {statistics.median(deltas_before):.4f}")
        print(f"  p95 absolute delta:  {p95_b:.4f}")
        print(f"  Max absolute delta:  {max(deltas_before):.4f}")
        print(f"  Threshold crossings before:")
        for t in THRESHOLDS:
            print(f"    Threshold {t:.2f}: {crossings_before[t]} ({crossings_before[t]/len(reports)*100:.1f}%)")

        print(f"\nAFTER CAP:")
        print(f"  Mean absolute delta: {statistics.mean(deltas_after):.4f}")
        print(f"  p50 absolute delta:  {statistics.median(deltas_after):.4f}")
        print(f"  p95 absolute delta:  {p95_a:.4f}")
        print(f"  Max absolute delta:  {max(deltas_after):.4f}")
        print(f"  Threshold crossings after:")
        for t in THRESHOLDS:
            print(f"    Threshold {t:.2f}: {crossings_after[t]} ({crossings_after[t]/len(reports)*100:.1f}%)")

        print(f"\n=== WEAK-LINK ISOLATED CONTRIBUTION (Delta over Strong Evidence Baseline) ===")
        print(f"BEFORE CAP (Weak links alone):")
        print(f"  Mean weak delta: {statistics.mean(weak_deltas_before):.4f}")
        print(f"  p95 weak delta:  {p95_wb:.4f}")
        print(f"  Max weak delta:  {max(weak_deltas_before):.4f}")
        print(f"  Threshold crossings caused by weak links: {sum(crossings_weak_before.values())}")
        for t, cnt in crossings_weak_before.items():
            if cnt > 0:
                print(f"    Threshold {t:.2f}: {cnt} ({cnt/len(reports)*100:.1f}%)")

        print(f"AFTER CAP (Weak links alone):")
        print(f"  Mean weak delta: {statistics.mean(weak_deltas_after):.4f}")
        print(f"  p95 weak delta:  {p95_wa:.4f}")
        print(f"  Max weak delta:  {max(weak_deltas_after):.4f}")
        print(f"  Threshold crossings caused by weak links: {sum(crossings_weak_after.values())}")
        for t, cnt in crossings_weak_after.items():
            print(f"    Threshold {t:.2f}: {cnt} ({cnt/len(reports)*100:.1f}%)")

if __name__ == "__main__":
    asyncio.run(main())
