"""Evaluate S1 Physical Weather Corroboration on the full 504-report baseline.

Produces:
(a) Full before/after credibility table across all 504 reports by category.
(b) Total-cap sensitivity analysis at 0.05, 0.10, and 0.15.
(c) K1 hoax vs genuine control re-run with exact per-post scores and deltas.
(d) Detailed 0.45 threshold crossings count in each direction.
"""

import asyncio
import os
import sys
from collections import defaultdict
from typing import Dict, List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

# Add back-end to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../back-end")))

from app.core.config import settings
from app.intelligence.credibility_collector import CredibilityCollector
from app.intelligence.credibility_scorer import CredibilityScorer
from app.intelligence.schemas import ContradictionInput, IncidentCredibilityInputs, PhysicalStationInput, SourceFamily
from app.models.report import WeatherReport


DB_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@localhost:5432/weather_platform_s1"
)


async def evaluate_504_baseline():
    engine = create_async_engine(DB_URL, echo=False)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    collector = CredibilityCollector()

    async with session_factory() as session:
        stmt = select(WeatherReport).order_by(WeatherReport.created_at)
        res = await session.execute(stmt)
        reports: List[WeatherReport] = list(res.scalars().all())

        print(f"Total reports loaded from database: {len(reports)}")

        # Collect raw inputs for all reports
        inputs_with_phys = []
        inputs_without_phys = []
        categories = []
        report_ids = []

        for r in reports:
            inp = await collector.collect_inputs(session, r.id)
            if not inp:
                continue

            # Full inputs with physical weather corroboration
            inputs_with_phys.append(inp)
            categories.append(r.reported_category or "OTHER")
            report_ids.append(r.id)

            # Strip physical weather corroboration for pure baseline
            # Physical weather stations have keys starting with 'OPEN_METEO' or 'IMD' or 'SIMULATED' or 'FIXTURE'
            non_phys_stations = [
                stn for stn in inp.observation_stations
                if not any(k in stn.station_key for k in ["OPEN_METEO", "IMD", "SIMULATED", "FIXTURE"])
            ]
            non_phys_contradictions = [
                c for c in inp.negative_contradictions
                if not any(k in c.signal_source_key for k in ["phys_OPEN_METEO", "phys_IMD", "phys_SIMULATED", "phys_FIXTURE"])
            ]

            inp_baseline = inp.model_copy(deep=True)
            inp_baseline.observation_stations = non_phys_stations
            inp_baseline.negative_contradictions = non_phys_contradictions
            inputs_without_phys.append(inp_baseline)

    await engine.dispose()

    n = len(inputs_with_phys)
    print(f"Successfully processed {n} reports for credibility evaluation.\n")

    # Baseline scores (total_physical_cap=None, physical disabled)
    scorer_base = CredibilityScorer(total_physical_cap=None)
    base_scores = [scorer_base.score_incident(inp).final_credibility_score for inp in inputs_without_phys]

    # Evaluate caps: 0.05, 0.10, 0.15
    caps = [0.05, 0.10, 0.15]
    results_by_cap = {}

    for cap in caps:
        scorer = CredibilityScorer(total_physical_cap=cap)
        cap_scores = [scorer.score_incident(inp).final_credibility_score for inp in inputs_with_phys]

        deltas = [round(c - b, 4) for c, b in zip(cap_scores, base_scores)]
        
        # Cross 0.45 counts
        # Direction 1: below 0.45 before -> above 0.45 after
        cross_up = sum(1 for b, c in zip(base_scores, cap_scores) if b < 0.45 and c >= 0.45)
        # Direction 2: above 0.45 before -> below 0.45 after
        cross_down = sum(1 for b, c in zip(base_scores, cap_scores) if b >= 0.45 and c < 0.45)

        # By category stats
        cat_deltas = defaultdict(list)
        for cat, d in zip(categories, deltas):
            cat_deltas[cat].append(d)

        results_by_cap[cap] = {
            "scores": cap_scores,
            "deltas": deltas,
            "mean_delta": sum(deltas) / len(deltas),
            "max_delta": max(deltas),
            "min_delta": min(deltas),
            "cross_up": cross_up,
            "cross_down": cross_down,
            "cat_deltas": cat_deltas,
        }

    # Print (a) Before / After table at default cap 0.10 across 504 reports
    cap10 = results_by_cap[0.10]
    print("==========================================================================================")
    print(f"S1 PHYSICAL CORROBORATION BEFORE / AFTER CREDIBILITY TABLE (504 REPORTS, DEFAULT CAP 0.10)")
    print("==========================================================================================")
    print(f"Overall Mean Baseline: {sum(base_scores)/n:.4f} | Overall Mean After: {sum(cap10['scores'])/n:.4f} | Overall Mean Delta: {cap10['mean_delta']:+.4f}")
    print(f"Max Delta: {cap10['max_delta']:+.4f} | Min Delta: {cap10['min_delta']:+.4f}")
    print(f"Crossings of 0.45 threshold: {cap10['cross_up']} crossed up (<0.45 -> >=0.45), {cap10['cross_down']} crossed down (>=0.45 -> <0.45)\n")

    print(f"{'Category':<26} | {'Count':<5} | {'Mean Base':<10} | {'Mean After':<10} | {'Mean Delta':<10} | {'Max Delta':<10} | {'Min Delta':<10}")
    print("-" * 92)
    for cat in sorted(cap10["cat_deltas"].keys()):
        cd = cap10["cat_deltas"][cat]
        cat_indices = [i for i, c in enumerate(categories) if c == cat]
        cat_base = [base_scores[i] for i in cat_indices]
        cat_after = [cap10["scores"][i] for i in cat_indices]
        m_base = sum(cat_base) / len(cat_base)
        m_after = sum(cat_after) / len(cat_after)
        m_delta = sum(cd) / len(cd)
        mx_delta = max(cd)
        mn_delta = min(cd)
        print(f"{cat:<26} | {len(cd):<5} | {m_base:<10.4f} | {m_after:<10.4f} | {m_delta:<+10.4f} | {mx_delta:<+10.4f} | {mn_delta:<+10.4f}")

    # Print (b) Total-Cap Sensitivity Analysis at 0.05, 0.10, 0.15
    print("\n==========================================================================================")
    print("TOTAL-CAP SENSITIVITY ANALYSIS AT 0.05 / 0.10 / 0.15 (504 REPORTS)")
    print("==========================================================================================")
    for cap in caps:
        r = results_by_cap[cap]
        print(f"\n--- TOTAL PHYSICAL CAP = {cap:.2f} ---")
        print(f"Overall Mean Delta: {r['mean_delta']:+.4f} | Max Delta: {r['max_delta']:+.4f} | Min Delta: {r['min_delta']:+.4f}")
        print(f"Cross 0.45 Threshold: {r['cross_up']} crossed up, {r['cross_down']} crossed down (Total crossings: {r['cross_up'] + r['cross_down']})")
        print(f"{'Category':<26} | {'Count':<5} | {'Mean Delta':<12} | {'Max Delta':<12}")
        print("-" * 60)
        for cat in sorted(r["cat_deltas"].keys()):
            cd = r["cat_deltas"][cat]
            print(f"{cat:<26} | {len(cd):<5} | {sum(cd)/len(cd):<+12.4f} | {max(cd):<+12.4f}")

    # Print (c) K1 Hoax vs Genuine Re-run
    print("\n==========================================================================================")
    print("K1 HOAX VS GENUINE POSTS EVALUATION UNDER S1")
    print("==========================================================================================")

    hoax_posts = [
        ("Old video: 2017 Florida hurricane reused as Mumbai cyclone", "CYCLONE_STORM", 0.50, 0.70, True),
        ("Old video: 2019 viral clip claimed as Dehradun cloudburst", "HEAVY_RAINFALL", 0.50, 0.70, True),
        ("Recycled 2015 Chennai flood clip shared on WhatsApp", "FLOOD_WATERLOGGING", 0.50, 0.70, True),
        ("Archived 2020 Bihar bridge collapse circulated as today", "FLOOD_WATERLOGGING", 0.50, 0.70, True),
        ("2004 Tsunami footage shared as Gujarat storm surge", "CYCLONE_STORM", 0.50, 0.70, True),
        ("Oklahoma tornado footage claimed as Bengaluru airport", "STRONG_WIND", 0.50, 0.55, False),
        ("Indonesia volcano ash claimed as Jaipur dust storm", "DUST_STORM", 0.50, 0.55, False),
        ("Chicago winter blizzard claimed as Marine Drive Mumbai", "STRONG_WIND", 0.50, 0.55, False),
        ("Phoenix Arizona haboob claimed as Delhi sandstorm", "DUST_STORM", 0.50, 0.55, False),
        ("NYC subway flood video claimed as Kolkata subway", "FLOOD_WATERLOGGING", 0.50, 0.55, False),
    ]

    genuine_posts = [
        ("Mumbai coast citizen check-in: cyclone winds and surge", "CYCLONE_STORM", 0.60, 0.70),
        ("Dehradun neighbourhood report: intense rainwater flooding", "HEAVY_RAINFALL", 0.60, 0.70),
        ("Chennai resident note: fresh waterlogging has commenced", "FLOOD_WATERLOGGING", 0.60, 0.70),
        ("Bihar local report: floodwater overtopping approach road", "FLOOD_WATERLOGGING", 0.60, 0.70),
        ("Gujarat coast resident report: cyclone-driven surges", "CYCLONE_STORM", 0.60, 0.70),
        ("Bengaluru airport witness describes storm winds and rain", "STRONG_WIND", 0.60, 0.70),
        ("Jaipur resident reports dust storm rolling over skyline", "DUST_STORM", 0.60, 0.70),
        ("Mumbai Marine Drive reports strong gusts and sea spray", "STRONG_WIND", 0.60, 0.70),
        ("Delhi resident reports severe dust storm near ring road", "DUST_STORM", 0.60, 0.70),
        ("Kolkata commuter reports heavy rain flooding subway tracks", "FLOOD_WATERLOGGING", 0.60, 0.70),
    ]

    print("\n--- HOAX POSTS (Without vs With Physical Corroboration Contradiction) ---")
    scorer_default = CredibilityScorer(total_physical_cap=0.10)
    for title, cat, trust, quality, has_reverse_image_contradiction in hoax_posts:
        # Base hoax input
        contras = []
        if has_reverse_image_contradiction:
            contras.append(
                ContradictionInput(
                    signal_source_key="evidence_reverse_image_match",
                    contradiction_score=0.85,
                    is_diagnostic=True,
                    is_physical_sensor=False,
                )
            )

        inp_hoax_base = IncidentCredibilityInputs(
            incident_id="00000000-0000-0000-0000-000000000001",
            source_code="CITIZEN_WEB",
            source_type="CITIZEN_REPORT",
            source_base_trust=trust,
            origin_family=SourceFamily.CITIZEN,
            has_coordinates=True,
            has_timestamp=True,
            has_location_name=True,
            has_description=True,
            has_category=True,
            cluster_member_count=1,
            evidence_groups=[],
            observation_stations=[],
            negative_contradictions=contras,
        )
        base_res = scorer_default.score_incident(inp_hoax_base)

        # Hoax with physical contradiction (e.g. station measures clear sky, 0 rain, calm wind)
        phys_contra = ContradictionInput(
            signal_source_key="phys_station_contradiction",
            contradiction_score=0.90,
            is_diagnostic=True,
            is_physical_sensor=True,
        )
        inp_hoax_phys = inp_hoax_base.model_copy(deep=True)
        inp_hoax_phys.negative_contradictions = contras + [phys_contra]
        phys_res = scorer_default.score_incident(inp_hoax_phys)

        delta = phys_res.final_credibility_score - base_res.final_credibility_score
        print(f"HOAX: {title:<52} | Base: {base_res.final_credibility_score:.4f} -> With Phys Contradiction: {phys_res.final_credibility_score:.4f} (Delta: {delta:+.4f})")

    print("\n--- GENUINE CONTROL POSTS (Without vs With Physical Support) ---")
    for title, cat, trust, quality in genuine_posts:
        inp_gen_base = IncidentCredibilityInputs(
            incident_id="00000000-0000-0000-0000-000000000002",
            source_code="CITIZEN_WEB",
            source_type="CITIZEN_REPORT",
            source_base_trust=trust,
            origin_family=SourceFamily.CITIZEN,
            has_coordinates=True,
            has_timestamp=True,
            has_location_name=True,
            has_description=True,
            has_category=True,
            cluster_member_count=1,
            evidence_groups=[],
            observation_stations=[],
            negative_contradictions=[],
        )
        base_res = scorer_default.score_incident(inp_gen_base)

        # Genuine with physical support (e.g. AWS confirms heavy rain)
        phys_support = PhysicalStationInput(
            station_key="phys_station_support",
            source_family=SourceFamily.SENSOR,
            corroboration_score=0.85,
            relationship_weight=1.00,
            points_count=3,
        )
        inp_gen_phys = inp_gen_base.model_copy(deep=True)
        inp_gen_phys.observation_stations = [phys_support]
        phys_res = scorer_default.score_incident(inp_gen_phys)

        delta = phys_res.final_credibility_score - base_res.final_credibility_score
        print(f"GENUINE: {title:<50} | Base: {base_res.final_credibility_score:.4f} -> With Phys Support: {phys_res.final_credibility_score:.4f} (Delta: {delta:+.4f})")


if __name__ == "__main__":
    asyncio.run(evaluate_504_baseline())
