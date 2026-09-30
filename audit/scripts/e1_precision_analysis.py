import asyncio
import os
import random
import statistics
import sys
import uuid
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent / "back-end"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.db.session import async_session_factory
from app.intelligence.credibility_collector import credibility_collector
from app.intelligence.credibility_engine import credibility_engine
from app.intelligence.credibility_scorer import credibility_scorer
from app.intelligence.evidence_candidate_generator import evidence_candidate_generator
from app.intelligence.evidence_linking_engine import evidence_linking_engine
from app.intelligence.evidence_scorer import evidence_scorer, EvidenceRelationship
from app.models.category import EventCategory
from app.models.evidence import EvidenceItem, IncidentEvidenceLink
from app.models.report import WeatherReport
from app.models.source import Source

async def get_old_links(db, report, candidate_evidence):
    """Old candidate generator + scorer logic."""
    links = {}
    for ev in candidate_evidence:
        candidates, _ = await evidence_candidate_generator.get_incident_candidates_for_evidence(db=db, evidence=ev)
        matching_cand = [c for c in candidates if c.id == report.id]
        if not matching_cand:
            continue
        incident = matching_cand[0]
        cat_code = "OTHER"
        if incident.category_id:
            cat_stmt = select(EventCategory.category_code).where(EventCategory.id == incident.category_id)
            cat_res = await db.execute(cat_stmt)
            cat_val = cat_res.scalar_one_or_none()
            if cat_val:
                cat_code = cat_val

        source_type = ev.evidence_type
        if ev.source_id:
            src_stmt = select(Source.source_type).where(Source.id == ev.source_id)
            src_res = await db.execute(src_stmt)
            src_val = src_res.scalar_one_or_none()
            if src_val:
                source_type = src_val

        assessment = evidence_scorer.score_link(
            incident_id=incident.id,
            evidence_id=ev.id,
            incident_title=incident.title,
            incident_desc=incident.description,
            incident_cat=cat_code,
            incident_lat=incident.latitude,
            incident_lon=incident.longitude,
            incident_time=incident.occurred_at,
            incident_loc_name=incident.location_name,
            evidence_title=ev.title,
            evidence_snippet=ev.text_snippet,
            evidence_source_type=source_type,
            evidence_pub_time=ev.published_at or ev.captured_at,
            evidence_url=ev.url,
            evidence_domain=ev.publisher_domain,
        )
        if assessment.relationship_type != EvidenceRelationship.IRRELEVANT:
            links[ev.id] = assessment
    return links

async def get_new_links(db, report, candidate_evidence):
    """New direct evaluation logic with top-10 cap."""
    cat_code = "OTHER"
    if report.category_id:
        cat_stmt = select(EventCategory.category_code).where(EventCategory.id == report.category_id)
        cat_res = await db.execute(cat_stmt)
        cat_val = cat_res.scalar_one_or_none()
        if cat_val:
            cat_code = cat_val
    elif report.reported_category:
        cat_code = report.reported_category.upper()

    assessed = []
    for ev in candidate_evidence:
        source_type = ev.evidence_type
        if ev.source_id:
            src_stmt = select(Source.source_type).where(Source.id == ev.source_id)
            src_res = await db.execute(src_stmt)
            src_val = src_res.scalar_one_or_none()
            if src_val:
                source_type = src_val

        assessment = evidence_scorer.score_link(
            incident_id=report.id,
            evidence_id=ev.id,
            incident_title=report.title,
            incident_desc=report.description,
            incident_cat=cat_code,
            incident_lat=report.latitude,
            incident_lon=report.longitude,
            incident_time=report.occurred_at,
            incident_loc_name=report.location_name,
            evidence_title=ev.title,
            evidence_snippet=ev.text_snippet,
            evidence_source_type=source_type,
            evidence_pub_time=ev.published_at or ev.captured_at,
            evidence_url=ev.url,
            evidence_domain=ev.publisher_domain,
        )
        if assessment.relationship_type != EvidenceRelationship.IRRELEVANT:
            assessed.append((ev.id, assessment))

    # Top-10 cap by score
    assessed.sort(key=lambda x: x[1].overall_score, reverse=True)
    return {ev_id: assess for ev_id, assess in assessed[:10]}

async def run_analysis():
    random.seed(42)
    os.makedirs("audit/logs", exist_ok=True)
    out_lines = []

    def p(line=""):
        print(line)
        out_lines.append(line)

    async with async_session_factory() as session:
        # 1. Fetch same 200 incidents as C1
        stmt = (
            select(WeatherReport)
            .where(WeatherReport.occurred_at.is_not(None))
            .order_by(WeatherReport.occurred_at.desc())
            .limit(200)
        )
        reports = list((await session.execute(stmt)).scalars().all())
        p(f"Fetched {len(reports)} test incidents.")

        # Check (f) category_id NULL counts among 200
        null_cat_count = sum(1 for r in reports if r.category_id is None)
        p(f"\n--- (f) Seeded Incidents Category Analysis ---")
        p(f"Total incidents checked: {len(reports)}")
        p(f"Incidents with category_id IS NULL: {null_cat_count} / {len(reports)} ({null_cat_count/len(reports)*100:.1f}%)")

        old_counts = []
        new_counts = []
        shared_scores = []
        new_only_scores = []
        new_only_items = []  # store tuples for random sampling

        incident_link_diffs = []

        for idx, report in enumerate(reports):
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
            candidate_evidence = list((await session.execute(ev_stmt)).scalars().all())

            old_map = await get_old_links(session, report, candidate_evidence)
            new_map = await get_new_links(session, report, candidate_evidence)

            old_counts.append(len(old_map))
            new_counts.append(len(new_map))

            ev_by_id = {ev.id: ev for ev in candidate_evidence}

            for ev_id, assess in new_map.items():
                if ev_id in old_map:
                    shared_scores.append(assess.overall_score)
                else:
                    new_only_scores.append(assess.overall_score)
                    new_only_items.append((report, ev_by_id[ev_id], assess))

            incident_link_diffs.append((
                abs(len(new_map) - len(old_map)),
                report,
                old_map,
                new_map
            ))

        # (a) Per-incident count stats
        p(f"\n--- (a) Per-Incident Count of Links ---")
        p(f"OLD links per incident: min={min(old_counts)}, median={statistics.median(old_counts)}, max={max(old_counts)}, total={sum(old_counts)}")
        p(f"NEW links per incident: min={min(new_counts)}, median={statistics.median(new_counts)}, max={max(new_counts)}, total={sum(new_counts)}")

        # (b) Link score histogram
        p(f"\n--- (b) Score Histograms (0.1 buckets) ---")
        buckets = [f"{i/10:.1f}-{(i+1)/10:.1f}" for i in range(10)]
        shared_hist = Counter()
        new_only_hist = Counter()

        for s in shared_scores:
            b_idx = min(int(s * 10), 9)
            shared_hist[buckets[b_idx]] += 1
        for s in new_only_scores:
            b_idx = min(int(s * 10), 9)
            new_only_hist[buckets[b_idx]] += 1

        p(f"{'Bucket':<10} | {'Shared Links':<14} | {'Only in NEW':<14}")
        p("-" * 44)
        for b in buckets:
            p(f"{b:<10} | {shared_hist[b]:<14} | {new_only_hist[b]:<14}")

        min_shared = min(shared_scores) if shared_scores else 0.0
        min_new_only = min(new_only_scores) if new_only_scores else 0.0
        p(f"Minimum score in shared links: {min_shared:.4f}")
        p(f"Minimum score in only-in-NEW: {min_new_only:.4f}")
        p(f"Active Thresholds: Supporting={evidence_scorer.supporting_threshold}, Related={evidence_scorer.related_threshold}, Contextual={evidence_scorer.contextual_threshold}")

        # (c) Negative controls (10 synthetic pairs that must NOT link)
        p(f"\n--- (c) Negative Controls Test (10 pairs) ---")
        now = datetime.now(timezone.utc)
        neg_pairs = [
            # 1. Different cities > 100km (Mumbai vs Pune 120km)
            ("Mumbai Waterlogging", "Waterlogging at Dadar", "FLOOD_WATERLOGGING", 19.0178, 72.8478, now, "Dadar, Mumbai",
             "Pune Heavy Downpour", "Heavy rain in Shivaji Nagar Pune", "NEWS_PORTAL", now, "Pune rain", 18.5204, 73.8567, "Pune, Maharashtra"),
            # 2. Different cities > 100km (Delhi vs Jaipur 240km)
            ("Delhi Flooded Street", "Severe waterlogging on Ring Road Delhi", "FLOOD_WATERLOGGING", 28.6139, 77.2090, now, "New Delhi",
             "Jaipur Sunny Weather", "Hot weather in Jaipur city", "NEWS_PORTAL", now, "Jaipur weather", 26.9124, 75.7873, "Jaipur, Rajasthan"),
            # 3. Different cities > 100km (Bengaluru vs Chennai 290km)
            ("Bengaluru Urban Flood", "Bellandur lake overflow in Bengaluru", "FLOOD_WATERLOGGING", 12.9716, 77.5946, now, "Bengaluru",
             "Chennai Marina Beach Rain", "Rains hit Marina Beach Chennai", "NEWS_PORTAL", now, "Chennai news", 13.0827, 80.2707, "Chennai, Tamil Nadu"),
            # 4. Same city, completely unrelated category (Heatwave vs Heavy Rainfall in Delhi)
            ("Extreme Heatwave in Delhi", "Temperatures touch 46C in Delhi severe loo conditions", "HEATWAVE", 28.6139, 77.2090, now, "New Delhi",
             "Flash Flood in Delhi", "Flash flood and waterlogging in Delhi subway", "NEWS_PORTAL", now, "Delhi subway flood", 28.6139, 77.2090, "New Delhi"),
            # 5. Same city, unrelated category (Drought vs Flash Flood in Nagpur)
            ("Severe Drought in Vidarbha", "Farmers face extreme drought and crop failure in Nagpur district", "DROUGHT", 21.1458, 79.0882, now, "Nagpur",
             "Torrential Rain and Inundation in Nagpur", "Streets inundated with flood water in Nagpur", "NEWS_PORTAL", now, "Nagpur flood", 21.1458, 79.0882, "Nagpur"),
            # 6. Same city, unrelated non-weather event (Cricket match in Mumbai)
            ("Heavy Rain in Mumbai", "Monsoon rain inundates Mumbai tracks", "HEAVY_RAINFALL", 19.0760, 72.8777, now, "Mumbai",
             "Cricket Stadium Match Tickets", "IPL cricket tournament match tickets on sale at Wankhede stadium celebrity attendance box office", "NEWS_PORTAL", now, "Cricket tickets", 19.0760, 72.8777, "Mumbai"),
            # 7. Same place, extreme temporal delta: +72 hours (3 days later)
            ("Mumbai Waterlogging", "Waterlogging in Kurla", "FLOOD_WATERLOGGING", 19.0657, 72.8794, now, "Kurla, Mumbai",
             "Kurla Waterlogging Report", "Waterlogging cleared in Kurla", "NEWS_PORTAL", now + timedelta(hours=72), "Kurla water", 19.0657, 72.8794, "Kurla, Mumbai"),
            # 8. Same place, extreme temporal delta: -96 hours (4 days earlier)
            ("Chennai Rain Inundation", "Inundation in Velachery", "FLOOD_WATERLOGGING", 12.9759, 80.2212, now, "Velachery, Chennai",
             "Velachery Advisory", "Pre-monsoon drainage cleaning in Velachery", "NEWS_PORTAL", now - timedelta(hours=96), "Velachery drain", 12.9759, 80.2212, "Velachery, Chennai"),
            # 9. Foreign location (Karachi Pakistan vs Mumbai)
            ("Mumbai Cyclone Alert", "Cyclone approaching Mumbai coast", "CYCLONE", 18.9220, 72.8347, now, "Mumbai Coast",
             "Karachi Coastal Alert", "Pakistan Karachi coast storm warning", "NEWS_PORTAL", now, "Karachi Pakistan storm", 24.8607, 67.0011, "Karachi, Pakistan"),
            # 10. Same city, completely contradictory text with denial
            ("Bridge Collapse in Kolkata", "Rumours of bridge collapse during rain in Kolkata", "FLOOD_WATERLOGGING", 22.5726, 88.3639, now, "Kolkata",
             "Police Denies Bridge Collapse", "Kolkata police confirms rumour and fake news claims rejected no bridge collapse traffic completely normal", "NEWS_PORTAL", now, "Kolkata debunk", 22.5726, 88.3639, "Kolkata"),
        ]

        neg_linked_count = 0
        for i, pair in enumerate(neg_pairs, 1):
            inc_title, inc_desc, inc_cat, inc_lat, inc_lon, inc_time, inc_loc, \
            evi_title, evi_snip, evi_src, evi_time, evi_url, evi_lat, evi_lon, evi_loc_str = pair

            assess = evidence_scorer.score_link(
                incident_id=uuid.uuid4(),
                evidence_id=uuid.uuid4(),
                incident_title=inc_title,
                incident_desc=inc_desc,
                incident_cat=inc_cat,
                incident_lat=inc_lat,
                incident_lon=inc_lon,
                incident_time=inc_time,
                incident_loc_name=inc_loc,
                evidence_title=evi_title,
                evidence_snippet=evi_snip,
                evidence_source_type=evi_src,
                evidence_pub_time=evi_time,
                evidence_url=evi_url,
                evidence_domain="news.example.com",
            )
            is_linked = assess.relationship_type not in (EvidenceRelationship.IRRELEVANT, EvidenceRelationship.CONTRADICTORY)
            if is_linked:
                neg_linked_count += 1
            p(f"Control {i:2d}: {assess.relationship_type.value:<12} (score={assess.overall_score:.4f}) | {assess.explanation[:60]}... | Linked? {is_linked}")
        p(f"Negative controls unexpectedly linked: {neg_linked_count} / {len(neg_pairs)}")

        # (d) 30 random only-in-NEW pairs
        p(f"\n--- (d) 30 Random Only-in-NEW Pairs Table ---")
        sampled = random.sample(new_only_items, min(30, len(new_only_items)))
        p(f"{'#':<3} | {'Incident (City/Cat)':<30} | {'Evidence (City/Type)':<32} | {'Score':<6} | {'Delta_h':<7} | {'Dist_km':<8} | {'Verdict'}")
        p("-" * 115)
        
        plausible_count = 0
        for i, (inc, ev, assess) in enumerate(sampled, 1):
            delta_h = assess.signals.temporal_delta_hours
            dist_km = (assess.signals.spatial_distance_meters / 1000.0) if assess.signals.spatial_distance_meters else None
            
            inc_info = f"{inc.location_name or 'Unknown'} / {inc.reported_category or 'OTHER'}"[:30]
            evi_info = f"{ev.title[:20]} / {ev.evidence_type}"[:32]
            
            # Simple heuristic plausibility assessment based on signals
            # If city matches or dist < 30km, and delta_h <= 24h, and score >= 0.55 -> Plausible
            score = assess.overall_score
            is_plausible = True
            reason = "Plausible"
            
            if dist_km and dist_km > 50.0:
                is_plausible = False
                reason = "Distant"
            elif delta_h and delta_h > 36.0:
                is_plausible = False
                reason = "Stale"
            elif assess.signals.category_relevance_score < 0.4:
                is_plausible = False
                reason = "HazardMismatch"
            elif score < 0.50:
                is_plausible = False
                reason = "LowConfidence"

            if is_plausible:
                plausible_count += 1

            d_str = f"{delta_h:.1f}h" if delta_h is not None else "N/A"
            dist_str = f"{dist_km:.1f}km" if dist_km is not None else "N/A"
            p(f"{i:<3} | {inc_info:<30} | {evi_info:<32} | {score:.4f} | {d_str:<7} | {dist_str:<8} | {reason}")

        p(f"\nPlausibility estimate: {plausible_count} / {len(sampled)} ({plausible_count/len(sampled)*100:.1f}%)")

        # (e) Credibility deep dive for 5 incidents with largest link count difference
        p(f"\n--- (e) Credibility for 5 Incidents with Largest Link Diff ---")
        incident_link_diffs.sort(key=lambda x: x[0], reverse=True)
        top5 = incident_link_diffs[:5]

        for rank, (diff, rep, old_m, new_m) in enumerate(top5, 1):
            p(f"\nTop {rank}: Incident {rep.id} ({rep.title[:40]})")
            p(f"Link counts: OLD={len(old_m)} (Supp={sum(1 for a in old_m.values() if a.relationship_type == EvidenceRelationship.SUPPORTING)}) | "
              f"NEW={len(new_m)} (Supp={sum(1 for a in new_m.values() if a.relationship_type == EvidenceRelationship.SUPPORTING)}) | Diff={diff}")
            
            # Now let's calculate credibility under OLD links:
            # We temporarily mock the DB query or mock inputs to see what credibility engine computes
            # Let's inspect what inputs credibility_collector produces
            raw_inputs = await credibility_collector.collect_inputs(db=session, incident_id=rep.id)
            # Recompute with OLD links
            # Build digital evidence groups for old_m
            old_prov_map = defaultdict(lambda: [0, 0.0, 0.0, "NEWS", False])
            for ev_id, a in old_m.items():
                ev = await session.get(EvidenceItem, ev_id)
                if not ev: continue
                role_w = 1.0 if a.relationship_type == EvidenceRelationship.SUPPORTING else 0.35
                pkey = f"domain_{ev.publisher_domain.lower()}" if ev.publisher_domain else f"evi_{ev.id}"
                old_prov_map[pkey][0] += 1
                old_prov_map[pkey][1] = max(old_prov_map[pkey][1], a.overall_score)
                old_prov_map[pkey][2] = max(old_prov_map[pkey][2], role_w)

            # Build digital evidence groups for new_m
            new_prov_map = defaultdict(lambda: [0, 0.0, 0.0, "NEWS", False])
            for ev_id, a in new_m.items():
                ev = await session.get(EvidenceItem, ev_id)
                if not ev: continue
                role_w = 1.0 if a.relationship_type == EvidenceRelationship.SUPPORTING else 0.35
                pkey = f"domain_{ev.publisher_domain.lower()}" if ev.publisher_domain else f"evi_{ev.id}"
                new_prov_map[pkey][0] += 1
                new_prov_map[pkey][1] = max(new_prov_map[pkey][1], a.overall_score)
                new_prov_map[pkey][2] = max(new_prov_map[pkey][2], role_w)

            from app.intelligence.schemas import DigitalEvidenceGroupInput
            
            inputs_old = raw_inputs.model_copy(deep=True)
            inputs_old.evidence_groups = [
                DigitalEvidenceGroupInput(
                    provenance_key=k, article_count=v[0], max_confidence=v[1],
                    role_weight=v[2], source_family=v[3], is_derived_lineage=v[4]
                ) for k, v in old_prov_map.items()
            ]

            inputs_new = raw_inputs.model_copy(deep=True)
            inputs_new.evidence_groups = [
                DigitalEvidenceGroupInput(
                    provenance_key=k, article_count=v[0], max_confidence=v[1],
                    role_weight=v[2], source_family=v[3], is_derived_lineage=v[4]
                ) for k, v in new_prov_map.items()
            ]

            score_old = credibility_scorer.score_incident(inputs_old).final_credibility_score
            score_new = credibility_scorer.score_incident(inputs_new).final_credibility_score
            
            p(f"Credibility inputs: BaseTrust={raw_inputs.source_base_trust:.4f}, ClusterMembers={raw_inputs.cluster_member_count}")
            p(f"Old evidence groups={len(inputs_old.evidence_groups)}, New evidence groups={len(inputs_new.evidence_groups)}")
            p(f"Computed Credibility Score: with OLD links = {score_old:.4f} | with NEW links = {score_new:.4f} (Diff = {score_new - score_old:+.4f})")

    with open("audit/logs/E1.txt", "w") as f:
        f.write("\n".join(out_lines))
    print("\nWrote raw output to audit/logs/E1.txt")

if __name__ == "__main__":
    asyncio.run(run_analysis())
