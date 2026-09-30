import uuid
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from geoalchemy2.shape import from_shape
from shapely.geometry import Point
from sqlalchemy import pool, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.intelligence import (
    EvidenceRelationship,
    EvidenceScorer,
    evidence_linking_engine,
    evidence_scorer,
    run_evidence_benchmark_evaluation,
)
from app.models.category import EventCategory
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


def test_evidence_scorer_direct_supporting():
    """Verify direct GDELT/Mastodon supporting news matches incident with SUPPORTING."""
    scorer = EvidenceScorer()
    res = scorer.score_link(
        incident_id=uuid.uuid4(),
        evidence_id=uuid.uuid4(),
        incident_title="Severe waterlogging near Andheri subway",
        incident_desc="Water knee-deep near railway station subway.",
        incident_cat="FLOOD_WATERLOGGING",
        incident_lat=19.1197,
        incident_lon=72.8468,
        incident_time=datetime(2026, 8, 29, 10, 0, tzinfo=timezone.utc),
        incident_loc_name="Andheri, Mumbai",
        evidence_title="Heavy rains cause severe waterlogging at Andheri subway in Mumbai",
        evidence_snippet="Subway traffic suspended as water levels rise outside Andheri station.",
        evidence_source_type="GDELT",
        evidence_pub_time=datetime(2026, 8, 29, 10, 30, tzinfo=timezone.utc),
    )
    assert res.relationship_type == EvidenceRelationship.SUPPORTING
    assert res.overall_score >= 0.65
    assert "Supporting" in res.explanation


def test_evidence_scorer_foreign_event_rejection():
    """Verify foreign news (Nepal flood) is strictly rejected as IRRELEVANT for Indian incidents."""
    scorer = EvidenceScorer()
    res = scorer.score_link(
        incident_id=uuid.uuid4(),
        evidence_id=uuid.uuid4(),
        incident_title="Waterlogging in Mumbai coastal belt",
        incident_desc="High tide surges water onto promenade.",
        incident_cat="FLOOD_WATERLOGGING",
        incident_lat=19.0760,
        incident_lon=72.8777,
        incident_time=datetime(2026, 8, 29, 10, 0, tzinfo=timezone.utc),
        incident_loc_name="Mumbai, Maharashtra",
        evidence_title="Severe floods in Nepal claim 20 lives after cloudburst",
        evidence_snippet="Rivers overflow across Nepal as continuous rains batter Kathmandu.",
        evidence_source_type="GDELT",
        evidence_pub_time=datetime(2026, 8, 29, 10, 30, tzinfo=timezone.utc),
    )
    assert res.relationship_type == EvidenceRelationship.IRRELEVANT
    assert res.overall_score == 0.0
    assert "foreign" in res.explanation.lower()


def test_evidence_scorer_different_city_rejection():
    """Verify news in a different city (Delhi vs Mumbai) is strictly rejected as IRRELEVANT."""
    scorer = EvidenceScorer()
    res = scorer.score_link(
        incident_id=uuid.uuid4(),
        evidence_id=uuid.uuid4(),
        incident_title="Waterlogging in Andheri Mumbai",
        incident_desc="Roads flooded in western suburbs.",
        incident_cat="FLOOD_WATERLOGGING",
        incident_lat=19.1197,
        incident_lon=72.8468,
        incident_time=datetime(2026, 8, 29, 10, 0, tzinfo=timezone.utc),
        incident_loc_name="Andheri, Mumbai",
        evidence_title="Severe waterlogging at ITO junction Delhi after heavy rain",
        evidence_snippet="Traffic halted near ITO and Pragati Maidan in New Delhi.",
        evidence_source_type="GDELT",
        evidence_pub_time=datetime(2026, 8, 29, 10, 20, tzinfo=timezone.utc),
    )
    assert res.relationship_type == EvidenceRelationship.IRRELEVANT
    assert res.overall_score == 0.0


def test_evidence_scorer_historical_mismatch_rejection():
    """Verify historical news (> 48h horizon) is strictly rejected as IRRELEVANT."""
    scorer = EvidenceScorer()
    res = scorer.score_link(
        incident_id=uuid.uuid4(),
        evidence_id=uuid.uuid4(),
        incident_title="Waterlogging in Andheri subway",
        incident_desc="Subway closed due to water accumulation.",
        incident_cat="FLOOD_WATERLOGGING",
        incident_lat=19.1197,
        incident_lon=72.8468,
        incident_time=datetime(2026, 8, 29, 10, 0, tzinfo=timezone.utc),
        incident_loc_name="Andheri, Mumbai",
        evidence_title="Memories of 2005 Mumbai floods and underpass submergence",
        evidence_snippet="A retrospective look at historical urban drainage issues in Mumbai.",
        evidence_source_type="NEWS_PORTAL",
        evidence_pub_time=datetime(2020, 7, 26, 10, 0, tzinfo=timezone.utc),
    )
    assert res.relationship_type == EvidenceRelationship.IRRELEVANT
    assert res.overall_score == 0.0
    assert "exceeding" in res.explanation.lower()


def test_evidence_scorer_incompatible_hazard_rejection():
    """Verify incompatible hazard (Heatwave vs Flood) is strictly rejected as IRRELEVANT."""
    scorer = EvidenceScorer()
    res = scorer.score_link(
        incident_id=uuid.uuid4(),
        evidence_id=uuid.uuid4(),
        incident_title="Flash flooding in residential sectors",
        incident_desc="Heavy cloudburst fills street drains.",
        incident_cat="FLOOD_WATERLOGGING",
        incident_lat=19.0760,
        incident_lon=72.8777,
        incident_time=datetime(2026, 8, 29, 12, 0, tzinfo=timezone.utc),
        incident_loc_name="Mumbai, Maharashtra",
        evidence_title="Scorching heatwave warning issued across district",
        evidence_snippet="Dry heatwave conditions with zero rain expected for next week.",
        evidence_source_type="NEWS_PORTAL",
        evidence_pub_time=datetime(2026, 8, 29, 12, 15, tzinfo=timezone.utc),
    )
    assert res.relationship_type == EvidenceRelationship.IRRELEVANT
    assert res.overall_score == 0.0
    assert "incompatible" in res.explanation.lower()


def test_evidence_scorer_contextual_government_release():
    """Verify PIB government preparedness reviews are categorized as CONTEXTUAL, not proof."""
    scorer = EvidenceScorer()
    res = scorer.score_link(
        incident_id=uuid.uuid4(),
        evidence_id=uuid.uuid4(),
        incident_title="Flooding in low lying neighborhoods in Mumbai",
        incident_desc="Water entering residential ground floors.",
        incident_cat="FLOOD_WATERLOGGING",
        incident_lat=19.0760,
        incident_lon=72.8777,
        incident_time=datetime(2026, 8, 29, 10, 0, tzinfo=timezone.utc),
        incident_loc_name="Mumbai, Maharashtra",
        evidence_title="Minister chairs monsoon flood preparedness review meeting",
        evidence_snippet="NDRF teams deployed as precautionary measure to monitor flood situation.",
        evidence_source_type="GOVERNMENT_PIB",
        evidence_pub_time=datetime(2026, 8, 29, 12, 0, tzinfo=timezone.utc),
    )
    assert res.relationship_type == EvidenceRelationship.CONTEXTUAL
    assert "Contextual" in res.explanation


def test_evidence_scorer_contradictory_debunking():
    """Verify explicit debunking/denial statements are categorized as CONTRADICTORY."""
    scorer = EvidenceScorer()
    res = scorer.score_link(
        incident_id=uuid.uuid4(),
        evidence_id=uuid.uuid4(),
        incident_title="Bridge collapse reported near Dadar TT circle",
        incident_desc="Citizen reports bridge collapse under flood waters.",
        incident_cat="FLOOD_WATERLOGGING",
        incident_lat=19.0178,
        incident_lon=72.8478,
        incident_time=datetime(2026, 8, 29, 14, 0, tzinfo=timezone.utc),
        incident_loc_name="Dadar, Mumbai",
        evidence_title="Police denies reports of bridge collapse near Dadar TT circle",
        evidence_snippet="Traffic police confirms fake news; no waterlogging at Dadar bridge.",
        evidence_source_type="NEWS_PORTAL",
        evidence_pub_time=datetime(2026, 8, 29, 14, 30, tzinfo=timezone.utc),
    )
    assert res.relationship_type == EvidenceRelationship.CONTRADICTORY
    assert "denial" in res.explanation.lower() or "contradict" in res.explanation.lower()


def test_evidence_evaluation_benchmark_all_passed():
    """Verify all 35 synthetic benchmark evaluation pairs pass with 100% precision & recall."""
    metrics = run_evidence_benchmark_evaluation(evidence_scorer)
    assert metrics["dataset_name"] == "Synthetic Evidence-Linking Benchmark Only"
    assert metrics["total_pairs"] == 65
    assert metrics["false_positives"] == 0
    assert metrics["false_negatives"] == 0
    assert metrics["precision"] == 1.0
    assert metrics["recall"] == 1.0
    assert metrics["f1_score"] == 1.0
    assert metrics["all_passed"] is True


def test_cwc_observation_cannot_enter_evidence_linking_engine():
    """Architectural regression test proving CWC observation cannot enter EvidenceLinkingEngine."""
    # 1. Verify table-level domain separation
    assert hasattr(IncidentEvidenceLink, "evidence_id")
    assert not hasattr(IncidentEvidenceLink, "observation_id")

    # 2. Verify WeatherObservation model is distinct from EvidenceItem
    cwc_obs = WeatherObservation(
        source_id=uuid.uuid4(),
        station_code="CWC-YAMUNA-01",
        station_name="Old Railway Bridge Yamuna",
        geom=from_shape(Point(77.2090, 28.6139), srid=4326),
        observed_at=datetime.now(timezone.utc),
        water_level_m=205.33,
        rainfall_mm=12.5,
    )

    # 3. Verify EvidenceItem requires title, url/snippet, and is an evidence artifact
    assert not hasattr(cwc_obs, "title")
    assert not hasattr(cwc_obs, "text_snippet")
    assert isinstance(cwc_obs, WeatherObservation)
    assert not isinstance(cwc_obs, EvidenceItem)


@pytest.mark.asyncio
async def test_evidence_linking_lifecycle_and_idempotency(db_session: AsyncSession):
    """Verify link lifecycle, idempotency, updates, and human override safety."""
    # 1. Sources & Categories setup
    src_stmt = select(Source).where(Source.source_code == "CITIZEN")
    src_res = await db_session.execute(src_stmt)
    source = src_res.scalar_one_or_none()
    if not source:
        source = Source(
            source_code="CITIZEN",
            name="Citizen Ingestion",
            source_type="CITIZEN",
            base_trust_score=0.5,
            is_active=True,
        )
        db_session.add(source)
        await db_session.flush()

    gdelt_src_stmt = select(Source).where(Source.source_code == "GDELT_DOC_API")
    gdelt_src_res = await db_session.execute(gdelt_src_stmt)
    gdelt_source = gdelt_src_res.scalar_one_or_none()
    if not gdelt_source:
        gdelt_source = Source(
            source_code="GDELT_DOC_API",
            name="GDELT Document API Ingestion",
            source_type="GDELT",
            base_trust_score=0.7,
            is_active=True,
        )
        db_session.add(gdelt_source)
        await db_session.flush()

    cat_stmt = select(EventCategory).where(EventCategory.category_code == "FLOOD_WATERLOGGING")
    cat_res = await db_session.execute(cat_stmt)
    category = cat_res.scalar_one_or_none()
    if not category:
        category = EventCategory(
            category_code="FLOOD_WATERLOGGING",
            title="Flood / Waterlogging",
            severity_default="HIGH",
            color_hex="#3B82F6",
            icon_name="waves",
        )
        db_session.add(category)
        await db_session.flush()

    base_time = datetime(2038, 1, 1, 12, 0, tzinfo=timezone.utc)

    # 2. Insert Incident A (Mumbai Andheri) & Incident C (Mumbai Kurla) & Incident B (Delhi)
    inc_a = WeatherReport(
        tracking_id=f"TRK-2026-{uuid.uuid4().hex[:6].upper()}",
        source_id=source.id,
        category_id=category.id,
        external_id=f"TEST-INCA-{uuid.uuid4().hex[:8]}",
        title="Severe waterlogging near Andheri subway",
        description="Vehicles stranded in deep flood water.",
        location_name="Andheri subway, Mumbai",
        latitude=19.1197,
        longitude=72.8468,
        geom=from_shape(Point(72.8468, 19.1197), srid=4326),
        occurred_at=base_time,
        verification_status="PENDING",
        credibility_score=0.7,
    )
    inc_c = WeatherReport(
        tracking_id=f"TRK-2026-{uuid.uuid4().hex[:6].upper()}",
        source_id=source.id,
        category_id=category.id,
        external_id=f"TEST-INCC-{uuid.uuid4().hex[:8]}",
        title="Kurla railway colony inundated with flood water",
        description="Kurla railway tracks waterlogged.",
        location_name="Kurla, Mumbai",
        latitude=19.0726,
        longitude=72.8845,
        geom=from_shape(Point(72.8845, 19.0726), srid=4326),
        occurred_at=base_time,
        verification_status="PENDING",
        credibility_score=0.7,
    )
    inc_b = WeatherReport(
        tracking_id=f"TRK-2026-{uuid.uuid4().hex[:6].upper()}",
        source_id=source.id,
        category_id=category.id,
        external_id=f"TEST-INCB-{uuid.uuid4().hex[:8]}",
        title="Severe waterlogging at Lajpat Nagar underpass",
        description="Lajpat Nagar underpass flooded in South Delhi.",
        location_name="Lajpat Nagar, New Delhi",
        latitude=28.5677,
        longitude=77.2433,
        geom=from_shape(Point(77.2433, 28.5677), srid=4326),
        occurred_at=base_time,
        verification_status="PENDING",
        credibility_score=0.7,
    )
    db_session.add_all([inc_a, inc_c, inc_b])
    await db_session.flush()

    # 3. Insert Evidence E1 (Mumbai Andheri Flood News)
    evi_1 = EvidenceItem(
        source_id=gdelt_source.id,
        external_id=f"GDELT-LIFECYCLE-{uuid.uuid4().hex[:8]}",
        evidence_type="NEWS_ARTICLE",
        title="Heavy rains cause severe waterlogging at Andheri subway in Mumbai",
        text_snippet="Traffic suspended outside Andheri station as subway is inundated.",
        url="https://example.com/news/andheri-flood-2038",
        publisher_domain="example.com",
        language="English",
        published_at=base_time + timedelta(minutes=30),
        captured_at=base_time + timedelta(minutes=35),
    )
    db_session.add(evi_1)
    await db_session.flush()

    # 4. Multi-Incident Evaluation:
    # E1 matches Incident A (SUPPORTING) within 25km radius
    results_e1 = await evidence_linking_engine.evaluate_and_link_evidence(db_session, evi_1)
    assert len(results_e1) >= 1

    res_a = next(r for r in results_e1 if r.incident_id == inc_a.id)
    assert res_a.is_linked is True
    assert res_a.relationship_type == EvidenceRelationship.SUPPORTING

    # Check pairwise scoring against distant Incident B -> IRRELEVANT (no link created)
    score_b = evidence_scorer.score_link(
        incident_id=inc_b.id,
        evidence_id=evi_1.id,
        incident_title=inc_b.title,
        incident_desc=inc_b.description,
        incident_cat="FLOOD_WATERLOGGING",
        incident_lat=inc_b.latitude,
        incident_lon=inc_b.longitude,
        incident_time=inc_b.occurred_at,
        incident_loc_name=inc_b.location_name,
        evidence_title=evi_1.title,
        evidence_snippet=evi_1.text_snippet,
        evidence_source_type="GDELT",
        evidence_pub_time=evi_1.published_at,
    )
    assert score_b.relationship_type == EvidenceRelationship.IRRELEVANT
    assert score_b.overall_score == 0.0

    # 5. Check Persistence: Evidence E1 links to both Mumbai incidents (A and C), but not Delhi (B)
    links_stmt = select(IncidentEvidenceLink).where(IncidentEvidenceLink.evidence_id == evi_1.id)
    links_res = await db_session.execute(links_stmt)
    persisted_links = links_res.scalars().all()
    assert len(persisted_links) == 2
    assert {lnk.report_id for lnk in persisted_links} == {inc_a.id, inc_c.id}
    assert inc_b.id not in {lnk.report_id for lnk in persisted_links}

    # 6. Idempotency: Repeated evaluation does not duplicate link rows
    rerun_results = await evidence_linking_engine.evaluate_and_link_evidence(db_session, evi_1)
    assert len(rerun_results) >= 2

    links_res2 = await db_session.execute(links_stmt)
    persisted_links2 = links_res2.scalars().all()
    assert len(persisted_links2) == 2
    assert {lnk.id for lnk in persisted_links2} == {lnk.id for lnk in persisted_links}

    # 7. Human Override Protection on Incident A link:
    # Simulate a human operator setting a custom manual decision
    link_a = next(lnk for lnk in persisted_links2 if lnk.report_id == inc_a.id)
    link_a.link_role = "MANUAL_VERIFIED_SUPPORT"
    link_a.confidence_score = 0.99
    match_dict = link_a.match_explanation or {}
    match_dict["is_human_override"] = True
    link_a.match_explanation = match_dict
    await db_session.flush()

    # Automated re-evaluation MUST NOT overwrite operator's decision
    await evidence_linking_engine.evaluate_and_link_evidence(db_session, evi_1)

    links_res3 = await db_session.execute(links_stmt)
    persisted_links3 = links_res3.scalars().all()
    assert len(persisted_links3) == 2
    re_link_a = next(lnk for lnk in persisted_links3 if lnk.report_id == inc_a.id)
    assert re_link_a.link_role == "MANUAL_VERIFIED_SUPPORT"
    assert re_link_a.confidence_score == 0.99
    assert re_link_a.match_explanation is not None
    assert "last_automated_assessment" in re_link_a.match_explanation

    # 8. WeatherReport verification status safety
    rep_check = await db_session.execute(select(WeatherReport).where(WeatherReport.id == inc_a.id))
    assert rep_check.scalar_one().verification_status == "PENDING"


def test_location_gate_puri_vs_mumbai_no_coords():
    """Verify coordinate-less Puri evidence does NOT link to coordinate-less Mumbai incident."""
    scorer = EvidenceScorer()
    res = scorer.score_link(
        incident_id=uuid.uuid4(),
        evidence_id=uuid.uuid4(),
        incident_title="Severe waterlogging in Mumbai",
        incident_desc="Heavy monsoon downpour submerges roads in Mumbai.",
        incident_cat="FLOOD_WATERLOGGING",
        incident_lat=None,
        incident_lon=None,
        incident_time=datetime(2026, 8, 29, 10, 0, tzinfo=timezone.utc),
        incident_loc_name="Mumbai, Maharashtra",
        evidence_title="Heavy rains cause waterlogging in Puri",
        evidence_snippet="Torrential rain submerges Grand Road in Puri town.",
        evidence_source_type="NEWS_PORTAL",
        evidence_pub_time=datetime(2026, 8, 29, 10, 30, tzinfo=timezone.utc),
    )
    assert res.relationship_type == EvidenceRelationship.IRRELEVANT
    assert res.overall_score == 0.0


def test_location_gate_goa_vs_bengaluru_no_coords():
    """Verify coordinate-less Goa evidence does NOT link to coordinate-less Bengaluru incident."""
    scorer = EvidenceScorer()
    res = scorer.score_link(
        incident_id=uuid.uuid4(),
        evidence_id=uuid.uuid4(),
        incident_title="Flooding across Bengaluru tech corridors",
        incident_desc="Waterlogging on Outer Ring Road in Bengaluru.",
        incident_cat="FLOOD_WATERLOGGING",
        incident_lat=None,
        incident_lon=None,
        incident_time=datetime(2026, 8, 29, 12, 0, tzinfo=timezone.utc),
        incident_loc_name="Bengaluru, Karnataka",
        evidence_title="Goa coastal weather warning issued",
        evidence_snippet="Heavy downpours submerge coastal streets across Goa.",
        evidence_source_type="NEWS_PORTAL",
        evidence_pub_time=datetime(2026, 8, 29, 12, 30, tzinfo=timezone.utc),
    )
    assert res.relationship_type == EvidenceRelationship.IRRELEVANT
    assert res.overall_score == 0.0


def test_location_gate_mumbai_vs_kurla_no_coords_links():
    """Verify coordinate-less Kurla evidence still links to coordinate-less Mumbai incident."""
    scorer = EvidenceScorer()
    res = scorer.score_link(
        incident_id=uuid.uuid4(),
        evidence_id=uuid.uuid4(),
        incident_title="Severe waterlogging across Mumbai suburban stations",
        incident_desc="Tracks and arterial roads submerged across Mumbai suburbs.",
        incident_cat="FLOOD_WATERLOGGING",
        incident_lat=None,
        incident_lon=None,
        incident_time=datetime(2026, 8, 29, 10, 0, tzinfo=timezone.utc),
        incident_loc_name="Mumbai, Maharashtra",
        evidence_title="Kurla railway station tracks waterlogged in Mumbai",
        evidence_snippet="Suburban train services disrupted due to water accumulation at Kurla in Mumbai.",
        evidence_source_type="NEWS_PORTAL",
        evidence_pub_time=datetime(2026, 8, 29, 10, 30, tzinfo=timezone.utc),
    )
    assert res.relationship_type in (EvidenceRelationship.SUPPORTING, EvidenceRelationship.RELATED)
    assert res.overall_score > 0.0


def test_location_gate_coordinate_cases_unchanged():
    """Verify coordinate-based links remain unchanged by the location gate."""
    scorer = EvidenceScorer()
    # Case 1: Matching coordinates in Mumbai -> SUPPORTING
    res_close = scorer.score_link(
        incident_id=uuid.uuid4(),
        evidence_id=uuid.uuid4(),
        incident_title="Severe waterlogging near Andheri subway",
        incident_desc="Water knee-deep near railway station subway.",
        incident_cat="FLOOD_WATERLOGGING",
        incident_lat=19.1197,
        incident_lon=72.8468,
        incident_time=datetime(2026, 8, 29, 10, 0, tzinfo=timezone.utc),
        incident_loc_name="Andheri, Mumbai",
        evidence_title="Heavy rains cause severe waterlogging at Andheri subway in Mumbai",
        evidence_snippet="Subway traffic suspended as water levels rise outside Andheri station.",
        evidence_source_type="GDELT",
        evidence_pub_time=datetime(2026, 8, 29, 10, 30, tzinfo=timezone.utc),
    )
    assert res_close.relationship_type == EvidenceRelationship.SUPPORTING
    assert res_close.overall_score >= 0.65

    # Case 2: Distant coordinates (> 25km) -> IRRELEVANT (Pune vs Mumbai)
    res_far = scorer.score_link(
        incident_id=uuid.uuid4(),
        evidence_id=uuid.uuid4(),
        incident_title="Waterlogging in Mumbai south",
        incident_desc="Streets flooded near Colaba.",
        incident_cat="FLOOD_WATERLOGGING",
        incident_lat=18.9067,
        incident_lon=72.8147,
        incident_time=datetime(2026, 8, 29, 10, 0, tzinfo=timezone.utc),
        incident_loc_name="Colaba, Mumbai",
        evidence_title="Severe flooding across Pune streets after cloudburst",
        evidence_snippet="Streets in Pune flooded with high water levels.",
        evidence_source_type="NEWS_PORTAL",
        evidence_pub_time=datetime(2026, 8, 29, 10, 30, tzinfo=timezone.utc),
    )
    # Pune is > 100km from Colaba
    assert res_far.relationship_type == EvidenceRelationship.IRRELEVANT
    assert res_far.overall_score == 0.0

