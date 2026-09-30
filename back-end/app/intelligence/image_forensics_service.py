"""Database service and worker pipeline for image forensics.

Processes uploaded images, extracts EXIF, computes pHash/dHash, detects cross-incident
reuse, persists findings idempotently, updates credibility, and stages outbox SSE events.
"""

from __future__ import annotations

from datetime import datetime, timezone
import logging
from typing import Any, Dict, List, Optional
import uuid

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.intelligence.credibility_collector import credibility_collector
from app.intelligence.credibility_scorer import credibility_scorer
from app.intelligence.image_forensics import (
    ForensicVerdict,
    ImageForensicResult,
    IncidentForensicsSummary,
    hamming_distance,
    process_raw_image_bytes,
)
from app.models.image_forensics import ImageHash, IncidentImageFinding
from app.models.media import ReportMedia
from app.models.outbox import RealtimeOutbox
from app.models.report import WeatherReport
from app.services.storage import storage_service

logger = logging.getLogger(__name__)


class ImageForensicsService:
    """Service coordinating image forensics extraction, persistence, and event delivery."""

    async def lookup_candidate_matches(
        self,
        db: AsyncSession,
        sha256: str,
        phash: str,
        max_hamming: int = 10,
    ) -> List[Dict[str, Any]]:
        """Find matching image hashes across the platform.

        Strategy:
        1. Exact SHA-256 matches (identical binary)
        2. Exact pHash matches
        3. Near matches (prefix filtering + bitwise Hamming distance <= max_hamming)
        """
        # Prefix for fast candidate pruning: first 4 hex chars (16 bits)
        prefix = phash[:3] if len(phash) >= 3 else phash

        stmt = (
            select(
                ImageHash.incident_id,
                ImageHash.phash,
                ImageHash.sha256,
                ImageHash.created_at,
                WeatherReport.occurred_at,
                WeatherReport.latitude,
                WeatherReport.longitude,
            )
            .outerjoin(WeatherReport, ImageHash.incident_id == WeatherReport.id)
            .where(
                or_(
                    ImageHash.sha256 == sha256,
                    ImageHash.phash == phash,
                    ImageHash.phash.startswith(prefix),
                )
            )
            .limit(100)
        )
        res = await db.execute(stmt)
        rows = res.all()

        candidates: List[Dict[str, Any]] = []
        for row in rows:
            inc_id, cand_phash, cand_sha, cand_created, cand_occ, cand_lat, cand_lon = row
            if cand_sha == sha256 or cand_phash == phash or hamming_distance(phash, cand_phash) <= max_hamming:
                candidates.append(
                    {
                        "incident_id": str(inc_id) if inc_id else None,
                        "phash": cand_phash,
                        "sha256": cand_sha,
                        "created_at": cand_created,
                        "occurred_at": cand_occ,
                        "latitude": float(cand_lat) if cand_lat is not None else None,
                        "longitude": float(cand_lon) if cand_lon is not None else None,
                    }
                )

        return candidates

    async def process_report_media(
        self,
        db: AsyncSession,
        report: WeatherReport,
        media: ReportMedia,
        image_bytes: Optional[bytes] = None,
    ) -> IncidentImageFinding:
        """Process a single media item, compute hashes/EXIF, and persist idempotently."""
        # 1. Obtain image bytes
        if image_bytes is None:
            try:
                obj = storage_service.client.get_object(
                    Bucket=media.storage_bucket,
                    Key=media.storage_key,
                )
                image_bytes = obj["Body"].read()
            except Exception as e:
                logger.warning("Failed to fetch image bytes from storage for media %s: %s", media.id, e)
                image_bytes = b""

        # 2. Extract hashes or process bytes
        incident_dt = report.occurred_at
        if incident_dt and incident_dt.tzinfo is None:
            incident_dt = incident_dt.replace(tzinfo=timezone.utc)

        inc_lat = float(report.latitude) if report.latitude is not None else None
        inc_lon = float(report.longitude) if report.longitude is not None else None

        # Look up reuse candidates if we can derive a hash
        candidates: List[Dict[str, Any]] = []
        if image_bytes:
            # Quick candidate check with media's existing sha256 if available
            cand_sha = media.sha256_hash or ""
            candidates = await self.lookup_candidate_matches(
                db=db,
                sha256=cand_sha,
                phash="0" * 16,
            )

        # 3. Pure logic forensic evaluation
        forensic_result: ImageForensicResult = process_raw_image_bytes(
            image_bytes=image_bytes,
            incident_dt_utc=incident_dt,
            incident_lat=inc_lat,
            incident_lon=inc_lon,
            current_incident_id=str(report.id),
            candidate_matches=candidates,
            media_id=str(media.id),
        )

        # If we got a valid phash from decode, do a deeper candidate lookup if none found yet
        if forensic_result.phash != "0" * 16:
            more_candidates = await self.lookup_candidate_matches(
                db=db,
                sha256=forensic_result.sha256,
                phash=forensic_result.phash,
                max_hamming=getattr(settings, "IMAGE_FORENSICS_PHASH_THRESHOLD", 10),
            )
            # Re-evaluate with discovered candidates
            forensic_result = process_raw_image_bytes(
                image_bytes=image_bytes,
                incident_dt_utc=incident_dt,
                incident_lat=inc_lat,
                incident_lon=inc_lon,
                current_incident_id=str(report.id),
                candidate_matches=more_candidates,
                media_id=str(media.id),
            )

        # 4. Upsert ImageHash record (idempotent on media_id)
        hash_stmt = select(ImageHash).where(ImageHash.media_id == media.id).limit(1)
        res_hash = await db.execute(hash_stmt)
        hash_record = res_hash.scalar_one_or_none()

        if hash_record is None:
            hash_record = ImageHash(
                id=uuid.uuid4(),
                media_id=media.id,
                incident_id=report.id,
                sha256=forensic_result.sha256,
                phash=forensic_result.phash,
                dhash=forensic_result.dhash,
                created_at=datetime.now(timezone.utc),
            )
            db.add(hash_record)
        else:
            hash_record.sha256 = forensic_result.sha256
            hash_record.phash = forensic_result.phash
            hash_record.dhash = forensic_result.dhash

        # 5. Upsert IncidentImageFinding (idempotent on (incident_id, media_id))
        finding_stmt = (
            select(IncidentImageFinding)
            .where(
                IncidentImageFinding.incident_id == report.id,
                IncidentImageFinding.media_id == media.id,
            )
            .limit(1)
        )
        res_finding = await db.execute(finding_stmt)
        finding_record = res_finding.scalar_one_or_none()

        time_check = next((c for c in forensic_result.checks if c.check_type == "EXIF_TIME"), None)
        gps_check = next((c for c in forensic_result.checks if c.check_type == "EXIF_LOCATION"), None)
        reuse_check = next((c for c in forensic_result.checks if c.check_type == "IMAGE_REUSE"), None)

        time_verdict = time_check.verdict.value if time_check else "NEUTRAL"
        time_diff = time_check.difference if time_check else None
        gps_verdict = gps_check.verdict.value if gps_check else "NEUTRAL"
        gps_diff = gps_check.difference if gps_check else None
        reuse_verdict = reuse_check.verdict.value if reuse_check else "NEUTRAL"
        matched_ids = reuse_check.matched_incident_ids if reuse_check else []

        exif_dt_parsed = None
        if forensic_result.exif_timestamp_utc:
            try:
                exif_dt_parsed = datetime.fromisoformat(forensic_result.exif_timestamp_utc)
            except ValueError:
                pass

        checks_payload = [c.model_dump() for c in forensic_result.checks]

        if finding_record is None:
            finding_record = IncidentImageFinding(
                id=uuid.uuid4(),
                incident_id=report.id,
                media_id=media.id,
                sha256=forensic_result.sha256,
                phash=forensic_result.phash,
                dhash=forensic_result.dhash,
                has_exif=forensic_result.has_exif,
                exif_timestamp_utc=exif_dt_parsed,
                timezone_assumed_ist=forensic_result.timezone_assumed_ist,
                time_verdict=time_verdict,
                time_difference=time_diff,
                location_verdict=gps_verdict,
                location_difference=gps_diff,
                reuse_verdict=reuse_verdict,
                matched_incident_ids=matched_ids,
                overall_verdict=forensic_result.overall_verdict.value,
                credibility_adjustment=forensic_result.credibility_adjustment,
                checks=checks_payload,
                error_reason=forensic_result.error_reason,
                is_simulated=False,
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
            db.add(finding_record)
        else:
            finding_record.sha256 = forensic_result.sha256
            finding_record.phash = forensic_result.phash
            finding_record.dhash = forensic_result.dhash
            finding_record.has_exif = forensic_result.has_exif
            finding_record.exif_timestamp_utc = exif_dt_parsed
            finding_record.timezone_assumed_ist = forensic_result.timezone_assumed_ist
            finding_record.time_verdict = time_verdict
            finding_record.time_difference = time_diff
            finding_record.location_verdict = gps_verdict
            finding_record.location_difference = gps_diff
            finding_record.reuse_verdict = reuse_verdict
            finding_record.matched_incident_ids = matched_ids
            finding_record.overall_verdict = forensic_result.overall_verdict.value
            finding_record.credibility_adjustment = forensic_result.credibility_adjustment
            finding_record.checks = checks_payload
            finding_record.error_reason = forensic_result.error_reason
            finding_record.updated_at = datetime.now(timezone.utc)

        await db.flush()
        return finding_record

    def stage_forensics_outbox_event(
        self,
        db: AsyncSession,
        report: WeatherReport,
        findings: List[IncidentImageFinding],
        overall_verdict: str,
        total_adjustment: float,
        is_simulated: bool = False,
    ) -> RealtimeOutbox:
        """Stage an outbox event for real-time frontend streaming (SSE) and worker reliability."""
        payload: Dict[str, Any] = {
            "incident_id": str(report.id),
            "tracking_id": report.tracking_id,
            "overall_verdict": overall_verdict,
            "credibility_adjustment": total_adjustment,
            "image_count": len(findings),
            "is_simulated": is_simulated,
            "images": [
                {
                    "media_id": str(f.media_id) if f.media_id else None,
                    "sha256": f.sha256,
                    "phash": f.phash,
                    "has_exif": f.has_exif,
                    "time_verdict": f.time_verdict,
                    "location_verdict": f.location_verdict,
                    "reuse_verdict": f.reuse_verdict,
                    "overall_verdict": f.overall_verdict,
                    "matched_incident_ids": f.matched_incident_ids or [],
                }
                for f in findings
            ],
        }

        outbox = RealtimeOutbox(
            event_id=uuid.uuid4(),
            event_type="incident.image_forensics_completed",
            entity_id=str(report.id),
            tracking_id=report.tracking_id,
            occurred_at=datetime.now(timezone.utc),
            payload=payload,
            status="PENDING",
            attempts=0,
            max_attempts=5,
        )
        db.add(outbox)
        return outbox

    async def run_incident_image_forensics(
        self,
        db: AsyncSession,
        report_id: uuid.UUID,
        force_run: bool = False,
        media_bytes_map: Optional[Dict[uuid.UUID, bytes]] = None,
        is_simulated: bool = False,
    ) -> IncidentForensicsSummary:
        """Execute full image forensics on all images for an incident, update credibility, and emit SSE outbox."""
        if not force_run and not getattr(settings, "IMAGE_FORENSICS_ENABLED", False):
            logger.debug("Image forensics disabled via IMAGE_FORENSICS_ENABLED.")
            return IncidentForensicsSummary(
                incident_id=str(report_id),
                images=[],
                overall_verdict=ForensicVerdict.NEUTRAL,
                total_credibility_adjustment=0.0,
            )

        # 1. Load report with media
        stmt = (
            select(WeatherReport)
            .where(WeatherReport.id == report_id)
            .options(selectinload(WeatherReport.media))
        )
        res = await db.execute(stmt)
        report = res.scalar_one_or_none()
        if not report:
            logger.warning("Report %s not found for image forensics.", report_id)
            return IncidentForensicsSummary(
                incident_id=str(report_id),
                images=[],
                overall_verdict=ForensicVerdict.NEUTRAL,
                total_credibility_adjustment=0.0,
            )

        # Filter only image media types
        image_media = [m for m in report.media if m.media_type == "IMAGE"]
        if not image_media:
            return IncidentForensicsSummary(
                incident_id=str(report_id),
                images=[],
                overall_verdict=ForensicVerdict.NEUTRAL,
                total_credibility_adjustment=0.0,
            )

        # 2. Process each image
        findings: List[IncidentImageFinding] = []
        result_items: List[ImageForensicResult] = []

        for m in image_media:
            raw_b = media_bytes_map.get(m.id) if media_bytes_map else None
            finding = await self.process_report_media(
                db=db,
                report=report,
                media=m,
                image_bytes=raw_b,
            )
            if is_simulated:
                finding.is_simulated = True
            findings.append(finding)

        # 3. Overall Verdict & Total Capped Adjustment
        has_contradict = any(f.overall_verdict == "CONTRADICTS" for f in findings)
        all_support = bool(findings) and all(f.overall_verdict == "SUPPORTS" for f in findings)

        cap = getattr(settings, "IMAGE_FORENSICS_CAP", 0.05)
        if has_contradict:
            overall_verdict_str = "CONTRADICTS"
            total_adj = -cap
        elif all_support:
            overall_verdict_str = "SUPPORTS"
            total_adj = cap
        else:
            overall_verdict_str = "NEUTRAL"
            total_adj = 0.0

        # 4. Recompute Credibility
        inputs = await credibility_collector.collect_inputs(db, report.id)
        if inputs:
            breakdown = credibility_scorer.score_incident(inputs)
            # Apply capped image adjustment if enabled
            new_credibility = round(
                max(0.0000, min(breakdown.final_credibility_score + total_adj, 0.9800)), 4
            )
            report.credibility_score = new_credibility
            # Product Rule P2: NEVER change report.verification_status!

        # 5. Stage Outbox SSE Event
        self.stage_forensics_outbox_event(
            db=db,
            report=report,
            findings=findings,
            overall_verdict=overall_verdict_str,
            total_adjustment=total_adj,
            is_simulated=is_simulated,
        )

        await db.flush()

        return IncidentForensicsSummary(
            incident_id=str(report.id),
            overall_verdict=ForensicVerdict(overall_verdict_str),
            total_credibility_adjustment=total_adj,
            simulated=is_simulated,
        )


image_forensics_service = ImageForensicsService()
