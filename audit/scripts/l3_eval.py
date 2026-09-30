"""audit/scripts/l3_eval.py — Rerun 20-link table on weather_platform_audit, check 13 implausible rows, total links, cap hits, and credibility deltas."""

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
from app.intelligence.credibility_collector import credibility_collector, map_source_type_to_family
from app.intelligence.credibility_scorer import credibility_scorer
from app.intelligence.evidence_candidate_generator import evidence_candidate_generator
from app.intelligence.evidence_scorer import evidence_scorer, EvidenceRelationship
from app.intelligence.schemas import DigitalEvidenceGroupInput
from app.models.category import EventCategory
from app.models.evidence import EvidenceItem
from app.models.report import WeatherReport
from app.models.source import Source

from audit.scripts.benchmark_v2_comparison import PreL1EvidenceScorer

DB_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@localhost:5432/weather_platform"
)

def build_groups(assessed_links, ev_by_id):
    prov_map = defaultdict(lambda: [0, 0.0, 0.0, None, False, None])
    for a in assessed_links:
        ev = ev_by_id[a.evidence_id]
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
        print(f"Loaded {len(reports)} incidents from audit DB.")

        pre_scorer = PreL1EvidenceScorer()
        new_scorer = evidence_scorer

        all_candidate_pairs = []

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
                cat_val = (await session.execute(cat_stmt)).scalar_one_or_none()
                if cat_val:
                    cat_code = cat_val
            elif rep.reported_category:
                cat_code = rep.reported_category.upper()

            for ev in candidate_evidence:
                source_type = ev.evidence_type
                if ev.source_id:
                    src_stmt = select(Source.source_type).where(Source.id == ev.source_id)
                    src_val = (await session.execute(src_stmt)).scalar_one_or_none()
                    if src_val:
                        source_type = src_val

                assessment_old = pre_scorer.score_link(
                    incident_id=rep.id, evidence_id=ev.id,
                    incident_title=rep.title, incident_desc=rep.description,
                    incident_cat=cat_code, incident_lat=rep.latitude, incident_lon=rep.longitude,
                    incident_time=rep.occurred_at, incident_loc_name=rep.location_name,
                    evidence_title=ev.title, evidence_snippet=ev.text_snippet,
                    evidence_source_type=source_type, evidence_pub_time=ev.published_at or ev.captured_at,
                    evidence_url=ev.url, evidence_domain=ev.publisher_domain,
                )

                if assessment_old.overall_score >= 0.50 and assessment_old.relationship_type != EvidenceRelationship.IRRELEVANT:
                    all_candidate_pairs.append({
                        "rep": rep,
                        "ev": ev,
                        "cat_code": cat_code,
                        "source_type": source_type,
                        "old_score": assessment_old.overall_score,
                        "old_role": assessment_old.relationship_type.value,
                    })

        # Sample the exact 20 rows with seed 42 as done in C2
        random.seed(42)
        sample_20 = random.sample(all_candidate_pairs, min(20, len(all_candidate_pairs)))

        print("\n=== 20-Link Table Evaluation (Pre-L1 vs New Logic) ===")
        print("| # | Incident Title | City | Evidence Title | Old Score | New Score | New Role | Status |")
        print("|---|---|---|---|---|---|---|---|")

        implausible_indices = {1, 4, 6, 7, 9, 10, 11, 12, 13, 16, 18, 19, 20}
        implausible_remained = 0

        for i, item in enumerate(sample_20, 1):
            rep = item["rep"]
            ev = item["ev"]
            cat_code = item["cat_code"]
            source_type = item["source_type"]

            assessment_new = new_scorer.score_link(
                incident_id=rep.id, evidence_id=ev.id,
                incident_title=rep.title, incident_desc=rep.description,
                incident_cat=cat_code, incident_lat=rep.latitude, incident_lon=rep.longitude,
                incident_time=rep.occurred_at, incident_loc_name=rep.location_name,
                evidence_title=ev.title, evidence_snippet=ev.text_snippet,
                evidence_source_type=source_type, evidence_pub_time=ev.published_at or ev.captured_at,
                evidence_url=ev.url, evidence_domain=ev.publisher_domain,
            )

            is_active_link = (
                assessment_new.relationship_type != EvidenceRelationship.IRRELEVANT
                and assessment_new.overall_score >= 0.50
            )
            status = "ACTIVE" if is_active_link else "**REMOVED**"

            if i in implausible_indices:
                if is_active_link:
                    implausible_remained += 1

            inc_title = rep.title[:30]
            inc_city = (rep.location_name or "Unknown")[:15]
            evi_title = ev.title[:30]
            old_s = f"{item['old_score']:.4f}"
            new_s = f"{assessment_new.overall_score:.4f}"
            new_role = assessment_new.relationship_type.value

            print(f"| {i} | {inc_title} | {inc_city} | {evi_title} | {old_s} | {new_s} | {new_role} | {status} |")

        print(f"\nImplausible rows (1, 4, 6, 7, 9, 10, 11, 12, 13, 16, 18, 19, 20) remaining: {implausible_remained} / 13")

        # 2. Total Links, Cap Hits, and Persisted Credibility Deltas on 200 Incidents
        total_links_old = len(all_candidate_pairs)
        total_links_new = 0
        cap_hits_new = 0
        deltas = []

        for rep in reports:
            time_min = rep.occurred_at - evidence_candidate_generator.max_window
            time_max = rep.occurred_at + evidence_candidate_generator.max_window
            ev_stmt = (
                select(EvidenceItem)
                .where(EvidenceItem.published_at >= time_min, EvidenceItem.published_at <= time_max)
                .limit(evidence_candidate_generator.default_limit)
            )
            cand_ev = list((await session.execute(ev_stmt)).scalars().all())
            ev_by_id = {ev.id: ev for ev in cand_ev}

            cat_code = 'OTHER'
            if rep.category_id:
                cat_stmt = select(EventCategory.category_code).where(EventCategory.id == rep.category_id)
                cat_val = (await session.execute(cat_stmt)).scalar_one_or_none()
                if cat_val:
                    cat_code = cat_val
            elif rep.reported_category:
                cat_code = rep.reported_category.upper()

            links_for_incident = []
            for ev in cand_ev:
                src_type = ev.evidence_type
                if ev.source_id:
                    src_stmt = select(Source.source_type).where(Source.id == ev.source_id)
                    src_val = (await session.execute(src_stmt)).scalar_one_or_none()
                    if src_val:
                        src_type = src_val

                assessment = new_scorer.score_link(
                    incident_id=rep.id, evidence_id=ev.id,
                    incident_title=rep.title, incident_desc=rep.description,
                    incident_cat=cat_code, incident_lat=rep.latitude, incident_lon=rep.longitude,
                    incident_time=rep.occurred_at, incident_loc_name=rep.location_name,
                    evidence_title=ev.title, evidence_snippet=ev.text_snippet,
                    evidence_source_type=src_type, evidence_pub_time=ev.published_at or ev.captured_at,
                    evidence_url=ev.url, evidence_domain=ev.publisher_domain,
                )
                if assessment.relationship_type != EvidenceRelationship.IRRELEVANT and assessment.overall_score >= 0.50:
                    total_links_new += 1
                    links_for_incident.append(assessment)

            # Measure credibility score delta
            raw_inputs = await credibility_collector.collect_inputs(db=session, incident_id=rep.id)
            inp_base = raw_inputs.model_copy(deep=True)
            inp_base.evidence_groups = []
            s_base = credibility_scorer.score_incident(inp_base).final_credibility_score

            groups_new = build_groups(links_for_incident, ev_by_id)
            inp_new = raw_inputs.model_copy(deep=True)
            inp_new.evidence_groups = groups_new
            scored_res = credibility_scorer.score_incident(inp_new)
            s_new = scored_res.final_credibility_score

            delta = round(abs(s_new - s_base), 4)
            deltas.append(delta)

            # Check if capped on weak links
            has_weak = any(credibility_scorer._is_weak_group(g) for g in groups_new)
            s_full_raw = credibility_scorer._compute_raw_signals(inp_new).final_credibility_score
            if has_weak and s_full_raw > s_new:
                cap_hits_new += 1

        import numpy as np
        deltas_arr = np.array(deltas)
        mean_delta = float(np.mean(deltas_arr))
        p95_delta = float(np.percentile(deltas_arr, 95))
        max_delta = float(np.max(deltas_arr))

        print("\n=== Aggregate Impact on 200 Incidents ===")
        print(f"Total links formed (score >= 0.50): {total_links_old} (Old) -> {total_links_new} (New)")
        print(f"Cap hits: {cap_hits_new} / 200")
        print(f"Persisted credibility deltas vs no-links baseline: Mean={mean_delta:.4f}, p95={p95_delta:.4f}, Max={max_delta:.4f}")

    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(main())
