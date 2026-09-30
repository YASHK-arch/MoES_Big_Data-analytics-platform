"""P6 Invariant Test: Verification status is never mutated by credibility scores.

Enforces Product Rule P6:
"Nothing in this feature may set a verification status. Add a test proving no code path
changes status from a score."
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.orchestration.handlers import StageName
from app.orchestration.incident_pipeline import incident_pipeline
from app.models.report import WeatherReport
from app.models.source import Source


@pytest.mark.asyncio
class TestP6VerificationStatusInvariant:
    """Rigorous verification that machine scoring never modifies verification status."""

    async def _create_test_report(
        self, db: AsyncSession, initial_status: str = "PENDING"
    ) -> WeatherReport:
        src_stmt = select(Source).limit(1)
        res = await db.execute(src_stmt)
        source = res.scalar_one_or_none()
        if not source:
            source = Source(
                id=uuid.uuid4(),
                code="CITIZEN_P6",
                name="Citizen Portal",
                source_type="CITIZEN",
                base_trust_score=0.45,
            )
            db.add(source)
            await db.flush()

        occurred = datetime(2026, 7, 15, 12, 0, tzinfo=timezone.utc)
        report = WeatherReport(
            id=uuid.uuid4(),
            tracking_id=f"P6-{uuid.uuid4().hex[:8].upper()}",
            source_id=source.id,
            reported_category="HEAVY_RAINFALL",
            severity="SEVERE",
            title="P6 Invariant Test Report",
            description="Testing that verification status never changes from score.",
            latitude=28.6139,
            longitude=77.2090,
            geom=func.ST_SetSRID(func.ST_MakePoint(77.2090, 28.6139), 4326),
            occurred_at=occurred,
            verification_status=initial_status,
            processing_status="PROCESSING",
        )
        db.add(report)
        await db.commit()
        await db.refresh(report)
        return report

    async def test_credibility_pipeline_never_mutates_pending_status(
        self, db_session: AsyncSession
    ) -> None:
        """Executing credibility scoring on PENDING report updates score but leaves status PENDING."""
        report = await self._create_test_report(db_session, initial_status="PENDING")
        assert report.verification_status == "PENDING"

        # Execute credibility stage
        await incident_pipeline.execute_single_stage(
            db=db_session,
            incident_id=report.id,
            stage_name=StageName.CREDIBILITY,
            commit=True,
        )

        await db_session.refresh(report)
        # Score is populated
        assert report.credibility_score is not None
        # Invariant P6: Verification status MUST remain strictly PENDING
        assert report.verification_status == "PENDING"

    async def test_credibility_pipeline_never_mutates_under_review_status(
        self, db_session: AsyncSession
    ) -> None:
        """Executing credibility scoring on UNDER_REVIEW report leaves status UNDER_REVIEW."""
        report = await self._create_test_report(db_session, initial_status="UNDER_REVIEW")
        assert report.verification_status == "UNDER_REVIEW"

        await incident_pipeline.execute_single_stage(
            db=db_session,
            incident_id=report.id,
            stage_name=StageName.CREDIBILITY,
            commit=True,
        )

        await db_session.refresh(report)
        assert report.credibility_score is not None
        assert report.verification_status == "UNDER_REVIEW"

    async def test_credibility_pipeline_never_mutates_verified_status(
        self, db_session: AsyncSession
    ) -> None:
        """Even if score is low or penalized, VERIFIED status set by human operator remains unchanged."""
        report = await self._create_test_report(db_session, initial_status="VERIFIED")
        assert report.verification_status == "VERIFIED"

        await incident_pipeline.execute_single_stage(
            db=db_session,
            incident_id=report.id,
            stage_name=StageName.CREDIBILITY,
            commit=True,
        )

        await db_session.refresh(report)
        assert report.verification_status == "VERIFIED"
