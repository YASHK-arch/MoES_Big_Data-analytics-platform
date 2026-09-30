"""Comprehensive test suite for the High-Assurance Incident Credibility Engine.

Validates:
1. Exact mathematical scoring against canonical worked examples A–O.
2. 60-Case Synthetic Benchmark (100% accuracy and ordering invariants).
3. Monotonicity and boundary guarantees.
4. Provenance hierarchy and syndication diminishing returns.
5. Physical station deduplication and trend integration.
6. Multi-source diversity accounting and cross-quoting defense.
7. Diagnostic contradiction penalties and missing-data neutrality.
8. Decoupled human verification authority.
9. Resilient failure fallback semantics.
10. Targeted incremental recomputation.
"""

import math
import uuid
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from sqlalchemy import pool, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.intelligence.credibility_engine import (
    credibility_engine,
)
from app.intelligence.credibility_evaluation_dataset import (
    run_synthetic_benchmark,
)
from app.intelligence.credibility_explanation_builder import (
    credibility_explanation_builder,
)
from app.intelligence.credibility_scorer import (
    credibility_scorer,
)
from app.intelligence.schemas import (
    ContradictionInput,
    DigitalEvidenceGroupInput,
    IncidentCredibilityInputs,
    ObservationRelationship,
    PhysicalStationInput,
    SourceFamily,
)
from app.models.corroboration import IncidentObservationCorroboration
from app.models.duplicate import DuplicateCluster
from app.models.evidence import EvidenceItem, IncidentEvidenceLink
from app.models.observation import WeatherObservation
from app.models.report import WeatherReport
from app.models.source import Source


@pytest_asyncio.fixture
async def db_session():
    """Create an isolated async database session per test with NullPool."""
    test_engine = create_async_engine(
        settings.DATABASE_URL,
        poolclass=pool.NullPool,
    )
    session_factory = async_sessionmaker(
        bind=test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    async with session_factory() as session:
        yield session

    await test_engine.dispose()


# =============================================================================
# 1. CANONICAL WORKED EXAMPLES (SCENARIOS A–O)
# =============================================================================


def test_scenario_a_citizen_only() -> None:
    """Scenario A: Isolated citizen report with complete metadata."""
    inputs = IncidentCredibilityInputs(
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
    sig = credibility_scorer.score_incident(inputs)
    assert sig.incident_baseline == 0.6000
    assert sig.synthesized_support == 0.0000
    assert sig.support_delta == 0.0000
    assert sig.applied_cap == 0.6500
    assert sig.final_credibility_score == 0.6000


def test_scenario_b_official_only() -> None:
    """Scenario B: Isolated official IMD AWS alert."""
    inputs = IncidentCredibilityInputs(
        incident_id=uuid.uuid4(),
        source_code="IMD_AWS",
        source_type="IMD",
        source_base_trust=0.90,
        origin_family=SourceFamily.OFFICIAL,
        has_coordinates=True,
        has_timestamp=True,
        has_location_name=True,
        has_description=True,
        has_category=True,
    )
    sig = credibility_scorer.score_incident(inputs)
    assert sig.incident_baseline == 0.9000
    assert sig.synthesized_support == 0.0000
    assert sig.applied_cap == 0.8800
    assert sig.final_credibility_score == 0.8800


def test_scenario_c_citizen_plus_official() -> None:
    """Scenario C: Citizen report linked to supporting official alert."""
    inputs = IncidentCredibilityInputs(
        incident_id=uuid.uuid4(),
        source_code="CITIZEN_WEB",
        source_type="CITIZEN_REPORT",
        source_base_trust=0.60,
        origin_family=SourceFamily.CITIZEN,
        evidence_groups=[
            DigitalEvidenceGroupInput(
                provenance_key="official_imd_alert",
                max_confidence=0.90,
                role_weight=1.0,
                article_count=1,
                source_family=SourceFamily.OFFICIAL,
            )
        ],
    )
    sig = credibility_scorer.score_incident(inputs)
    assert sig.incident_baseline == 0.6000
    assert sig.digital_evidence_score == 0.4500
    assert sig.synthesized_support == 0.2250
    assert sig.diversity_multiplier == 1.0600
    assert sig.support_delta == 0.0954
    assert sig.positive_score == 0.6954
    assert sig.final_credibility_score == 0.6954


def test_scenario_d_citizen_plus_5_duplicates() -> None:
    """Scenario D: Citizen report backed by 5 duplicate reports in cluster."""
    inputs = IncidentCredibilityInputs(
        incident_id=uuid.uuid4(),
        source_code="CITIZEN_WEB",
        source_type="CITIZEN_REPORT",
        source_base_trust=0.60,
        origin_family=SourceFamily.CITIZEN,
        cluster_member_count=5,
    )
    sig = credibility_scorer.score_incident(inputs)
    assert sig.incident_baseline == 0.6000
    assert sig.crowd_cluster_score == 0.7364
    assert sig.synthesized_support == 0.2209
    assert sig.diversity_multiplier == 1.0000
    assert sig.support_delta == 0.0884
    assert sig.positive_score == 0.6884
    assert sig.applied_cap == 0.8200
    assert sig.final_credibility_score == 0.6884


def test_scenario_e_citizen_plus_20_syndicated_articles() -> None:
    """Scenario E: Citizen report backed by 20 syndicated articles from 1 domain."""
    inputs = IncidentCredibilityInputs(
        incident_id=uuid.uuid4(),
        source_code="CITIZEN_WEB",
        source_type="CITIZEN_REPORT",
        source_base_trust=0.60,
        origin_family=SourceFamily.CITIZEN,
        evidence_groups=[
            DigitalEvidenceGroupInput(
                provenance_key="domain_timesofindia.com",
                max_confidence=0.80,
                role_weight=1.0,
                article_count=20,
                source_family=SourceFamily.NEWS,
            )
        ],
    )
    sig = credibility_scorer.score_incident(inputs)
    assert sig.incident_baseline == 0.6000
    assert sig.digital_evidence_score == 0.5000
    assert sig.synthesized_support == 0.2500
    assert sig.diversity_multiplier == 1.0600
    assert sig.support_delta == 0.1060
    assert sig.positive_score == 0.7060
    assert sig.final_credibility_score == 0.7060


def test_scenario_f_citizen_plus_2_independent_news() -> None:
    """Scenario F: Citizen report backed by 2 independent news publisher domains."""
    inputs = IncidentCredibilityInputs(
        incident_id=uuid.uuid4(),
        source_code="CITIZEN_WEB",
        source_type="CITIZEN_REPORT",
        source_base_trust=0.60,
        origin_family=SourceFamily.CITIZEN,
        evidence_groups=[
            DigitalEvidenceGroupInput(
                provenance_key="domain_thehindu.com",
                max_confidence=0.80,
                role_weight=1.0,
                article_count=1,
                source_family=SourceFamily.NEWS,
            ),
            DigitalEvidenceGroupInput(
                provenance_key="domain_ndtv.com",
                max_confidence=0.80,
                role_weight=1.0,
                article_count=1,
                source_family=SourceFamily.NEWS,
            ),
        ],
    )
    sig = credibility_scorer.score_incident(inputs)
    assert sig.incident_baseline == 0.6000
    assert sig.digital_evidence_score == 0.6400
    assert sig.synthesized_support == 0.3200
    assert sig.diversity_multiplier == 1.0600
    assert sig.support_delta == 0.1357
    assert sig.positive_score == 0.7357
    assert sig.final_credibility_score == 0.7357


def test_scenario_g_citizen_plus_cwc_single_reading() -> None:
    """Scenario G: Citizen report corroborated by single CWC gauge reading."""
    inputs = IncidentCredibilityInputs(
        incident_id=uuid.uuid4(),
        source_code="CITIZEN_WEB",
        source_type="CITIZEN_REPORT",
        source_base_trust=0.60,
        origin_family=SourceFamily.CITIZEN,
        observation_stations=[
            PhysicalStationInput(
                station_key="cwc_bhad_01",
                corroboration_score=0.60,
                relationship_weight=1.0,
                source_family=SourceFamily.SENSOR,
                points_count=1,
            )
        ],
    )
    sig = credibility_scorer.score_incident(inputs)
    assert sig.incident_baseline == 0.6000
    assert sig.physical_observation_score == 0.3600
    assert sig.synthesized_support == 0.1800
    assert sig.diversity_multiplier == 1.0600
    assert sig.support_delta == 0.0763
    assert sig.positive_score == 0.6763
    assert sig.final_credibility_score == 0.6763


def test_scenario_g2_citizen_plus_cwc_24_pt_trend() -> None:
    """Scenario G2: Citizen report corroborated by CWC 24-point rising trend."""
    inputs = IncidentCredibilityInputs(
        incident_id=uuid.uuid4(),
        source_code="CITIZEN_WEB",
        source_type="CITIZEN_REPORT",
        source_base_trust=0.60,
        origin_family=SourceFamily.CITIZEN,
        observation_stations=[
            PhysicalStationInput(
                station_key="cwc_bhad_01",
                corroboration_score=0.85,
                relationship_weight=1.0,
                source_family=SourceFamily.SENSOR,
                points_count=24,
            )
        ],
    )
    sig = credibility_scorer.score_incident(inputs)
    assert sig.incident_baseline == 0.6000
    assert sig.physical_observation_score == 0.5100
    assert sig.synthesized_support == 0.2550
    assert sig.diversity_multiplier == 1.0600
    assert sig.support_delta == 0.1081
    assert sig.positive_score == 0.7081
    assert sig.final_credibility_score == 0.7081


def test_scenario_h_citizen_plus_cwc_plus_2_news() -> None:
    """Scenario H: Citizen report backed by CWC telemetry and 2 independent news domains."""
    inputs = IncidentCredibilityInputs(
        incident_id=uuid.uuid4(),
        source_code="CITIZEN_WEB",
        source_type="CITIZEN_REPORT",
        source_base_trust=0.60,
        origin_family=SourceFamily.CITIZEN,
        observation_stations=[
            PhysicalStationInput(
                station_key="cwc_bhad_01",
                corroboration_score=0.85,
                relationship_weight=1.0,
                source_family=SourceFamily.SENSOR,
                points_count=24,
            )
        ],
        evidence_groups=[
            DigitalEvidenceGroupInput(
                provenance_key="domain_thehindu.com",
                max_confidence=0.80,
                role_weight=1.0,
                article_count=1,
                source_family=SourceFamily.NEWS,
            ),
            DigitalEvidenceGroupInput(
                provenance_key="domain_ndtv.com",
                max_confidence=0.80,
                role_weight=1.0,
                article_count=1,
                source_family=SourceFamily.NEWS,
            ),
        ],
    )
    sig = credibility_scorer.score_incident(inputs)
    assert sig.incident_baseline == 0.6000
    assert sig.physical_observation_score == 0.5100
    assert sig.digital_evidence_score == 0.6400
    assert sig.synthesized_support == 0.5750
    assert sig.diversity_multiplier == 1.1200
    assert sig.support_delta == 0.2576
    assert sig.positive_score == 0.8576
    assert sig.final_credibility_score == 0.8576


def test_scenario_j_cwc_plus_imd_aws() -> None:
    """Scenario J: Citizen report corroborated by CWC gauge and IMD AWS (2 physical families)."""
    inputs = IncidentCredibilityInputs(
        incident_id=uuid.uuid4(),
        source_code="CITIZEN_WEB",
        source_type="CITIZEN_REPORT",
        source_base_trust=0.60,
        origin_family=SourceFamily.CITIZEN,
        observation_stations=[
            PhysicalStationInput(
                station_key="cwc_bhad_01",
                corroboration_score=0.85,
                relationship_weight=1.0,
                source_family=SourceFamily.SENSOR,
                points_count=24,
            ),
            PhysicalStationInput(
                station_key="imd_aws_station_01",
                corroboration_score=0.80,
                relationship_weight=1.0,
                source_family=SourceFamily.OFFICIAL,
                points_count=24,
            ),
        ],
    )
    sig = credibility_scorer.score_incident(inputs)
    assert sig.incident_baseline == 0.6000
    assert sig.physical_observation_score == 0.7452
    assert sig.synthesized_support == 0.3726
    assert sig.diversity_multiplier == 1.1200
    assert sig.support_delta == 0.1669
    assert sig.positive_score == 0.7669
    assert sig.final_credibility_score == 0.7669


def test_scenario_k_missing_coordinates() -> None:
    """Scenario K: Missing coordinates slightly reduces quality without negative penalty."""
    inputs = IncidentCredibilityInputs(
        incident_id=uuid.uuid4(),
        source_code="CITIZEN_WEB",
        source_type="CITIZEN_REPORT",
        source_base_trust=0.60,
        origin_family=SourceFamily.CITIZEN,
        has_coordinates=False,
        has_timestamp=True,
        has_location_name=True,
        has_description=True,
        has_category=True,
    )
    sig = credibility_scorer.score_incident(inputs)
    assert sig.report_quality_score == 0.7000
    assert sig.incident_baseline == 0.5460
    assert sig.negative_penalty == 0.0000
    assert sig.final_credibility_score == 0.5460


def test_scenario_m_diagnostic_physical_contradiction() -> None:
    """Scenario M: Diagnostic physical gauge contradiction drops credibility substantially."""
    inputs = IncidentCredibilityInputs(
        incident_id=uuid.uuid4(),
        source_code="CITIZEN_WEB",
        source_type="CITIZEN_REPORT",
        source_base_trust=0.60,
        origin_family=SourceFamily.CITIZEN,
        negative_contradictions=[
            ContradictionInput(
                signal_source_key="cwc_gauge_contradiction",
                contradiction_score=0.90,
                is_diagnostic=True,
                is_physical_sensor=True,
            )
        ],
    )
    sig = credibility_scorer.score_incident(inputs)
    assert sig.incident_baseline == 0.6000
    assert sig.negative_penalty == 0.2700
    assert sig.penalized_score == 0.3300
    assert sig.final_credibility_score == 0.3300


# =============================================================================
# 2. FULL 60-CASE SYNTHETIC BENCHMARK EXECUTION
# =============================================================================


def test_60_case_synthetic_benchmark_suite() -> None:
    """Run full 60-case benchmark and verify 100% pass rate and ordering invariants."""
    benchmark_report = run_synthetic_benchmark()
    assert benchmark_report["benchmark_label"] == "Synthetic Credibility Benchmark Only"
    assert benchmark_report["total_cases"] == 60
    assert benchmark_report["passed_cases"] == 60
    assert benchmark_report["pass_rate_pct"] == 100.00
    assert benchmark_report["monotonicity_ordering_passed"] is True


# =============================================================================
# 3. MONOTONICITY & INVARIANT PROPERTIES
# =============================================================================


def test_monotonicity_ordering_invariants() -> None:
    """Verify strictly expected relational ordering across core scenarios."""
    base_citizen = IncidentCredibilityInputs(
        incident_id=uuid.uuid4(),
        source_code="CITIZEN_WEB",
        source_type="CITIZEN_REPORT",
        source_base_trust=0.60,
        origin_family=SourceFamily.CITIZEN,
    )
    score_base = credibility_scorer.score_incident(base_citizen).final_credibility_score

    # 1. Duplicate crowd cluster improves score
    with_cluster = base_citizen.model_copy(update={"cluster_member_count": 5})
    score_cluster = credibility_scorer.score_incident(with_cluster).final_credibility_score

    # 2. CWC single gauge improves score
    with_cwc_1 = base_citizen.model_copy(
        update={
            "observation_stations": [
                PhysicalStationInput(
                    station_key="cwc_1",
                    corroboration_score=0.60,
                    relationship_weight=1.0,
                    source_family=SourceFamily.SENSOR,
                )
            ]
        }
    )
    score_cwc_1 = credibility_scorer.score_incident(with_cwc_1).final_credibility_score

    # 3. CWC 24-pt trend improves score further
    with_cwc_trend = base_citizen.model_copy(
        update={
            "observation_stations": [
                PhysicalStationInput(
                    station_key="cwc_1",
                    corroboration_score=0.85,
                    relationship_weight=1.0,
                    source_family=SourceFamily.SENSOR,
                    points_count=24,
                )
            ]
        }
    )
    score_cwc_trend = credibility_scorer.score_incident(with_cwc_trend).final_credibility_score

    # 4. 2 Independent news domains improves score further
    with_2_news = base_citizen.model_copy(
        update={
            "evidence_groups": [
                DigitalEvidenceGroupInput(
                    provenance_key="domain_thehindu.com",
                    max_confidence=0.80,
                    role_weight=1.0,
                    article_count=1,
                    source_family=SourceFamily.NEWS,
                ),
                DigitalEvidenceGroupInput(
                    provenance_key="domain_ndtv.com",
                    max_confidence=0.80,
                    role_weight=1.0,
                    article_count=1,
                    source_family=SourceFamily.NEWS,
                ),
            ]
        }
    )
    score_2_news = credibility_scorer.score_incident(with_2_news).final_credibility_score

    # 5. Full multi-source (Citizen + CWC + 2 News) reaches high tier
    with_multi = base_citizen.model_copy(
        update={
            "observation_stations": with_cwc_trend.observation_stations,
            "evidence_groups": with_2_news.evidence_groups,
        }
    )
    score_multi = credibility_scorer.score_incident(with_multi).final_credibility_score

    # Assert strict ordering
    assert score_base < score_cluster
    assert score_cwc_1 < score_cwc_trend
    assert score_cwc_trend < score_2_news
    assert score_2_news < score_multi
    assert score_multi <= 0.9800


def test_syndication_diminishing_returns_invariant() -> None:
    """Verify 20 syndicated copies from 1 domain cannot beat 2 independent domains."""
    base_citizen = IncidentCredibilityInputs(
        incident_id=uuid.uuid4(),
        source_code="CITIZEN_WEB",
        source_type="CITIZEN_REPORT",
        source_base_trust=0.60,
        origin_family=SourceFamily.CITIZEN,
    )

    syndicated_20 = base_citizen.model_copy(
        update={
            "evidence_groups": [
                DigitalEvidenceGroupInput(
                    provenance_key="domain_timesofindia.com",
                    max_confidence=0.80,
                    role_weight=1.0,
                    article_count=20,
                    source_family=SourceFamily.NEWS,
                )
            ]
        }
    )
    score_syndicated = credibility_scorer.score_incident(syndicated_20).final_credibility_score

    independent_2 = base_citizen.model_copy(
        update={
            "evidence_groups": [
                DigitalEvidenceGroupInput(
                    provenance_key="domain_thehindu.com",
                    max_confidence=0.80,
                    role_weight=1.0,
                    article_count=1,
                    source_family=SourceFamily.NEWS,
                ),
                DigitalEvidenceGroupInput(
                    provenance_key="domain_ndtv.com",
                    max_confidence=0.80,
                    role_weight=1.0,
                    article_count=1,
                    source_family=SourceFamily.NEWS,
                ),
            ]
        }
    )
    score_independent = credibility_scorer.score_incident(independent_2).final_credibility_score

    assert score_syndicated < score_independent


# =============================================================================
# 4. EXPLANATION BUILDER & AUDIT TRAIL
# =============================================================================


def test_credibility_explanation_builder() -> None:
    """Verify structured assessment envelope contains explainable audit trail."""
    incident_id = uuid.uuid4()
    inputs = IncidentCredibilityInputs(
        incident_id=incident_id,
        source_code="CITIZEN_WEB",
        source_type="CITIZEN_REPORT",
        source_base_trust=0.60,
        origin_family=SourceFamily.CITIZEN,
        cluster_member_count=5,
        observation_stations=[
            PhysicalStationInput(
                station_key="cwc_bhad_01",
                corroboration_score=0.85,
                relationship_weight=1.0,
                source_family=SourceFamily.SENSOR,
                points_count=24,
            )
        ],
    )
    signals = credibility_scorer.score_incident(inputs)
    assessment = credibility_explanation_builder.build_assessment(
        incident_id=incident_id,
        inputs=inputs,
        signals=signals,
    )

    assert assessment.incident_id == incident_id
    assert assessment.credibility_score == signals.final_credibility_score
    assert assessment.provenance.independent_family_count == 2
    assert SourceFamily.CITIZEN in assessment.provenance.participating_families
    assert SourceFamily.SENSOR in assessment.provenance.participating_families
    assert len(assessment.positive_drivers) >= 2
    assert "Machine Credibility Score" in assessment.explanation


def test_crowd_volume_signal_explanation_and_diminishing_returns() -> None:
    """Verify crowd signal wording and non-linear diminishing returns for k in [1, 2, 5, 18]."""
    # 1. Test mathematical diminishing returns: s_crowd = 1 - exp(-(k-1)/3)
    k_values = [1, 2, 5, 18]
    scores = {}
    for k in k_values:
        inputs = IncidentCredibilityInputs(
            incident_id=uuid.uuid4(),
            source_code="CITIZEN_APP",
            source_type="CITIZEN_REPORT",
            source_base_trust=0.60,
            origin_family=SourceFamily.CITIZEN,
            cluster_member_count=k,
        )
        signals = credibility_scorer.score_incident(inputs)
        scores[k] = signals.crowd_cluster_score

    assert scores[1] == 0.0
    assert abs(scores[2] - (1.0 - math.exp(-1.0 / 3.0))) < 1e-4  # ~0.2835
    assert abs(scores[5] - (1.0 - math.exp(-4.0 / 3.0))) < 1e-4  # ~0.7364
    assert abs(scores[18] - (1.0 - math.exp(-17.0 / 3.0))) < 1e-4  # ~0.9965
    assert scores[1] < scores[2] < scores[5] < scores[18] <= 1.0

    # 2. Test explanation builder wording:
    test_id = uuid.uuid4()
    inputs_18 = IncidentCredibilityInputs(
        incident_id=test_id,
        source_code="CITIZEN_APP",
        source_type="CITIZEN_REPORT",
        source_base_trust=0.60,
        origin_family=SourceFamily.CITIZEN,
        cluster_member_count=18,
    )
    signals_18 = credibility_scorer.score_incident(inputs_18)
    assessment = credibility_explanation_builder.build_assessment(
        incident_id=test_id,
        inputs=inputs_18,
        signals=signals_18,
    )

    crowd_drivers = [d for d in assessment.positive_drivers if "Crowd" in d]
    assert len(crowd_drivers) == 1
    assert (
        "Crowd volume signal from 18 duplicate incident reports (sub-signal: 1.00)."
        in crowd_drivers[0]
    )
    assert "Crowd corroboration" not in crowd_drivers[0]
    assert "score: 1.00" not in crowd_drivers[0]


# =============================================================================
# 5. INTEGRATION TESTS (DATABASE FIXTURES)
# =============================================================================


@pytest.mark.asyncio
async def test_end_to_end_credibility_evaluation(db_session: AsyncSession) -> None:
    """Test full database evaluation and persistence into WeatherReport."""
    uid_hex = uuid.uuid4().hex[:8]
    # 1. Create Source
    source = Source(
        source_code=f"CITIZEN_TEST_{uid_hex}",
        name="Citizen Test Portal",
        source_type="CITIZEN_REPORT",
        base_trust_score=0.60,
        is_active=True,
    )
    db_session.add(source)
    await db_session.flush()

    # 2. Create WeatherReport
    report = WeatherReport(
        tracking_id=f"RPT-CRED-{uid_hex}",
        source_id=source.id,
        title="Severe Flood Inundation",
        description="Water level entering residential homes near river bridge.",
        location_name="Bhadra Nagar, Shimoga",
        reported_category="FLOOD",
        latitude=13.9299,
        longitude=75.5681,
        occurred_at=datetime.now(timezone.utc),
        geom="SRID=4326;POINT(75.5681 13.9299)",
        processing_status="COMPLETED",
        verification_status="PENDING",
        credibility_score=0.0,
    )
    db_session.add(report)
    await db_session.flush()

    # 3. Create DuplicateCluster with 4 members
    cluster = DuplicateCluster(
        primary_report_id=report.id,
        centroid_geom=report.geom,
        member_count=4,
    )
    db_session.add(cluster)
    await db_session.flush()

    # 4. Create EvidenceItem & IncidentEvidenceLink
    evidence = EvidenceItem(
        source_id=source.id,
        external_id=f"news_flood_{uid_hex}",
        evidence_type="NEWS_ARTICLE",
        title="Shimoga Floods: Water level rises above danger mark",
        publisher_domain="thehindu.com",
        published_at=datetime.now(timezone.utc),
    )
    db_session.add(evidence)
    await db_session.flush()

    link = IncidentEvidenceLink(
        report_id=report.id,
        evidence_id=evidence.id,
        link_role="SUPPORTING",
        confidence_score=0.85,
    )
    db_session.add(link)
    await db_session.flush()

    # 5. Create WeatherObservation & IncidentObservationCorroboration
    obs_source = Source(
        source_code=f"CWC_HYDRO_{uid_hex}",
        name="CWC Hydrological Service",
        source_type="PHYSICAL_SENSOR",
        base_trust_score=0.92,
        is_active=True,
    )
    db_session.add(obs_source)
    await db_session.flush()

    observation = WeatherObservation(
        source_id=obs_source.id,
        external_id=f"cwc_reading_{uid_hex}",
        station_code="BHAD_01",
        station_name="Bhadra Dam Gauge",
        water_level_m=642.5,
        observed_at=datetime.now(timezone.utc),
        geom="SRID=4326;POINT(75.5681 13.9299)",
    )
    db_session.add(observation)
    await db_session.flush()

    corroboration = IncidentObservationCorroboration(
        report_id=report.id,
        observation_id=observation.id,
        corroboration_score=0.85,
        corroboration_assessment={
            "relationship_type": ObservationRelationship.CORROBORATING.value,
            "trend": {"points_count": 24, "direction": "RISING"},
        },
    )
    db_session.add(corroboration)
    await db_session.commit()

    # 6. Execute CredibilityEngine
    result = await credibility_engine.evaluate_incident_credibility(
        db=db_session,
        incident_id=report.id,
    )
    assert result is not None
    assert result.is_persisted is True
    assert result.credibility_score > 0.8000
    assert result.assessment.provenance.independent_family_count == 3

    # 7. Check persistence in WeatherReport
    stmt = select(WeatherReport).where(WeatherReport.id == report.id)
    res = await db_session.execute(stmt)
    refreshed = res.scalar_one()

    assert refreshed.credibility_score == result.credibility_score
    assert refreshed.credibility_explanation is not None
    assert refreshed.credibility_explanation["credibility_score"] == result.credibility_score

    # 8. Human Verification Decoupling check
    refreshed.verification_status = "VERIFIED"
    await db_session.commit()

    # Recomputing credibility does not overwrite human VERIFIED status
    recomputed = await credibility_engine.evaluate_incident_credibility(
        db=db_session,
        incident_id=report.id,
    )
    assert recomputed is not None
    assert refreshed.verification_status == "VERIFIED"
    assert refreshed.credibility_score == recomputed.credibility_score


@pytest.mark.asyncio
async def test_targeted_recomputations(db_session: AsyncSession) -> None:
    """Test targeted recomputation hooks on evidence link and observation change."""
    uid_hex = uuid.uuid4().hex[:8]
    source = Source(
        source_code=f"CITIZEN_RECOMP_{uid_hex}",
        name="Citizen Recompute Portal",
        source_type="CITIZEN_REPORT",
        base_trust_score=0.60,
        is_active=True,
    )
    db_session.add(source)
    await db_session.flush()

    report = WeatherReport(
        tracking_id=f"RPT-RECOMP-{uid_hex}",
        source_id=source.id,
        title="Moderate Rainfall Alert",
        description="Continuous rainfall for the past 3 hours in urban area.",
        location_name="MG Road, Bangalore",
        reported_category="HEAVY_RAINFALL",
        latitude=12.9716,
        longitude=77.5946,
        occurred_at=datetime.now(timezone.utc),
        geom="SRID=4326;POINT(77.5946 12.9716)",
        processing_status="COMPLETED",
        verification_status="PENDING",
        credibility_score=0.0,
    )
    db_session.add(report)
    await db_session.commit()

    # Initial baseline
    init_res = await credibility_engine.evaluate_incident_credibility(
        db=db_session,
        incident_id=report.id,
    )
    assert init_res is not None
    assert init_res.credibility_score == 0.6000

    # Add evidence link
    evidence = EvidenceItem(
        source_id=source.id,
        external_id=f"news_recomp_{uid_hex}",
        evidence_type="NEWS_ARTICLE",
        title="Rainfall Alert Confirmed",
        publisher_domain="deccanherald.com",
        published_at=datetime.now(timezone.utc),
    )
    db_session.add(evidence)
    await db_session.flush()

    link = IncidentEvidenceLink(
        report_id=report.id,
        evidence_id=evidence.id,
        link_role="SUPPORTING",
        confidence_score=0.80,
    )
    db_session.add(link)
    await db_session.commit()

    # Trigger targeted recomputation via link_id
    recomp_res = await credibility_engine.recompute_for_evidence_link(
        db=db_session,
        link_id=link.id,
    )
    assert recomp_res is not None
    assert recomp_res.credibility_score > 0.6000


@pytest.mark.asyncio
async def test_provenance_hierarchy_resolution_order(db_session: AsyncSession) -> None:
    """Verify strict provenance hierarchy (Hash > Canonical > Wire > Domain > ID)."""
    from app.intelligence.credibility_collector import credibility_collector

    uid_hex = uuid.uuid4().hex[:8]
    source = Source(
        source_code=f"SRC_PROV_{uid_hex}",
        name="Provenance Test Source",
        source_type="CITIZEN_REPORT",
        base_trust_score=0.60,
        is_active=True,
    )
    db_session.add(source)
    await db_session.flush()

    report = WeatherReport(
        tracking_id=f"RPT-PROV-{uid_hex}",
        source_id=source.id,
        title="Cyclone Gale Warning",
        description="High velocity wind gale damaging structures.",
        location_name="Puri, Odisha",
        reported_category="CYCLONE",
        latitude=19.8135,
        longitude=85.8312,
        occurred_at=datetime.now(timezone.utc),
        geom="SRID=4326;POINT(85.8312 19.8135)",
        processing_status="COMPLETED",
        verification_status="PENDING",
        credibility_score=0.0,
    )
    db_session.add(report)
    await db_session.flush()

    # 1. Two items with SAME SHA256 but DIFFERENT publisher domains
    evi1 = EvidenceItem(
        source_id=source.id,
        external_id=f"hash_evi1_{uid_hex}",
        evidence_type="NEWS_ARTICLE",
        title="Cyclone Storm Alert",
        publisher_domain="domain-a.com",
        sha256_hash="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        raw_payload={"canonical_url": "https://domain-a.com/story-1"},
    )
    evi2 = EvidenceItem(
        source_id=source.id,
        external_id=f"hash_evi2_{uid_hex}",
        evidence_type="NEWS_ARTICLE",
        title="Cyclone Storm Alert (Republished)",
        publisher_domain="domain-b.com",
        sha256_hash="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        raw_payload={"canonical_url": "https://domain-b.com/story-repub"},
    )
    db_session.add_all([evi1, evi2])
    await db_session.flush()

    link1 = IncidentEvidenceLink(
        report_id=report.id,
        evidence_id=evi1.id,
        link_role="SUPPORTING",
        confidence_score=0.80,
    )
    link2 = IncidentEvidenceLink(
        report_id=report.id,
        evidence_id=evi2.id,
        link_role="SUPPORTING",
        confidence_score=0.80,
    )
    db_session.add_all([link1, link2])
    await db_session.commit()

    inputs = await credibility_collector.collect_inputs(db=db_session, incident_id=report.id)
    assert inputs is not None
    # Identical hash MUST collapse both articles under 1 provenance group (hash_...)
    assert len(inputs.evidence_groups) == 1
    assert inputs.evidence_groups[0].provenance_key.startswith("hash_")
    assert inputs.evidence_groups[0].article_count == 2

    # 2. Canonical URL hierarchy check (No hash, but same canonical URL)
    evi3 = EvidenceItem(
        source_id=source.id,
        external_id=f"canon_evi3_{uid_hex}",
        evidence_type="NEWS_ARTICLE",
        title="Cyclone Warning Update",
        publisher_domain="mirror-site.com",
        raw_payload={"canonical_url": "https://original-site.com/cyclone-report"},
    )
    db_session.add(evi3)
    await db_session.flush()

    link3 = IncidentEvidenceLink(
        report_id=report.id,
        evidence_id=evi3.id,
        link_role="SUPPORTING",
        confidence_score=0.80,
    )
    db_session.add(link3)
    await db_session.commit()

    inputs2 = await credibility_collector.collect_inputs(db=db_session, incident_id=report.id)
    assert inputs2 is not None
    # Now there should be 2 groups: the hash_ group and the canon_ group
    assert len(inputs2.evidence_groups) == 2
    keys = {g.provenance_key for g in inputs2.evidence_groups}
    assert any(k.startswith("hash_") for k in keys)
    assert any(k.startswith("canon_https://original-site.com/cyclone-report") for k in keys)


@pytest.mark.asyncio
async def test_failure_transaction_safety_and_rollback(db_session: AsyncSession) -> None:
    """Verify failure during scoring triggers rollback and safely records stale fallback."""
    from unittest.mock import patch

    uid_hex = uuid.uuid4().hex[:8]
    source = Source(
        source_code=f"SRC_FAIL_{uid_hex}",
        name="Failure Test Source",
        source_type="CITIZEN_REPORT",
        base_trust_score=0.60,
        is_active=True,
    )
    db_session.add(source)
    await db_session.flush()

    report = WeatherReport(
        tracking_id=f"RPT-FAIL-{uid_hex}",
        source_id=source.id,
        title="Initial Valid Incident",
        description="Initial report description for testing fallback preservation.",
        location_name="Shimoga, Karnataka",
        reported_category="FLOOD",
        latitude=13.9299,
        longitude=75.5681,
        occurred_at=datetime.now(timezone.utc),
        geom="SRID=4326;POINT(75.5681 13.9299)",
        processing_status="COMPLETED",
        verification_status="PENDING",
        credibility_score=0.6000,
        credibility_explanation={"credibility_score": 0.6000, "is_stale": False},
    )
    db_session.add(report)
    await db_session.commit()

    # Simulate exception in scorer during evaluation
    with patch(
        "app.intelligence.credibility_scorer.CredibilityScorer.score_incident",
        side_effect=RuntimeError("Simulated computational failure during scoring"),
    ):
        result = await credibility_engine.evaluate_incident_credibility(
            db=db_session,
            incident_id=report.id,
        )
        assert result is None

    # Verify report in DB has preserved score, not zero, and is marked stale
    stmt = select(WeatherReport).where(WeatherReport.id == report.id)
    res = await db_session.execute(stmt)
    refreshed = res.scalar_one()

    assert refreshed.credibility_score == 0.6000  # NEVER set to 0.0 or None
    assert refreshed.credibility_explanation is not None
    assert refreshed.credibility_explanation.get("is_stale") is True
    assert refreshed.credibility_explanation.get("is_failure_fallback") is True
    last_err = refreshed.credibility_explanation.get("last_error", "")
    assert "Simulated computational failure" in last_err


def test_weak_link_contribution_cap_and_threshold_barrier():
    """Verify RELATED/weak links cannot increase score by > 0.03 and cannot cross thresholds."""
    # 1. Base input without evidence
    base_input = IncidentCredibilityInputs(
        incident_id=uuid.uuid4(),
        source_code="CITIZEN_WEB",
        source_type="CITIZEN",
        source_base_trust=0.60,
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
    sig_base = credibility_scorer.score_incident(base_input)
    base_score = sig_base.final_credibility_score

    # 2. Add 10 weak (RELATED, role_weight=0.35) groups across multiple domains
    weak_groups = [
        DigitalEvidenceGroupInput(
            provenance_key=f"domain_news_{i}.com",
            max_confidence=0.95,
            role_weight=0.35,  # RELATED
            article_count=5,
            source_family=SourceFamily.NEWS,
        )
        for i in range(10)
    ]
    weak_input = base_input.model_copy(update={"evidence_groups": weak_groups})
    sig_weak = credibility_scorer.score_incident(weak_input)

    # Must not exceed base + 0.03
    delta = sig_weak.final_credibility_score - base_score
    assert delta <= 0.0300 + 1e-6, f"Weak link delta {delta} exceeded 0.03"

    # Must not cross the next threshold if base_score < threshold
    for t in (0.45, 0.50, 0.65, 0.70, 0.80, 0.82, 0.85, 0.88):
        if base_score < t:
            assert sig_weak.final_credibility_score < t, (
                f"Weak links crossed threshold {t} from base_score {base_score}"
            )
            break

    # 3. Verify strong (SUPPORTING, role_weight=1.0) links are NOT capped at 0.03
    strong_groups = [
        DigitalEvidenceGroupInput(
            provenance_key=f"domain_official_{i}.gov",
            max_confidence=0.95,
            role_weight=1.00,  # SUPPORTING
            article_count=3,
            source_family=SourceFamily.NEWS,
        )
        for i in range(5)
    ]
    strong_input = base_input.model_copy(update={"evidence_groups": strong_groups})
    sig_strong = credibility_scorer.score_incident(strong_input)
    strong_delta = sig_strong.final_credibility_score - base_score
    assert strong_delta > 0.05, f"Strong link delta {strong_delta} was unexpectedly capped"
