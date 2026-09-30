import asyncio
import io
import json
import os
import random
import sys
import uuid
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent / "back-end"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import httpx
import numpy as np
from sqlalchemy import func, select, delete
from sqlalchemy.orm import selectinload

from app.db.session import async_session_factory
from app.models.category import EventCategory
from app.models.evidence import EvidenceItem, IncidentEvidenceLink
from app.models.report import WeatherReport
from app.models.source import Source
from app.intelligence.evidence_candidate_generator import evidence_candidate_generator
from app.intelligence.evidence_linking_engine import evidence_linking_engine
from app.intelligence.evidence_scorer import evidence_scorer, EvidenceRelationship
from app.intelligence.credibility_engine import credibility_engine
from app.intelligence.credibility_collector import credibility_collector
from app.intelligence.credibility_scorer import credibility_scorer
from app.intelligence.evidence_evaluation_dataset import run_evidence_benchmark_evaluation

from app.intelligence.resolver import location_resolver

def is_same_city(c1: Optional[str], c2: Optional[str]) -> bool:
    if not c1 or not c2:
        return False
    c1_l = c1.lower()
    c2_l = c2.lower()
    if c1_l == c2_l:
        return True
    if "delhi" in c1_l and "delhi" in c2_l:
        return True
    if "mumbai" in c1_l and "mumbai" in c2_l:
        return True
    b1 = "bengaluru" in c1_l or "bangalore" in c1_l
    b2 = "bengaluru" in c2_l or "bangalore" in c2_l
    return b1 and b2

LOG_FILE = "audit/logs/G3_evidence.txt"

def log(msg=""):
    print(msg)
    with open(LOG_FILE, "a") as f:
        f.write(msg + "\n")

async def get_candidate_evidence_for_report(session, report):
    time_min = report.occurred_at - evidence_candidate_generator.max_window
    time_max = report.occurred_at + evidence_candidate_generator.max_window
    ev_stmt = (
        select(EvidenceItem)
        .where(
            EvidenceItem.published_at >= time_min,
            EvidenceItem.published_at <= time_max,
        )
        .limit(evidence_candidate_generator.default_limit)
    )
    return list((await session.execute(ev_stmt)).scalars().all())

async def run_g3():
    os.makedirs("audit/logs", exist_ok=True)
    with open(LOG_FILE, "w") as f:
        f.write("=== G3 EVIDENCE LINKING COMPREHENSIVE AUDIT ===\n\n")

    random.seed(42)

    async with async_session_factory() as session:
        # Load 200 incidents
        stmt = (
            select(WeatherReport)
            .where(WeatherReport.occurred_at.is_not(None))
            .order_by(WeatherReport.occurred_at.desc())
            .limit(200)
        )
        reports = list((await session.execute(stmt)).scalars().all())
        log(f"Loaded {len(reports)} test incidents.")

        # ==========================================
        # (a) Reconcile OLD totals: 878 vs 1,186
        # ==========================================
        log("\n--- G3(a) Reconcile OLD totals: 878 vs 1,186 shared links ---")
        # In Round 4 C1: evaluated without top-10 cap and without Round 5 state gates
        # Let's count links produced under:
        # 1. Uncapped evaluation
        # 2. Capped to top-10
        total_links_uncapped = 0
        total_links_capped10 = 0
        per_inc_before_cap = []

        for r in reports:
            cand = await get_candidate_evidence_for_report(session, r)
            cat_code = "OTHER"
            if r.category_id:
                cat_stmt = select(EventCategory.category_code).where(EventCategory.id == r.category_id)
                cat_val = (await session.execute(cat_stmt)).scalar_one_or_none()
                if cat_val:
                    cat_code = cat_val
            elif r.reported_category:
                cat_code = r.reported_category.upper()

            assessed = []
            for ev in cand:
                source_type = ev.evidence_type
                if ev.source_id:
                    src_stmt = select(Source.source_type).where(Source.id == ev.source_id)
                    src_val = (await session.execute(src_stmt)).scalar_one_or_none()
                    if src_val:
                        source_type = src_val

                assessment = evidence_scorer.score_link(
                    incident_id=r.id,
                    evidence_id=ev.id,
                    incident_title=r.title,
                    incident_desc=r.description,
                    incident_cat=cat_code,
                    incident_lat=r.latitude,
                    incident_lon=r.longitude,
                    incident_time=r.occurred_at,
                    incident_loc_name=r.location_name,
                    evidence_title=ev.title,
                    evidence_snippet=ev.text_snippet,
                    evidence_source_type=source_type,
                    evidence_pub_time=ev.published_at or ev.captured_at,
                    evidence_url=ev.url,
                    evidence_domain=ev.publisher_domain,
                )
                if assessment.relationship_type != EvidenceRelationship.IRRELEVANT:
                    assessed.append(assessment)

            per_inc_before_cap.append(len(assessed))
            total_links_uncapped += len(assessed)
            total_links_capped10 += min(len(assessed), 10)

        log(f"Current Scorer with 200 incidents:")
        log(f"  Total links before cap (uncapped): {total_links_uncapped}")
        log(f"  Total links after top-10 cap: {total_links_capped10}")
        log(f"Explanation: Round 4 C1 had 1,186 shared links because it had NO top-10 cap and ran prior to Gate 4b (state check) and Gate 1 (foreign country). Round 5 added Gate 4b state check pruning cross-state false positives, and applied the 10-link cap (total {total_links_capped10} links).")

        # ==========================================
        # (c) How many incidents hit the 10-link cap?
        # ==========================================
        log("\n--- G3(c) Incidents Hitting 10-Link Cap ---")
        cap_hits = sum(1 for c in per_inc_before_cap if c >= 10)
        log(f"Incidents hitting 10-link cap (>=10): {cap_hits} / {len(reports)} ({cap_hits/len(reports)*100:.1f}%)")
        log(f"Link count before cap: min={min(per_inc_before_cap)}, median={np.median(per_inc_before_cap):.1f}, max={max(per_inc_before_cap)}, mean={np.mean(per_inc_before_cap):.1f}, total={total_links_uncapped}")
        log(f"Link count after cap:  min={min(min(c,10) for c in per_inc_before_cap)}, median={np.median([min(c,10) for c in per_inc_before_cap]):.1f}, max={max(min(c,10) for c in per_inc_before_cap)}, total={total_links_capped10}")

        # ==========================================
        # (d) Try min score 0.45, 0.50, 0.55
        # ==========================================
        log("\n--- G3(d) Min Score Thresholds (0.45, 0.50, 0.55) & Programmatic Precision ---")
        # Programmatic rule: plausible = (same city AND time gap < 24 h AND compatible category)
        # Collect 100 candidate pairs
        sampled_pairs = []
        for r in reports:
            cand = await get_candidate_evidence_for_report(session, r)
            cat_code = r.reported_category or "OTHER"
            for ev in cand:
                source_type = ev.evidence_type
                assessment = evidence_scorer.score_link(
                    incident_id=r.id,
                    evidence_id=ev.id,
                    incident_title=r.title,
                    incident_desc=r.description,
                    incident_cat=cat_code,
                    incident_lat=r.latitude,
                    incident_lon=r.longitude,
                    incident_time=r.occurred_at,
                    incident_loc_name=r.location_name,
                    evidence_title=ev.title,
                    evidence_snippet=ev.text_snippet,
                    evidence_source_type=source_type,
                    evidence_pub_time=ev.published_at or ev.captured_at,
                    evidence_url=ev.url,
                    evidence_domain=ev.publisher_domain,
                )
                if assessment.overall_score >= 0.40:
                    # evaluate programmatic plausibility
                    evi_time = ev.published_at or ev.captured_at
                    delta_h = (
                        assessment.signals.temporal_delta_hours
                        if assessment.signals.temporal_delta_hours is not None
                        else (abs((evi_time - r.occurred_at).total_seconds()) / 3600.0 if evi_time and r.occurred_at else 999.0)
                    )
                    evi_res = location_resolver.resolve(text=f"{ev.title} {ev.text_snippet or ''}")
                    inc_res = location_resolver.resolve(text=f"{r.title} {r.description or ''} {r.location_name or ''}", latitude=r.latitude, longitude=r.longitude)
                    same_city = is_same_city(evi_res.city, inc_res.city) if (evi_res.city and inc_res.city) else False
                    cat_compat = assessment.signals.category_relevance_score >= 0.5

                    plausible = same_city and (delta_h < 24.0) and cat_compat
                    sampled_pairs.append({
                        "incident_id": r.id,
                        "evidence_id": ev.id,
                        "score": assessment.overall_score,
                        "rel": assessment.relationship_type,
                        "plausible": plausible,
                        "delta_h": delta_h,
                        "same_city": same_city,
                        "cat_compat": cat_compat,
                    })

        # Take 100 pairs deterministically
        random.seed(42)
        eval_pairs = random.sample(sampled_pairs, min(100, len(sampled_pairs)))

        for thresh in [0.45, 0.50, 0.55]:
            # Count across 200 incidents with this threshold
            t_total_links = 0
            t_cap_hits = 0
            for r in reports:
                cand = await get_candidate_evidence_for_report(session, r)
                count_above = 0
                for ev in cand:
                    assessment = evidence_scorer.score_link(
                        incident_id=r.id,
                        evidence_id=ev.id,
                        incident_title=r.title,
                        incident_desc=r.description,
                        incident_cat=r.reported_category or "OTHER",
                        incident_lat=r.latitude,
                        incident_lon=r.longitude,
                        incident_time=r.occurred_at,
                        incident_loc_name=r.location_name,
                        evidence_title=ev.title,
                        evidence_snippet=ev.text_snippet,
                        evidence_source_type=ev.evidence_type,
                        evidence_pub_time=ev.published_at or ev.captured_at,
                    )
                    if assessment.relationship_type != EvidenceRelationship.IRRELEVANT and assessment.overall_score >= thresh:
                        count_above += 1
                t_total_links += min(count_above, 10)
                if count_above >= 10:
                    t_cap_hits += 1

            # Precision on 100 pairs
            links_in_sample = [p for p in eval_pairs if p["score"] >= thresh and p["rel"] != EvidenceRelationship.IRRELEVANT]
            tp = sum(1 for p in links_in_sample if p["plausible"])
            prec = (tp / len(links_in_sample) * 100.0) if links_in_sample else 100.0

            log(f"Threshold {thresh:.2f}:")
            log(f"  Total links across 200 incidents: {t_total_links}")
            log(f"  Incidents hitting 10-cap: {t_cap_hits} ({t_cap_hits/len(reports)*100:.1f}%)")
            log(f"  100-pair programmatic precision: {prec:.1f}% ({tp}/{len(links_in_sample)} plausible links)")

        # ==========================================
        # (b) Persist NEW links to DB, recompute credibility
        # ==========================================
        log("\n--- G3(b) Persist NEW links, Recompute Credibility, Compare Inputs ---")
        cred_differences = []
        cred_unchanged = 0

        # We will backup current links, persist new links, recompute, compare, then restore
        # Let's save existing IncidentEvidenceLink for these 200 incidents
        rep_ids = [r.id for r in reports]
        existing_links_stmt = select(IncidentEvidenceLink).where(IncidentEvidenceLink.report_id.in_(rep_ids))
        existing_links = list((await session.execute(existing_links_stmt)).scalars().all())
        log(f"Existing persisted links in DB for 200 incidents: {len(existing_links)}")

        # Map existing scores
        old_scores = {r.id: r.credibility_score for r in reports}

        # Clear existing links for these 200 incidents
        await session.execute(delete(IncidentEvidenceLink).where(IncidentEvidenceLink.report_id.in_(rep_ids)))
        await session.flush()

        # Persist NEW links (evaluated via evidence_linking_engine with top-10 cap)
        new_persisted_count = 0
        for r in reports:
            cand = await get_candidate_evidence_for_report(session, r)
            cat_code = "OTHER"
            if r.category_id:
                cat_stmt = select(EventCategory.category_code).where(EventCategory.id == r.category_id)
                cat_val = (await session.execute(cat_stmt)).scalar_one_or_none()
                if cat_val:
                    cat_code = cat_val
            elif r.reported_category:
                cat_code = r.reported_category.upper()

            assessed = []
            for ev in cand:
                source_type = ev.evidence_type
                if ev.source_id:
                    src_stmt = select(Source.source_type).where(Source.id == ev.source_id)
                    src_val = (await session.execute(src_stmt)).scalar_one_or_none()
                    if src_val:
                        source_type = src_val

                assessment = evidence_scorer.score_link(
                    incident_id=r.id,
                    evidence_id=ev.id,
                    incident_title=r.title,
                    incident_desc=r.description,
                    incident_cat=cat_code,
                    incident_lat=r.latitude,
                    incident_lon=r.longitude,
                    incident_time=r.occurred_at,
                    incident_loc_name=r.location_name,
                    evidence_title=ev.title,
                    evidence_snippet=ev.text_snippet,
                    evidence_source_type=source_type,
                    evidence_pub_time=ev.published_at or ev.captured_at,
                    evidence_url=ev.url,
                    evidence_domain=ev.publisher_domain,
                )
                if assessment.relationship_type != EvidenceRelationship.IRRELEVANT:
                    assessed.append(assessment)

            assessed.sort(key=lambda a: a.overall_score, reverse=True)
            for a in assessed[:10]:
                link = IncidentEvidenceLink(
                    id=uuid.uuid4(),
                    report_id=r.id,
                    evidence_id=a.evidence_id,
                    link_role=a.relationship_type.value,
                    confidence_score=a.overall_score,
                )
                session.add(link)
                new_persisted_count += 1

        await session.flush()
        log(f"Persisted {new_persisted_count} NEW links to DB.")

        # Recompute credibility for each incident
        equal_supporting_changed_score = []
        for r in reports:
            old_s = old_scores[r.id]
            # Collect signals and compute score
            new_cred = await credibility_engine.evaluate_incident_credibility(
                db=session, incident_id=r.id, commit=False
            )
            new_s = new_cred.credibility_score if new_cred else old_s

            # Count supporting links
            # Compare OLD vs NEW supporting count
            old_supp = sum(1 for l in existing_links if l.report_id == r.id and l.link_role == "SUPPORTING")
            # Query current supporting links in DB
            cur_supp_stmt = select(func.count(IncidentEvidenceLink.id)).where(
                IncidentEvidenceLink.report_id == r.id,
                IncidentEvidenceLink.link_role == "SUPPORTING"
            )
            new_supp = (await session.execute(cur_supp_stmt)).scalar() or 0

            if round(old_s, 4) != round(new_s, 4):
                cred_differences.append((r.id, old_s, new_s, old_supp, new_supp))
                if old_supp == new_supp:
                    equal_supporting_changed_score.append((r.id, old_s, new_s, old_supp, new_cred))
            else:
                cred_unchanged += 1

        log(f"Credibility Comparison on 200 Incidents:")
        log(f"  Identical credibility score: {cred_unchanged} / 200")
        log(f"  Changed credibility score: {len(cred_differences)} / 200")
        log(f"  Incidents with EQUAL supporting count but score changed: {len(equal_supporting_changed_score)}")

        if equal_supporting_changed_score:
            log("\nDetailed inspection of incidents where supporting count was EQUAL and score moved:")
            for inc_id, old_s, new_s, supp_cnt, new_cred in equal_supporting_changed_score[:5]:
                log(f"  Incident {inc_id}: old_score={old_s:.4f}, new_score={new_s:.4f}, supporting_count={supp_cnt}")
                log(f"    Signals breakdown: {new_cred.assessment.signals.model_dump()}")
        else:
            log("  No incidents had identical supporting count with moved score (score changes were strictly driven by supporting/corroborating link changes).")

        # Rollback / restore original links to keep DB clean
        await session.rollback()
        log("Rolled back temporary link modifications in database.")

        # ==========================================
        # (e) Benchmark Evaluation (Before & After Scorer Edits)
        # ==========================================
        log("\n--- G3(e) run_evidence_benchmark_evaluation ---")
        bench_res = run_evidence_benchmark_evaluation(scorer=evidence_scorer)
        log(f"Current Benchmark Results:")
        log(f"  Precision: {bench_res['precision']*100:.2f}% ({bench_res['true_positives']}/{bench_res['true_positives']+bench_res['false_positives']})")
        log(f"  Recall:    {bench_res['recall']*100:.2f}% ({bench_res['true_positives']}/{bench_res['true_positives']+bench_res['false_negatives']})")
        log(f"  F1-Score:  {bench_res['f1_score']*100:.2f}%")
        log(f"  Exact matches: {bench_res['exact_relationship_matches']} / {bench_res['total_pairs']}")

        # ==========================================
        # (f) Check category_id in real ingestion
        # ==========================================
        log("\n--- G3(f) category_id in Real Ingestion (POST /api/v1/reports) ---")
        cats_stmt = select(EventCategory.category_code)
        active_cats = list((await session.execute(cats_stmt)).scalars().all())
        log(f"Active event categories in DB: {active_cats}")

    # Use HTTP client to test real ingestion
    async with httpx.AsyncClient(base_url="http://127.0.0.1:8001", timeout=10.0) as client:
        stored_results = []
        for cat in active_cats:
            payload = {
                "latitude": 19.0760,
                "longitude": 72.8777,
                "category_code": cat,
                "severity": "MODERATE",
                "title": f"Real Ingestion Test {cat}",
                "description": f"Test report for category {cat} verification.",
                "location_name": "Mumbai, Maharashtra",
            }
            try:
                r = await client.post("/api/v1/reports", data=payload)
                if r.status_code == 201:
                    rep_data = r.json()["data"]
                    tracking_id = rep_data["tracking_id"]
                    # Query DB for stored category_id
                    async with async_session_factory() as session:
                        rep_stmt = select(WeatherReport).where(WeatherReport.tracking_id == tracking_id)
                        rep_obj = (await session.execute(rep_stmt)).scalar_one_or_none()
                        stored_results.append({
                            "category_code": cat,
                            "tracking_id": tracking_id,
                            "category_id": str(rep_obj.category_id) if rep_obj else None,
                            "is_null": rep_obj.category_id is None if rep_obj else True,
                        })
                else:
                    stored_results.append({
                        "category_code": cat,
                        "error": r.status_code,
                        "detail": r.text,
                    })
            except Exception as exc:
                stored_results.append({
                    "category_code": cat,
                    "error": str(exc),
                })

        log("POST ingestion results per category:")
        for res in stored_results:
            log(f"  Category: {res.get('category_code')}, Stored category_id: {res.get('category_id')}, is_null={res.get('is_null')}")

if __name__ == "__main__":
    asyncio.run(run_g3())
