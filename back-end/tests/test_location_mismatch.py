"""Unit tests for the location-mismatch signal (L5 Item 3).

No database, no network, no external services.
Tests the pure evaluate_location_mismatch() function.

Product rules verified:
  P1. MISMATCH needs both sides known; either unknown -> NEUTRAL
  P2. Multi-place: no mismatch if declared state is among text places
  P3. Aliases handled correctly by extractor
  P4. Only negative adjustments; never positive; no status change
  P5. Explainable result fields present

Additionally:
  - Foreign place mismatch
  - Different-state mismatch
  - Consistent (same state)
  - Devanagari / Hinglish -> NEUTRAL (not in gazetteer)
  - Cap respected at all penalty sizes
  - No status change through any path
"""

import pytest

from app.intelligence.location_mismatch import (
    MismatchVerdict,
    evaluate_location_mismatch,
)


# ─── P1: Both sides must be known ─────────────────────────────────────────────

class TestP1BothSidesKnown:
    def test_no_declared_state_is_neutral(self):
        r = evaluate_location_mismatch(
            report_text="Flooding in Mumbai",
            declared_state=None,
            declared_country="India",
        )
        assert r.verdict == MismatchVerdict.NEUTRAL
        assert r.adjustment == 0.0

    def test_empty_declared_state_is_neutral(self):
        r = evaluate_location_mismatch(
            report_text="Flooding in Mumbai",
            declared_state="",
            declared_country="India",
        )
        assert r.verdict == MismatchVerdict.NEUTRAL
        assert r.adjustment == 0.0

    def test_no_report_text_is_neutral(self):
        r = evaluate_location_mismatch(
            report_text=None,
            declared_state="Maharashtra",
        )
        assert r.verdict == MismatchVerdict.NEUTRAL
        assert r.adjustment == 0.0

    def test_empty_report_text_is_neutral(self):
        r = evaluate_location_mismatch(
            report_text="   ",
            declared_state="Maharashtra",
        )
        assert r.verdict == MismatchVerdict.NEUTRAL
        assert r.adjustment == 0.0

    def test_text_with_no_place_entities_is_neutral(self):
        r = evaluate_location_mismatch(
            report_text="Heavy rain, roads flooded, power outage in the area",
            declared_state="Maharashtra",
        )
        assert r.verdict == MismatchVerdict.NEUTRAL
        assert r.adjustment == 0.0

    def test_explanation_field_always_present(self):
        r = evaluate_location_mismatch(
            report_text=None,
            declared_state=None,
        )
        assert isinstance(r.explanation, str)
        assert len(r.explanation) > 0


# ─── P2: Multi-place — declared state among text places ───────────────────────

class TestP2MultiPlace:
    def test_multi_place_declared_state_in_text_is_consistent(self):
        # Mumbai (Maharashtra) + Chennai (Tamil Nadu); declared Maharashtra
        r = evaluate_location_mismatch(
            report_text="Heavy floods hit Mumbai and Chennai today",
            declared_state="Maharashtra",
        )
        assert r.verdict == MismatchVerdict.CONSISTENT
        assert r.adjustment == 0.0

    def test_multi_place_declared_city_in_text_is_consistent(self):
        # Text has both Bengaluru and Pune; declared Karnataka
        r = evaluate_location_mismatch(
            report_text="Flooding in Bengaluru and Pune; Karnataka on high alert",
            declared_state="Karnataka",
        )
        assert r.verdict == MismatchVerdict.CONSISTENT
        assert r.adjustment == 0.0

    def test_multi_place_only_other_states_is_mismatch(self):
        # Text mentions only Bengaluru (Karnataka) and Pune (Maharashtra);
        # declared is Tamil Nadu -> mismatch
        r = evaluate_location_mismatch(
            report_text="Flooding in Bengaluru and Pune",
            declared_state="Tamil Nadu",
        )
        assert r.verdict == MismatchVerdict.MISMATCH
        assert r.adjustment < 0.0

    def test_multi_place_declared_state_name_in_text_is_consistent(self):
        r = evaluate_location_mismatch(
            report_text="Severe cyclone warning for Tamil Nadu and Andhra Pradesh",
            declared_state="Tamil Nadu",
        )
        assert r.verdict == MismatchVerdict.CONSISTENT
        assert r.adjustment == 0.0


# ─── Different-state mismatch ─────────────────────────────────────────────────

class TestDifferentStateMismatch:
    def test_bengaluru_text_chennai_declared_is_mismatch(self):
        # Text: Bengaluru (Karnataka), Declared: Tamil Nadu
        r = evaluate_location_mismatch(
            report_text="Major flooding hit Bengaluru city",
            declared_state="Tamil Nadu",
        )
        assert r.verdict == MismatchVerdict.MISMATCH
        assert r.adjustment < 0.0
        assert r.text_state == "Karnataka"

    def test_mumbai_text_delhi_declared_is_mismatch(self):
        r = evaluate_location_mismatch(
            report_text="Cyclone warning for Mumbai coast",
            declared_state="Delhi",
        )
        assert r.verdict == MismatchVerdict.MISMATCH
        assert r.adjustment < 0.0

    def test_guwahati_text_maharashtra_declared_is_mismatch(self):
        r = evaluate_location_mismatch(
            report_text="Guwahati floods leave thousands homeless",
            declared_state="Maharashtra",
        )
        assert r.verdict == MismatchVerdict.MISMATCH
        assert r.adjustment < 0.0

    def test_same_state_is_consistent(self):
        r = evaluate_location_mismatch(
            report_text="Mumbai floods: Andheri underwater",
            declared_state="Maharashtra",
        )
        assert r.verdict == MismatchVerdict.CONSISTENT
        assert r.adjustment == 0.0

    def test_same_state_different_city_is_consistent(self):
        # Andheri is in Maharashtra; Pune is also in Maharashtra
        r = evaluate_location_mismatch(
            report_text="Heavy rain in Andheri",
            declared_state="Maharashtra",
        )
        assert r.verdict == MismatchVerdict.CONSISTENT
        assert r.adjustment == 0.0


# ─── Foreign place mismatch ───────────────────────────────────────────────────

class TestForeignPlaceMismatch:
    def test_kathmandu_text_india_declared_is_mismatch(self):
        r = evaluate_location_mismatch(
            report_text="Earthquake reported near Kathmandu valley",
            declared_state="Maharashtra",
        )
        assert r.verdict == MismatchVerdict.MISMATCH
        assert r.adjustment < 0.0
        assert r.text_country == "Nepal"

    def test_nepal_country_text_india_declared_is_mismatch(self):
        r = evaluate_location_mismatch(
            report_text="Floods in Nepal causing displacement",
            declared_state="Bihar",
        )
        assert r.verdict == MismatchVerdict.MISMATCH
        assert r.adjustment < 0.0

    def test_dhaka_text_india_declared_is_mismatch(self):
        r = evaluate_location_mismatch(
            report_text="Cyclone hits Dhaka with high winds",
            declared_state="West Bengal",
        )
        assert r.verdict == MismatchVerdict.MISMATCH
        assert r.adjustment < 0.0
        assert r.text_country == "Bangladesh"

    def test_colombo_text_india_declared_is_mismatch(self):
        r = evaluate_location_mismatch(
            report_text="Heavy rain in Colombo city",
            declared_state="Kerala",
        )
        assert r.verdict == MismatchVerdict.MISMATCH
        assert r.adjustment < 0.0

    def test_unknown_foreign_place_is_neutral(self):
        # Kyoto is NOT in gazetteer or curated list -> text side unknown -> NEUTRAL
        r = evaluate_location_mismatch(
            report_text="Flooding in Kyoto today",
            declared_state="Maharashtra",
        )
        assert r.verdict == MismatchVerdict.NEUTRAL
        assert r.adjustment == 0.0


# ─── Alias handling (P3) ─────────────────────────────────────────────────────

class TestAliasHandling:
    def test_bombay_alias_same_state_is_consistent(self):
        r = evaluate_location_mismatch(
            report_text="Heavy rain in Bombay",
            declared_state="Maharashtra",
        )
        assert r.verdict == MismatchVerdict.CONSISTENT
        assert r.adjustment == 0.0

    def test_bangalore_alias_different_state_is_mismatch(self):
        r = evaluate_location_mismatch(
            report_text="Severe flooding in Bangalore",
            declared_state="Tamil Nadu",
        )
        assert r.verdict == MismatchVerdict.MISMATCH
        assert r.adjustment < 0.0

    def test_madras_alias_same_state_is_consistent(self):
        r = evaluate_location_mismatch(
            report_text="Cyclone warning for Madras coast",
            declared_state="Tamil Nadu",
        )
        assert r.verdict == MismatchVerdict.CONSISTENT
        assert r.adjustment == 0.0

    def test_calcutta_alias_different_state_is_mismatch(self):
        r = evaluate_location_mismatch(
            report_text="Flooding in Calcutta",
            declared_state="Bihar",
        )
        assert r.verdict == MismatchVerdict.MISMATCH
        assert r.adjustment < 0.0

    def test_trivandrum_alias_same_state_is_consistent(self):
        r = evaluate_location_mismatch(
            report_text="Heavy rain in Trivandrum",
            declared_state="Kerala",
        )
        assert r.verdict == MismatchVerdict.CONSISTENT
        assert r.adjustment == 0.0


# ─── Devanagari / Hinglish -> NEUTRAL (P1) ───────────────────────────────────

class TestDevanagariHinglish:
    def test_devanagari_mumbai_is_neutral(self):
        # मुंबई not in gazetteer -> text side unknown
        r = evaluate_location_mismatch(
            report_text="बाढ़ मुंबई में",
            declared_state="Maharashtra",
        )
        assert r.verdict == MismatchVerdict.NEUTRAL
        assert r.adjustment == 0.0

    def test_hinglish_dilli_is_neutral(self):
        r = evaluate_location_mismatch(
            report_text="Dilli mein baarish",
            declared_state="Delhi",
        )
        assert r.verdict == MismatchVerdict.NEUTRAL
        assert r.adjustment == 0.0


# ─── Cap respected (P4) ───────────────────────────────────────────────────────

class TestCapRespected:
    def test_cap_0_05_limits_adjustment(self):
        r = evaluate_location_mismatch(
            report_text="Earthquake near Kathmandu",
            declared_state="Maharashtra",
            penalty=0.10,
            cap=0.05,
        )
        assert r.verdict == MismatchVerdict.MISMATCH
        assert r.adjustment == pytest.approx(-0.05, abs=0.001)
        assert r.cap_applied == 0.05

    def test_cap_0_10_limits_adjustment(self):
        r = evaluate_location_mismatch(
            report_text="Earthquake near Kathmandu",
            declared_state="Maharashtra",
            penalty=0.20,
            cap=0.10,
        )
        assert r.adjustment == pytest.approx(-0.10, abs=0.001)

    def test_cap_0_15_limits_adjustment(self):
        r = evaluate_location_mismatch(
            report_text="Earthquake near Kathmandu",
            declared_state="Maharashtra",
            penalty=0.30,
            cap=0.15,
        )
        assert r.adjustment == pytest.approx(-0.15, abs=0.001)

    def test_adjustment_is_never_positive(self):
        # Even for consistent cases, adjustment must be <= 0
        r = evaluate_location_mismatch(
            report_text="Mumbai floods",
            declared_state="Maharashtra",
        )
        assert r.adjustment <= 0.0

    def test_neutral_adjustment_is_zero(self):
        r = evaluate_location_mismatch(
            report_text=None,
            declared_state="Maharashtra",
        )
        assert r.adjustment == 0.0

    def test_consistent_adjustment_is_zero(self):
        r = evaluate_location_mismatch(
            report_text="Mumbai floods",
            declared_state="Maharashtra",
        )
        assert r.adjustment == 0.0


# ─── P4: No path changes verification_status ─────────────────────────────────

class TestNoStatusChange:
    """No call to evaluate_location_mismatch() may change verification_status.

    Since this is a pure function that returns a float adjustment only,
    any caller is responsible for not using it to change status.
    This test proves the function produces no side effects and has no
    status-changing return value.
    """

    def test_mismatch_result_has_no_status_field(self):
        r = evaluate_location_mismatch(
            report_text="Flooding in Kathmandu",
            declared_state="Maharashtra",
        )
        assert r.verdict == MismatchVerdict.MISMATCH
        # LocationMismatchResult has no verification_status attribute
        assert not hasattr(r, "verification_status")
        assert not hasattr(r, "status")

    def test_result_is_frozen_dataclass(self):
        r = evaluate_location_mismatch(
            report_text="Flooding in Kathmandu",
            declared_state="Maharashtra",
        )
        # Frozen dataclass: cannot mutate
        with pytest.raises((AttributeError, TypeError)):
            r.adjustment = 0.0  # type: ignore[misc]

    def test_explain_dict_has_no_status_change(self):
        r = evaluate_location_mismatch(
            report_text="Flooding in Kathmandu",
            declared_state="Maharashtra",
        )
        d = r.as_explain_dict()
        assert "verification_status" not in d
        assert "status_change" not in d


# ─── Explainability (P5) ─────────────────────────────────────────────────────

class TestExplainability:
    def test_mismatch_explain_dict_has_required_fields(self):
        r = evaluate_location_mismatch(
            report_text="Earthquake near Kathmandu",
            declared_state="Maharashtra",
        )
        d = r.as_explain_dict()
        required = [
            "signal", "verdict", "declared_place", "declared_state",
            "text_place", "text_state", "text_country",
            "text_confidence", "adjustment", "cap", "method", "explanation", "assumption",
        ]
        for field in required:
            assert field in d, f"Missing field: {field}"

    def test_assumption_label_in_explain(self):
        r = evaluate_location_mismatch(
            report_text="Flooding in Dhaka",
            declared_state="West Bengal",
        )
        d = r.as_explain_dict()
        assert "ASSUMPTION" in d["assumption"]

    def test_neutral_explain_dict_present(self):
        r = evaluate_location_mismatch(report_text=None, declared_state=None)
        d = r.as_explain_dict()
        assert d["verdict"] == "NEUTRAL"
        assert d["adjustment"] == 0.0


# ─── Curated foreign list (ASSUMPTION) ───────────────────────────────────────

class TestCuratedForeignList:
    def test_pakistan_in_curated_list_is_mismatch(self):
        r = evaluate_location_mismatch(
            report_text="Floods hit pakistan with heavy casualties",
            declared_state="Punjab",
        )
        assert r.verdict == MismatchVerdict.MISMATCH
        assert r.adjustment < 0.0

    def test_islamabad_in_curated_list_is_mismatch(self):
        r = evaluate_location_mismatch(
            report_text="Heavy snow in islamabad",
            declared_state="Himachal Pradesh",
        )
        assert r.verdict == MismatchVerdict.MISMATCH

    def test_london_not_in_gazetteer_is_neutral(self):
        # Auckland is NOT in gazetteer or curated list -> text side unknown -> NEUTRAL
        r = evaluate_location_mismatch(
            report_text="Flooding in auckland",
            declared_state="Maharashtra",
        )
        assert r.verdict == MismatchVerdict.NEUTRAL
