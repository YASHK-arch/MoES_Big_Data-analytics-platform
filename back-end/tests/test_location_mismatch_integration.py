"""Integration tests for location-mismatch signal wired into CredibilityScorer (L5 Item 4).

Verifies that:
  - When flag=OFF (default): existing scores unchanged, lm_adjustment=0.0
  - When flag=ON: MISMATCH cases have negative adjustment, CONSISTENT/NEUTRAL unchanged
  - Backward compatibility: all callers with no report_text/declared_state are unaffected
  - Final score is always >= 0.0 and <= 0.98
  - Applied cap is never raised by the signal (P4: never positive)
  - Explainability field populated when active
"""

import uuid

import pytest

from app.intelligence.credibility_scorer import CredibilityScorer
from app.intelligence.schemas import IncidentCredibilityInputs, SourceFamily


def _make_inputs(**kwargs) -> IncidentCredibilityInputs:
    defaults = dict(
        incident_id=uuid.uuid4(),
        source_code="CITIZEN_WEB",
        source_type="CITIZEN_REPORT",
        source_base_trust=0.60,
        origin_family=SourceFamily.CITIZEN,
        has_coordinates=True,
        has_timestamp=True,
        has_location_name=True,
        has_description=True,
        has_category=True,
    )
    defaults.update(kwargs)
    return IncidentCredibilityInputs(**defaults)


class TestFlagOff:
    """With flag=OFF, the signal must not touch any score."""

    def test_no_report_text_no_adjustment(self):
        scorer = CredibilityScorer(location_mismatch_enabled=False)
        bd = scorer.score_incident(_make_inputs())
        assert bd.location_mismatch_adjustment == 0.0
        assert bd.location_mismatch_signal is None

    def test_mismatch_text_no_adjustment_when_flag_off(self):
        scorer = CredibilityScorer(location_mismatch_enabled=False)
        bd = scorer.score_incident(_make_inputs(
            report_text="Earthquake near Kathmandu",
            declared_state="Maharashtra",
        ))
        assert bd.location_mismatch_adjustment == 0.0
        # Score unchanged from what it would be without signal
        bd_ref = scorer.score_incident(_make_inputs())
        assert bd.final_credibility_score == bd_ref.final_credibility_score

    def test_consistent_text_no_adjustment_when_flag_off(self):
        scorer = CredibilityScorer(location_mismatch_enabled=False)
        bd = scorer.score_incident(_make_inputs(
            report_text="Mumbai flooding hits Andheri",
            declared_state="Maharashtra",
        ))
        assert bd.location_mismatch_adjustment == 0.0


class TestFlagOn:
    """With flag=ON, MISMATCH cases get negative adjustment."""

    def test_foreign_place_mismatch_reduces_score(self):
        scorer = CredibilityScorer(location_mismatch_enabled=True)
        bd_with = scorer.score_incident(_make_inputs(
            report_text="Earthquake near Kathmandu",
            declared_state="Maharashtra",
        ))
        bd_without = scorer.score_incident(_make_inputs())
        assert bd_with.location_mismatch_adjustment < 0.0
        assert bd_with.final_credibility_score < bd_without.final_credibility_score

    def test_different_state_mismatch_reduces_score(self):
        scorer = CredibilityScorer(location_mismatch_enabled=True)
        bd = scorer.score_incident(_make_inputs(
            report_text="Flooding in Bengaluru",
            declared_state="Tamil Nadu",
        ))
        assert bd.location_mismatch_adjustment < 0.0
        assert bd.final_credibility_score < 0.60  # baseline was 0.60

    def test_consistent_location_no_adjustment(self):
        scorer = CredibilityScorer(location_mismatch_enabled=True)
        bd = scorer.score_incident(_make_inputs(
            report_text="Flooding in Mumbai",
            declared_state="Maharashtra",
        ))
        assert bd.location_mismatch_adjustment == 0.0
        assert bd.final_credibility_score == pytest.approx(0.60, abs=0.001)

    def test_neutral_no_text_no_adjustment(self):
        scorer = CredibilityScorer(location_mismatch_enabled=True)
        bd = scorer.score_incident(_make_inputs(
            report_text=None,
            declared_state="Maharashtra",
        ))
        assert bd.location_mismatch_adjustment == 0.0

    def test_neutral_unknown_text_place_no_adjustment(self):
        # Kyoto not in gazetteer -> NEUTRAL -> no adjustment
        scorer = CredibilityScorer(location_mismatch_enabled=True)
        bd = scorer.score_incident(_make_inputs(
            report_text="Flooding in Kyoto today",
            declared_state="Maharashtra",
        ))
        assert bd.location_mismatch_adjustment == 0.0

    def test_score_never_below_zero(self):
        scorer = CredibilityScorer(location_mismatch_enabled=True)
        # Use very low trust source, large penalty
        bd = scorer.score_incident(_make_inputs(
            source_base_trust=0.10,
            report_text="Floods in Kathmandu",
            declared_state="Maharashtra",
        ))
        assert bd.final_credibility_score >= 0.0

    def test_score_never_above_max(self):
        scorer = CredibilityScorer(location_mismatch_enabled=True)
        bd = scorer.score_incident(_make_inputs(
            report_text="Flooding in Bengaluru",
            declared_state="Tamil Nadu",
        ))
        assert bd.final_credibility_score <= 0.98

    def test_adjustment_never_positive(self):
        scorer = CredibilityScorer(location_mismatch_enabled=True)
        bd = scorer.score_incident(_make_inputs(
            report_text="Flooding in Mumbai",
            declared_state="Maharashtra",
        ))
        assert bd.location_mismatch_adjustment <= 0.0


class TestExplainabilityIntegration:
    """When active and MISMATCH, signal dict is populated with required fields."""

    def test_mismatch_signal_dict_present(self):
        scorer = CredibilityScorer(location_mismatch_enabled=True)
        bd = scorer.score_incident(_make_inputs(
            report_text="Earthquake near Kathmandu",
            declared_state="Maharashtra",
        ))
        assert bd.location_mismatch_signal is not None
        d = bd.location_mismatch_signal
        assert d["verdict"] == "MISMATCH"
        assert d["adjustment"] < 0.0
        assert "ASSUMPTION" in d["assumption"]

    def test_consistent_signal_dict_present(self):
        scorer = CredibilityScorer(location_mismatch_enabled=True)
        bd = scorer.score_incident(_make_inputs(
            report_text="Flooding in Mumbai",
            declared_state="Maharashtra",
        ))
        assert bd.location_mismatch_signal is not None
        assert bd.location_mismatch_signal["verdict"] == "CONSISTENT"

    def test_neutral_signal_dict_present(self):
        scorer = CredibilityScorer(location_mismatch_enabled=True)
        bd = scorer.score_incident(_make_inputs(
            report_text=None,
            declared_state="Maharashtra",
        ))
        assert bd.location_mismatch_signal is not None
        assert bd.location_mismatch_signal["verdict"] == "NEUTRAL"

    def test_flag_off_signal_dict_none(self):
        scorer = CredibilityScorer(location_mismatch_enabled=False)
        bd = scorer.score_incident(_make_inputs(
            report_text="Flooding in Kathmandu",
            declared_state="Maharashtra",
        ))
        assert bd.location_mismatch_signal is None


class TestBackwardCompatibility:
    """All existing callers without new fields must be unaffected."""

    def test_no_new_fields_unchanged_score(self):
        scorer_default = CredibilityScorer()  # flag=False by default from settings
        bd = scorer_default.score_incident(_make_inputs())
        assert bd.final_credibility_score == pytest.approx(0.60, abs=0.001)
        assert bd.location_mismatch_adjustment == 0.0

    def test_singleton_scorer_unchanged(self):
        from app.intelligence.credibility_scorer import credibility_scorer
        bd = credibility_scorer.score_incident(_make_inputs())
        # Flag is OFF by default; no change expected
        assert bd.location_mismatch_adjustment == 0.0
        assert bd.final_credibility_score == pytest.approx(0.60, abs=0.001)

    def test_weak_link_path_still_works(self):
        """score_incident with weak evidence groups still passes through."""
        from app.intelligence.schemas import DigitalEvidenceGroupInput
        scorer = CredibilityScorer(location_mismatch_enabled=True)
        bd = scorer.score_incident(_make_inputs(
            report_text="Flooding in Chennai",
            declared_state="Tamil Nadu",
            evidence_groups=[
                DigitalEvidenceGroupInput(
                    provenance_key="domain_thehindu.com",
                    max_confidence=0.80,
                    role_weight=0.35,  # weak -> RELATED
                    article_count=1,
                    source_family=SourceFamily.NEWS,
                )
            ],
        ))
        assert bd.final_credibility_score > 0.0
        assert bd.location_mismatch_adjustment == 0.0  # consistent -> no adj


class TestScoreImpactHoax:
    """Item 4 verification: K1 hoax posts now score lower with signal ON."""

    def test_hoax_foreign_scores_lower_than_baseline(self):
        scorer_on = CredibilityScorer(location_mismatch_enabled=True)
        scorer_off = CredibilityScorer(location_mismatch_enabled=False)

        hoax_inputs = _make_inputs(
            report_text="Flood emergency in Kathmandu valley",
            declared_state="Maharashtra",
        )
        bd_on = scorer_on.score_incident(hoax_inputs)
        bd_off = scorer_off.score_incident(hoax_inputs)

        assert bd_on.final_credibility_score < bd_off.final_credibility_score
        assert bd_on.final_credibility_score < 0.55  # should be 0.50 (0.60 - 0.10)
        assert bd_on.final_credibility_score >= 0.0

    def test_genuine_same_state_unchanged(self):
        scorer_on = CredibilityScorer(location_mismatch_enabled=True)
        scorer_off = CredibilityScorer(location_mismatch_enabled=False)

        genuine_inputs = _make_inputs(
            report_text="Flooding hits Mumbai suburbs hard",
            declared_state="Maharashtra",
        )
        bd_on = scorer_on.score_incident(genuine_inputs)
        bd_off = scorer_off.score_incident(genuine_inputs)

        assert bd_on.final_credibility_score == bd_off.final_credibility_score
        assert bd_on.location_mismatch_adjustment == 0.0
