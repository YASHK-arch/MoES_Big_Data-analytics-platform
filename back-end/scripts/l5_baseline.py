"""
L5 Item 1: Baseline evaluation of K1 hoax and genuine posts.

Runs synthetic hoax posts (foreign/different-location) and genuine posts through
the current credibility scorer to establish pre-signal baselines.

SYNTHETIC DATA: All posts are agent-authored for evaluation only.
NOT REAL INCIDENTS. No real-world misinformation claims are made.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import uuid
from app.intelligence.credibility_scorer import CredibilityScorer
from app.intelligence.schemas import IncidentCredibilityInputs, SourceFamily

# Isolated scorer – feature flag OFF (default)
scorer = CredibilityScorer()

# ─── SYNTHETIC K1 HOAX POSTS ──────────────────────────────────────────────────
# 5 posts mentioning a foreign/different-location that scored ~0.5427 in K1
# Each has complete metadata (coords, time, location_name, description, category)
# because they were quality posts – just geographically dishonest.

HOAX_POSTS = [
    {
        "id": "H1",
        "label": "Foreign-location hoax: text says Kathmandu, declared Mumbai",
        "inputs": IncidentCredibilityInputs(
            incident_id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
            source_code="CITIZEN_WEB",
            source_type="CITIZEN_REPORT",
            source_base_trust=0.60,
            origin_family=SourceFamily.CITIZEN,
            has_coordinates=True,   # coords submitted for Mumbai
            has_timestamp=True,
            has_location_name=True, # location_name="Mumbai"
            has_description=True,
            has_category=True,
            cluster_member_count=1,
        ),
    },
    {
        "id": "H2",
        "label": "Foreign-location hoax: text says Nepal flooding, declared Delhi",
        "inputs": IncidentCredibilityInputs(
            incident_id=uuid.UUID("00000000-0000-0000-0000-000000000002"),
            source_code="CITIZEN_WEB",
            source_type="CITIZEN_REPORT",
            source_base_trust=0.60,
            origin_family=SourceFamily.CITIZEN,
            has_coordinates=True,
            has_timestamp=True,
            has_location_name=True,
            has_description=True,
            has_category=True,
            cluster_member_count=1,
        ),
    },
    {
        "id": "H3",
        "label": "Different-state hoax: text says Bengaluru floods, declared Chennai",
        "inputs": IncidentCredibilityInputs(
            incident_id=uuid.UUID("00000000-0000-0000-0000-000000000003"),
            source_code="CITIZEN_WEB",
            source_type="CITIZEN_REPORT",
            source_base_trust=0.60,
            origin_family=SourceFamily.CITIZEN,
            has_coordinates=True,
            has_timestamp=True,
            has_location_name=True,
            has_description=True,
            has_category=True,
            cluster_member_count=1,
        ),
    },
    {
        "id": "H4",
        "label": "Different-state hoax: text says Colombo flood, declared Kochi",
        "inputs": IncidentCredibilityInputs(
            incident_id=uuid.UUID("00000000-0000-0000-0000-000000000004"),
            source_code="CITIZEN_WEB",
            source_type="CITIZEN_REPORT",
            source_base_trust=0.60,
            origin_family=SourceFamily.CITIZEN,
            has_coordinates=True,
            has_timestamp=True,
            has_location_name=True,
            has_description=True,
            has_category=True,
            cluster_member_count=1,
        ),
    },
    {
        "id": "H5",
        "label": "Different-state hoax: text says Dhaka cyclone, declared Kolkata",
        "inputs": IncidentCredibilityInputs(
            incident_id=uuid.UUID("00000000-0000-0000-0000-000000000005"),
            source_code="CITIZEN_WEB",
            source_type="CITIZEN_REPORT",
            source_base_trust=0.60,
            origin_family=SourceFamily.CITIZEN,
            has_coordinates=True,
            has_timestamp=True,
            has_location_name=True,
            has_description=True,
            has_category=True,
            cluster_member_count=1,
        ),
    },
]

# ─── SYNTHETIC GENUINE POSTS ──────────────────────────────────────────────────
# 5 genuine posts: text and declared location are consistent

GENUINE_POSTS = [
    {
        "id": "G1",
        "label": "Genuine: text says Mumbai flooding, declared Mumbai",
        "inputs": IncidentCredibilityInputs(
            incident_id=uuid.UUID("00000000-0000-0000-0000-000000000011"),
            source_code="CITIZEN_WEB",
            source_type="CITIZEN_REPORT",
            source_base_trust=0.60,
            origin_family=SourceFamily.CITIZEN,
            has_coordinates=True,
            has_timestamp=True,
            has_location_name=True,
            has_description=True,
            has_category=True,
            cluster_member_count=1,
        ),
    },
    {
        "id": "G2",
        "label": "Genuine: text says Guwahati floods, declared Assam",
        "inputs": IncidentCredibilityInputs(
            incident_id=uuid.UUID("00000000-0000-0000-0000-000000000012"),
            source_code="CITIZEN_WEB",
            source_type="CITIZEN_REPORT",
            source_base_trust=0.60,
            origin_family=SourceFamily.CITIZEN,
            has_coordinates=True,
            has_timestamp=True,
            has_location_name=True,
            has_description=True,
            has_category=True,
            cluster_member_count=1,
        ),
    },
    {
        "id": "G3",
        "label": "Genuine: text says Chennai cyclone, declared Tamil Nadu",
        "inputs": IncidentCredibilityInputs(
            incident_id=uuid.UUID("00000000-0000-0000-0000-000000000013"),
            source_code="CITIZEN_WEB",
            source_type="CITIZEN_REPORT",
            source_base_trust=0.60,
            origin_family=SourceFamily.CITIZEN,
            has_coordinates=True,
            has_timestamp=True,
            has_location_name=True,
            has_description=True,
            has_category=True,
            cluster_member_count=1,
        ),
    },
    {
        "id": "G4",
        "label": "Genuine: text says Bengaluru hailstorm, declared Karnataka",
        "inputs": IncidentCredibilityInputs(
            incident_id=uuid.UUID("00000000-0000-0000-0000-000000000014"),
            source_code="CITIZEN_WEB",
            source_type="CITIZEN_REPORT",
            source_base_trust=0.60,
            origin_family=SourceFamily.CITIZEN,
            has_coordinates=True,
            has_timestamp=True,
            has_location_name=True,
            has_description=True,
            has_category=True,
            cluster_member_count=1,
        ),
    },
    {
        "id": "G5",
        "label": "Genuine: text says Delhi smog, declared Delhi",
        "inputs": IncidentCredibilityInputs(
            incident_id=uuid.UUID("00000000-0000-0000-0000-000000000015"),
            source_code="CITIZEN_WEB",
            source_type="CITIZEN_REPORT",
            source_base_trust=0.60,
            origin_family=SourceFamily.CITIZEN,
            has_coordinates=True,
            has_timestamp=True,
            has_location_name=True,
            has_description=True,
            has_category=True,
            cluster_member_count=1,
        ),
    },
]


def run_and_print(posts: list, group_label: str) -> list:
    scores = []
    print(f"\n{'='*70}")
    print(f"GROUP: {group_label}")
    print(f"{'='*70}")
    for post in posts:
        bd = scorer.score_incident(post["inputs"])
        scores.append(bd.final_credibility_score)
        print(f"\n  Post {post['id']}: {post['label']}")
        print(f"  final_credibility_score : {bd.final_credibility_score:.4f}")
        print(f"  source_prior            : {bd.source_prior:.4f}")
        print(f"  report_quality_score    : {bd.report_quality_score:.4f}")
        print(f"  incident_baseline       : {bd.incident_baseline:.4f}")
        print(f"  crowd_cluster_score     : {bd.crowd_cluster_score:.4f}")
        print(f"  digital_evidence_score  : {bd.digital_evidence_score:.4f}")
        print(f"  physical_obs_score      : {bd.physical_observation_score:.4f}")
        print(f"  synthesized_support     : {bd.synthesized_support:.4f}")
        print(f"  diversity_multiplier    : {bd.diversity_multiplier:.4f}")
        print(f"  support_delta           : {bd.support_delta:.4f}")
        print(f"  positive_score          : {bd.positive_score:.4f}")
        print(f"  negative_penalty        : {bd.negative_penalty:.4f}")
        print(f"  penalized_score         : {bd.penalized_score:.4f}")
        print(f"  applied_cap             : {bd.applied_cap:.4f}")
    print(f"\n  SUMMARY {group_label}:")
    print(f"    mean={sum(scores)/len(scores):.4f}  min={min(scores):.4f}  max={max(scores):.4f}")
    return scores


def main():
    print("L5 Item 1: K1 Baseline (FEATURE FLAG=OFF, pre-signal)")
    print("SYNTHETIC POSTS — AGENT-AUTHORED, NOT REAL INCIDENTS")

    h_scores = run_and_print(HOAX_POSTS, "HOAX (foreign/different-location)")
    g_scores = run_and_print(GENUINE_POSTS, "GENUINE (location-consistent)")

    print("\n" + "="*70)
    print("CROSS-GROUP SUMMARY")
    print("="*70)
    print(f"  HOAX    mean={sum(h_scores)/len(h_scores):.4f}  min={min(h_scores):.4f}  max={max(h_scores):.4f}")
    print(f"  GENUINE mean={sum(g_scores)/len(g_scores):.4f}  min={min(g_scores):.4f}  max={max(g_scores):.4f}")
    print(f"\n  Review line = 0.45")
    print(f"  HOAX above 0.45: {sum(1 for s in h_scores if s > 0.45)}/{len(h_scores)}")
    print(f"  GENUINE above 0.45: {sum(1 for s in g_scores if s > 0.45)}/{len(g_scores)}")

    # Explain which components produce the score for H1 specifically
    print("\n" + "="*70)
    print("COMPONENT TRACE: H1 (the canonical foreign-location hoax)")
    print("="*70)
    bd = scorer.score_incident(HOAX_POSTS[0]["inputs"])
    print(f"  source_base_trust=0.60, all metadata=True, cluster=1, no evidence, no obs")
    print(f"  quality = 0.30*1+0.25*1+0.20*1+0.15*1+0.10*1 = 1.00")
    print(f"  b_incident = 0.60 * (0.70 + 0.30*1.00) = 0.60 * 1.00 = {0.60*1.00:.4f}")
    print(f"  s_crowd=0, s_evidence=0, s_obs=0 -> s_support=0, delta_support=0")
    print(f"  c_positive = b_incident = {bd.incident_baseline:.4f}")
    print(f"  p_negative = 0 (no contradictions)")
    print(f"  applicable_cap = cap_citizen = 0.65 (no corroboration)")
    print(f"  final = min(c_positive={bd.positive_score:.4f}, cap=0.65) = {bd.final_credibility_score:.4f}")
    print(f"\n  RESULT: Signal is absent because no component penalizes location mismatch.")
    print(f"  The score {bd.final_credibility_score:.4f} is purely from source_prior × quality_score × base_factor.")

    print("\n" + "="*70)
    print("PYTEST BASELINE COUNT")
    print("="*70)
    print("  [Run separately: cd back-end && python -m pytest tests/ --co -q | tail -1]")
    print("  Baseline count: 523 tests collected (see L5_1.log)")


if __name__ == "__main__":
    main()
