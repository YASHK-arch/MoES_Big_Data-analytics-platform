
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
from app.db.session import async_session_factory
from app.intelligence.credibility_collector import credibility_collector, map_source_type_to_family
from app.intelligence.credibility_scorer import credibility_scorer
from app.intelligence.evidence_candidate_generator import evidence_candidate_generator
from app.intelligence.evidence_scorer import evidence_scorer, EvidenceRelationship
from app.intelligence.schemas import DigitalEvidenceGroupInput, SourceFamily
from app.models.category import EventCategory
from app.models.evidence import EvidenceItem
from app.models.report import WeatherReport
from app.models.source import Source

async def get_old_links(db, report, candidate_evidence):
    links = {}
    for ev in candidate_evidence:
        candidates, _ = await evidence_candidate_generator.get_incident_candidates_for_evidence(db=db, evidence=ev)
        matching_cand = [c for c in candidates if c.id == report.id]
        if not matching_cand:
            continue
        incident = matching_cand[0]
        cat_code = 'OTHER'
        if incident.category_id:
            cat_stmt = select(EventCategory.category_code).where(EventCategory.id == incident.category_id)
            cat_val = (await db.execute(cat_stmt)).scalar_one_or_none()
            if cat_val: cat_code = cat_val

        source_type = ev.evidence_type
        if ev.source_id:
            src_stmt = select(Source.source_type).where(Source.id == ev.source_id)
            src_val = (await db.execute(src_stmt)).scalar_one_or_none()
            if src_val: source_type = src_val

        assessment = evidence_scorer.score_link(
            incident_id=incident.id, evidence_id=ev.id,
            incident_title=incident.title, incident_desc=incident.description,
            incident_cat=cat_code, incident_lat=incident.latitude, incident_lon=incident.longitude,
            incident_time=incident.occurred_at, incident_loc_name=incident.location_name,
            evidence_title=ev.title, evidence_snippet=ev.text_snippet,
            evidence_source_type=source_type, evidence_pub_time=ev.published_at or ev.captured_at,
            evidence_url=ev.url, evidence_domain=ev.publisher_domain,
        )
        if assessment.relationship_type != EvidenceRelationship.IRRELEVANT:
            links[ev.id] = assessment
    return links

async def get_new_links(db, report, candidate_evidence):
    cat_code = 'OTHER'
    if report.category_id:
        cat_stmt = select(EventCategory.category_code).where(EventCategory.id == report.category_id)
        cat_val = (await db.execute(cat_stmt)).scalar_one_or_none()
        if cat_val: cat_code = cat_val
    elif report.reported_category:
        cat_code = report.reported_category.upper()

    assessed = []
    for ev in candidate_evidence:
        source_type = ev.evidence_type
        if ev.source_id:
            src_stmt = select(Source.source_type).where(Source.id == ev.source_id)
            src_val = (await db.execute(src_stmt)).scalar_one_or_none()
            if src_val: source_type = src_val

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

def build_groups_from_map(links_map, ev_by_id):
    prov_map = defaultdict(lambda: [0, 0.0, 0.0, SourceFamily.NEWS, False])
    for ev_id, a in links_map.items():
        ev = ev_by_id.get(ev_id)
        if not ev: continue
        if a.relationship_type == EvidenceRelationship.SUPPORTING:
            role_w = 1.00
        elif a.relationship_type == EvidenceRelationship.RELATED:
            role_w = 0.35
        else:
            role_w = 0.00
        fam = map_source_type_to_family(ev.evidence_type)
        pkey = f'domain_{ev.publisher_domain.lower()}' if ev.publisher_domain else f'evi_{ev.id}'
        prov_map[pkey][0] += 1
        prov_map[pkey][1] = max(prov_map[pkey][1], a.overall_score)
        prov_map[pkey][2] = max(prov_map[pkey][2], role_w)
        prov_map[pkey][3] = fam
    
    return [
        DigitalEvidenceGroupInput(
            provenance_key=k, article_count=v[0], max_confidence=v[1],
            role_weight=v[2], source_family=v[3], is_derived_lineage=v[4]
        ) for k, v in prov_map.items() if v[2] > 0.0
    ]

async def main():
    async with async_session_factory() as session:
        stmt = (
            select(WeatherReport)
            .where(WeatherReport.occurred_at.is_not(None))
            .order_by(WeatherReport.occurred_at.desc())
            .limit(200)
        )
        reports = list((await session.execute(stmt)).scalars().all())
        print(f'Fetched {len(reports)} incidents.')

        deltas = []
        abs_deltas = []
        old_scores = []
        new_scores = []
        increases = 0
        decreases = 0
        unchanged = 0
        detailed_records = []

        thresholds = [0.50, 0.65, 0.70, 0.80, 0.82, 0.85, 0.88]
        crossings = {t: 0 for t in thresholds}

        for idx, rep in enumerate(reports):
            time_min = rep.occurred_at - evidence_candidate_generator.max_window
            time_max = rep.occurred_at + evidence_candidate_generator.max_window
            ev_stmt = (
                select(EvidenceItem)
                .where(EvidenceItem.published_at >= time_min, EvidenceItem.published_at <= time_max)
                .limit(evidence_candidate_generator.default_limit)
            )
            candidate_evidence = list((await session.execute(ev_stmt)).scalars().all())
            ev_by_id = {ev.id: ev for ev in candidate_evidence}

            old_map = await get_old_links(session, rep, candidate_evidence)
            new_map = await get_new_links(session, rep, candidate_evidence)

            raw_inputs = await credibility_collector.collect_inputs(db=session, incident_id=rep.id)
            
            inp_old = raw_inputs.model_copy(deep=True)
            inp_old.evidence_groups = build_groups_from_map(old_map, ev_by_id)
            score_old = credibility_scorer.score_incident(inp_old).final_credibility_score

            inp_new = raw_inputs.model_copy(deep=True)
            inp_new.evidence_groups = build_groups_from_map(new_map, ev_by_id)
            score_new = credibility_scorer.score_incident(inp_new).final_credibility_score

            diff = score_new - score_old
            abs_diff = abs(diff)

            deltas.append(diff)
            abs_deltas.append(abs_diff)
            old_scores.append(score_old)
            new_scores.append(score_new)

            if diff > 0.0001: increases += 1
            elif diff < -0.0001: decreases += 1
            else: unchanged += 1

            for t in thresholds:
                if (score_old < t <= score_new) or (score_new < t <= score_old):
                    crossings[t] += 1

            detailed_records.append({
                'rep': rep,
                'old_len': len(old_map),
                'new_len': len(new_map),
                'old_supp': sum(1 for a in old_map.values() if a.relationship_type == EvidenceRelationship.SUPPORTING),
                'new_supp': sum(1 for a in new_map.values() if a.relationship_type == EvidenceRelationship.SUPPORTING),
                'old_rel': sum(1 for a in old_map.values() if a.relationship_type == EvidenceRelationship.RELATED),
                'new_rel': sum(1 for a in new_map.values() if a.relationship_type == EvidenceRelationship.RELATED),
                'score_old': score_old,
                'score_new': score_new,
                'diff': diff,
                'abs_diff': abs_diff,
            })

        abs_deltas_sorted = sorted(abs_deltas)
        p50 = statistics.median(abs_deltas)
        p95_idx = int(len(abs_deltas) * 0.95)
        p95 = abs_deltas_sorted[p95_idx]
        mean_abs = statistics.mean(abs_deltas)
        max_abs = max(abs_deltas)

        print('\n=== Credibility Impact Analysis on 200 Incidents ===')
        print(f'Mean absolute delta: {mean_abs:.4f}')
        print(f'p50 (median) absolute delta: {p50:.4f}')
        print(f'p95 absolute delta: {p95:.4f}')
        print(f'Max absolute delta: {max_abs:.4f}')
        print(f'Increases: {increases} ({increases/len(reports)*100:.1f}%)')
        print(f'Decreases: {decreases} ({decreases/len(reports)*100:.1f}%)')
        print(f'Unchanged: {unchanged} ({unchanged/len(reports)*100:.1f}%)')

        print('\n=== Threshold Crossings ===')
        for t, c in crossings.items():
            print(f'Threshold {t:.2f}: {c} incidents crossed ({c/len(reports)*100:.1f}%)')

        print('\n=== 3 Concrete Examples ===')
        # Sort by abs_diff descending
        detailed_records.sort(key=lambda x: x['abs_diff'], reverse=True)
        for i, rec in enumerate(detailed_records[:3], 1):
            r = rec['rep']
            print(f'Example {i}: Incident ID {r.id}')
            print(f'  Title: "{r.title}" | Location: {r.location_name}')
            print(f'  OLD links: {rec["old_len"]} (SUPPORTING={rec["old_supp"]}, RELATED={rec["old_rel"]})')
            print(f'  NEW links: {rec["new_len"]} (SUPPORTING={rec["new_supp"]}, RELATED={rec["new_rel"]})')
            print(f'  Score: Before (OLD)={rec["score_old"]:.4f} -> After (NEW)={rec["score_new"]:.4f} (Delta={rec["diff"]:+.4f})')

asyncio.run(main())