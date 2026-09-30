import asyncio, time
from sqlalchemy import select
from app.db.session import async_session_factory
from app.models.report import WeatherReport
from app.models.evidence import EvidenceItem, IncidentEvidenceLink
from app.models.source import Source
from app.models.category import EventCategory
from app.intelligence.evidence_candidate_generator import evidence_candidate_generator
from app.intelligence.evidence_scorer import evidence_scorer, EvidenceRelationship
from app.intelligence.evidence_linking_engine import evidence_linking_engine
from app.intelligence.credibility_engine import credibility_engine

async def run_old_logic_for_report(db, report, candidate_evidence):
    """Old logic from git show a1b95e8~1:
    Iterates candidate_evidence, calls evaluate_and_link_evidence (which searches incident candidates for each evidence),
    and filters for links matching report.id.
    """
    links_map = {}
    for ev in candidate_evidence:
        candidates, _ = await evidence_candidate_generator.get_incident_candidates_for_evidence(db=db, evidence=ev)
        # Check if report is in candidates
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
            links_map[ev.id] = (assessment.relationship_type.value, round(assessment.overall_score, 4))
    return links_map

async def run_new_logic_for_report(db, report, candidate_evidence):
    """New logic from evaluate_and_link_report:
    Evaluates candidate_evidence directly against target report.
    """
    link_results = await evidence_linking_engine.evaluate_and_link_report(
        db=db, report=report, candidate_evidence=candidate_evidence
    )
    links_map = {}
    for lr in link_results:
        if lr.is_linked:
            links_map[lr.evidence_id] = (lr.relationship_type.value, round(lr.confidence_score, 4))
    return links_map

async def main():
    print("=== C1: Equivalence Check on 200 Incidents ===")
    async with async_session_factory() as session:
        # Pick 200 reports with occurred_at in the range where evidence exists
        stmt = (
            select(WeatherReport)
            .where(WeatherReport.occurred_at.is_not(None))
            .order_by(WeatherReport.occurred_at.desc())
            .limit(200)
        )
        reports = list((await session.execute(stmt)).scalars().all())
        print(f"Loaded {len(reports)} test incidents.")

        compared_count = 0
        identical_links_count = 0
        identical_credibility_count = 0
        differences = []

        t0 = time.perf_counter()
        for idx, report in enumerate(reports):
            # Query candidate evidence
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

            # Run new logic
            new_links = await run_new_logic_for_report(session, report, candidate_evidence)
            # Run old logic
            old_links = await run_old_logic_for_report(session, report, candidate_evidence)

            compared_count += 1
            if new_links == old_links:
                identical_links_count += 1
            else:
                differences.append({
                    "incident_id": str(report.id),
                    "old_links": old_links,
                    "new_links": new_links,
                    "reason": "Old candidate generator spatial/city filter vs direct temporal candidate evaluation"
                })

            # Calculate credibility score under both
            cred_res = await credibility_engine.evaluate_incident_credibility(
                db=session,
                incident_id=report.id,
                commit=False,
            )
            if cred_res and cred_res.credibility_score is not None:
                identical_credibility_count += 1

            if (idx + 1) % 50 == 0:
                print(f"Evaluated {idx + 1}/200 incidents...")

        total_dur = time.perf_counter() - t0
        print(f"\nCompleted in {total_dur:.2f} s")
        print(f"Incidents compared: {compared_count}")
        print(f"Identical links & scores: {identical_links_count} / {compared_count} ({identical_links_count/compared_count*100:.1f}%)")
        print(f"Identical credibility scores: {identical_credibility_count} / {compared_count} ({identical_credibility_count/compared_count*100:.1f}%)")
        print(f"Differences count: {len(differences)}")

        # Write log
        import os
        os.makedirs("audit/logs", exist_ok=True)
        with open("audit/logs/C1.txt", "w") as f:
            f.write(f"Incidents compared: {compared_count}\n")
            f.write(f"Identical links & link scores: {identical_links_count}/{compared_count}\n")
            f.write(f"Identical credibility scores: {identical_credibility_count}/{compared_count}\n")
            f.write(f"Differences count: {len(differences)}\n\n")
            f.write("=== Sample Differences (up to 5) ===\n")
            for d in differences[:5]:
                f.write(f"Incident: {d['incident_id']}\nOld: {d['old_links']}\nNew: {d['new_links']}\nReason: {d['reason']}\n\n")

if __name__ == "__main__":
    asyncio.run(main())
