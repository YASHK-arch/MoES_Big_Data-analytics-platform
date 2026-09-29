"""Phase 4 Audit Test Suite — Ingestion Source Trust Score Audit (C1).

Audits and verifies that base_trust_score and source metadata are mathematically
consistent across all 9 registered ingestion sources and services:

1. NDMA_SACHET        = 0.95 (Official National Disaster Alert System)
2. CWC_NWDP           = 0.92 (Official Central Water Commission River Telemetry)
3. IMD_NOWCAST        = 0.90 (Official India Meteorological Department Warnings)
4. GDACS_FEED         = 0.88 (UN OCHA Global Disaster Alert & Coordination System)
5. DEMO_SEED          = 0.85 (High-fidelity seed verification feed)
6. OPEN_METEO         = 0.80 (Open-Meteo Virtual Meteorological Weather Stations)
7. GDELT_DOC          = 0.70 (GDELT DOC 2.0 Web News Feed)
8. CITIZEN_WEB/MOBILE = 0.60 (Unverified Citizen Intake Prior)
9. MASTODON_PUBLIC    = 0.50 (Unverified Public Mastodon Social Feed)
"""

from typing import Dict

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.ingestion import adapter_registry
from app.ingestion.cwc_adapter import CWCTelemetryAdapter
from app.ingestion.demo_adapter import DemoSeedAdapter
from app.ingestion.gdacs_adapter import GDACSAlertAdapter
from app.ingestion.gdelt_adapter import GDELTNewsAdapter
from app.ingestion.imd_adapter import IMDNowcastAdapter
from app.ingestion.mastodon_adapter import MastodonSocialAdapter
from app.ingestion.ndma_adapter import NDMASachetAdapter
from app.ingestion.open_meteo_adapter import OpenMeteoAdapter
from app.services.evidence_service import evidence_service
from app.services.observation_service import observation_service
from app.services.report_service import report_service

# Authoritative expected base trust score catalog
EXPECTED_TRUST_SCORES: Dict[str, float] = {
    "NDMA_SACHET": 0.95,
    "CWC_NWDP": 0.92,
    "IMD_NOWCAST": 0.90,
    "GDACS_FEED": 0.88,
    "OPEN_METEO": 0.80,
    "DEMO_FEED": 0.75,
    "GDELT_DOC": 0.70,
    "MASTODON_PUBLIC": 0.60,
}


class TestSourceTrustScoreAudit:
    """Audit tests for ingestion source trust scores."""

    def test_adapter_class_trust_scores(self):
        """Audit individual adapter class base_trust_score attributes."""
        assert NDMASachetAdapter().base_trust_score == 0.95
        assert CWCTelemetryAdapter().base_trust_score == 0.92
        assert IMDNowcastAdapter().base_trust_score == 0.90
        assert GDACSAlertAdapter().base_trust_score == 0.88
        assert OpenMeteoAdapter().base_trust_score == 0.80
        assert DemoSeedAdapter().base_trust_score == 0.75
        assert GDELTNewsAdapter().base_trust_score == 0.70
        assert MastodonSocialAdapter().base_trust_score == 0.60

    def test_adapter_registry_resolves_authoritative_trust_scores(self):
        """Verify adapter_registry returns exact expected trust scores for all registered sources."""
        for source_code, expected_trust in EXPECTED_TRUST_SCORES.items():
            adapter = adapter_registry.get(source_code)
            assert adapter is not None, f"Source '{source_code}' missing from adapter_registry!"
            assert adapter.base_trust_score == pytest.approx(expected_trust), (
                f"Source '{source_code}' has trust score {adapter.base_trust_score}, expected {expected_trust}!"
            )

    def test_trust_score_ordering_hierarchy(self):
        """Verify strict mathematical hierarchy of trust priors across categories:
        Official Gov (0.90-0.95) > International UN (0.88) > Sensor/Meteo (0.80-0.92) > News (0.70) >= Public Social/Citizen (0.60)
        """
        ndma = adapter_registry.get("NDMA_SACHET").base_trust_score
        cwc = adapter_registry.get("CWC_NWDP").base_trust_score
        imd = adapter_registry.get("IMD_NOWCAST").base_trust_score
        gdacs = adapter_registry.get("GDACS_FEED").base_trust_score
        open_meteo = adapter_registry.get("OPEN_METEO").base_trust_score
        gdelt = adapter_registry.get("GDELT_DOC").base_trust_score
        mastodon = adapter_registry.get("MASTODON_PUBLIC").base_trust_score

        assert ndma > gdacs > open_meteo > gdelt >= mastodon
        assert cwc > open_meteo > mastodon
        assert imd >= 0.90

    @pytest.mark.asyncio
    async def test_report_service_get_or_create_source_dynamic_lookup(self, db_session: AsyncSession):
        """ReportService.get_or_create_source dynamically resolves trust score from adapter_registry."""
        for code, expected_trust in EXPECTED_TRUST_SCORES.items():
            source = await report_service.get_or_create_source(db_session, source_code=code)
            assert source.base_trust_score == pytest.approx(expected_trust)

    @pytest.mark.asyncio
    async def test_evidence_service_get_or_create_source_dynamic_lookup(self, db_session: AsyncSession):
        """EvidenceService.get_or_create_source dynamically resolves trust score from adapter_registry."""
        source_gdelt = await evidence_service.get_or_create_source(db_session, source_code="GDELT_DOC")
        assert source_gdelt.base_trust_score == pytest.approx(0.70)

        source_mastodon = await evidence_service.get_or_create_source(
            db_session, source_code="MASTODON_PUBLIC"
        )
        assert source_mastodon.base_trust_score == pytest.approx(0.60)

    @pytest.mark.asyncio
    async def test_observation_service_get_or_create_source_dynamic_lookup(self, db_session: AsyncSession):
        """ObservationService.get_or_create_source dynamically resolves trust score from adapter_registry."""
        source_cwc = await observation_service.get_or_create_source(db_session, source_code="CWC_NWDP")
        assert source_cwc.base_trust_score == pytest.approx(0.92)

        source_om = await observation_service.get_or_create_source(db_session, source_code="OPEN_METEO")
        assert source_om.base_trust_score == pytest.approx(0.80)
