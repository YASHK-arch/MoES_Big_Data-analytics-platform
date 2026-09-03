"""Repeatable local stack verification for the SIH26069 weather platform."""

import asyncio
import logging
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

from app.db.session import async_session_factory
from app.orchestration.triggers import on_incident_ingested
from app.schemas.report import CitizenReportCreate
from app.services.report_service import report_service
from app.services.retention_service import retention_service

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("scripts.verify_stack")
BACKEND_DIR = Path(__file__).resolve().parent.parent


async def verify_stack() -> int:
    passed = 0
    total = 6

    try:
        from app.core.config import settings

        logger.info("[PASS 1/6] Configuration loaded: %s", settings.PROJECT_NAME)
        passed += 1
    except Exception as exc:
        logger.error("[FAIL 1/6] Configuration import failed: %s", exc)

    migration = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=BACKEND_DIR,
        capture_output=True,
        text=True,
    )
    if migration.returncode == 0:
        logger.info("[PASS 2/6] Alembic migrations are current")
        passed += 1
    else:
        logger.error("[FAIL 2/6] Alembic failed: %s", migration.stderr.strip())

    report_id = None
    async with async_session_factory() as session:
        try:
            payload = CitizenReportCreate(
                latitude=19.0760,
                longitude=72.8777,
                category_code="FLOOD_WATERLOGGING",
                severity="MODERATE",
                title=f"Stack verification report {uuid.uuid4().hex[:8]}",
                description="Automated local stack verification report.",
                location_name="Mumbai verification point",
                occurred_at=datetime.now(timezone.utc),
            )
            report, _ = await report_service.create_citizen_report(session, payload)
            report_id = report.id
            if report.processing_status == "QUEUED":
                logger.info("[PASS 3/6] Report accepted: %s", report.tracking_id)
                passed += 1
            else:
                logger.error(
                    "[FAIL 3/6] Report accepted with unexpected status: %s",
                    report.processing_status,
                )

            if report.processing_status == "QUEUED":
                logger.info("[PASS 4/6] Immediate processing status is QUEUED")
                passed += 1
            else:
                logger.error("[FAIL 4/6] Immediate processing status is not QUEUED")

            if report_id is not None:
                await on_incident_ingested(db=session, incident_id=report_id)
                await session.refresh(report)
                if report.processing_status == "COMPLETED" and report.credibility_score > 0.0:
                    logger.info(
                        "[PASS 5/6] Pipeline completed: status=%s credibility=%.4f",
                        report.processing_status,
                        report.credibility_score,
                    )
                    passed += 1
                else:
                    logger.error(
                        "[FAIL 5/6] Pipeline result: status=%s credibility=%.4f",
                        report.processing_status,
                        report.credibility_score,
                    )
        except Exception as exc:
            logger.error("[FAIL 3-5/6] Report/pipeline verification failed: %s", exc, exc_info=True)

    async with async_session_factory() as session:
        try:
            result = await retention_service.run_retention_cycle(session=session, dry_run=True)
            logger.info(
                "[PASS 6/6] Retention dry run: archived=%d deleted_reports=%d "
                "deleted_observations=%d deleted_evidence=%d",
                result.reports_archived,
                result.reports_deleted,
                result.observations_deleted,
                result.evidence_deleted,
            )
            passed += 1
        except Exception as exc:
            logger.error("[FAIL 6/6] Retention dry run failed: %s", exc, exc_info=True)

    logger.info("Stack verification summary: %d/%d checks passed", passed, total)
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(verify_stack()))
