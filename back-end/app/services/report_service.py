import logging
import math
import secrets
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from fastapi import UploadFile
from geoalchemy2.elements import WKTElement
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload

from app.core.config import settings
from app.ingestion.schemas import NormalizedIngestionEvent
from app.models.category import EventCategory
from app.models.forecast import ForecastAdvisory
from app.models.media import ReportMedia
from app.models.report import WeatherReport
from app.models.source import Source
from app.models.user import User
from app.models.verification import VerificationEvent
from app.schemas.report import CitizenReportCreate
from app.services.realtime_service import RealtimeService, realtime_service
from app.services.storage import StorageService, storage_service

logger = logging.getLogger(__name__)

REPORT_COUNT_CACHE_TTL_SECONDS: float = 30.0
_UNFILTERED_COUNT_CACHE: Dict[str, float] = {"count": 0, "expires_at": 0.0}


class InvalidStateTransitionError(Exception):
    """Raised when an invalid verification status transition is attempted."""

    def __init__(
        self,
        current_status: str,
        target_status: str,
        message: Optional[str] = None,
    ) -> None:
        self.current_status = current_status
        self.target_status = target_status
        self.message = message or (
            f"Invalid verification state transition from '{current_status}' to '{target_status}'."
        )
        super().__init__(self.message)


ALLOWED_VERIFICATION_TRANSITIONS: Dict[str, set[str]] = {
    "PENDING": {"UNDER_REVIEW", "VERIFIED", "REJECTED", "DUPLICATE"},
    "UNDER_REVIEW": {"VERIFIED", "REJECTED", "DUPLICATE"},
    "VERIFIED": set(),
    "REJECTED": set(),
    "DUPLICATE": set(),
}


class ReportService:
    """Business logic service for citizen weather reports."""

    def __init__(
        self,
        storage: Optional[StorageService] = None,
        realtime_svc: Optional[RealtimeService] = None,
    ) -> None:
        self.storage = storage or storage_service
        self.realtime_svc = realtime_svc or realtime_service

    @staticmethod
    def _parse_ndma_end_time(raw_value: Any) -> Optional[datetime]:
        """Parse the NDMA CAP effective end time, including its published IST format."""
        if not raw_value:
            return None
        raw_text = str(raw_value).strip()
        for fmt, tz in (
            ("%a %b %d %H:%M:%S IST %Y", timezone(timedelta(hours=5, minutes=30))),
            ("%Y-%m-%dT%H:%M:%S%z", timezone.utc),
            ("%Y-%m-%dT%H:%M:%SZ", timezone.utc),
        ):
            try:
                parsed = datetime.strptime(raw_text, fmt)
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=tz)
                return parsed.astimezone(timezone.utc)
            except ValueError:
                continue
        return None

    async def _maybe_create_ndma_forecast(
        self,
        session: AsyncSession,
        event: NormalizedIngestionEvent,
    ) -> None:
        """Persist NDMA CAP warnings with an explicit validity end as forecast advisories."""
        if event.source_code != "NDMA_SACHET":
            return

        raw_record = event.raw_payload.get("ndma_raw_record")
        if not isinstance(raw_record, dict) or not raw_record.get("effective_end_time"):
            return

        valid_until = self._parse_ndma_end_time(raw_record["effective_end_time"])
        if valid_until is None:
            return

        existing = await session.scalar(
            select(ForecastAdvisory).where(
                ForecastAdvisory.source_code == event.source_code,
                ForecastAdvisory.advisory_title == event.title,
                ForecastAdvisory.valid_until == valid_until,
            )
        )
        if existing:
            existing.raw_payload = event.raw_payload
            return

        session.add(
            ForecastAdvisory(
                source_code=event.source_code,
                hazard_type=event.category_code or "OTHER",
                severity=event.severity,
                advisory_title=event.title,
                advisory_text=event.description,
                geom=WKTElement(f"POINT({event.longitude} {event.latitude})", srid=4326),
                valid_from=event.occurred_at,
                valid_until=valid_until,
                issued_at=event.ingested_at,
                raw_payload=event.raw_payload,
            )
        )

    @staticmethod
    def generate_tracking_id() -> str:
        """Generate human-readable and safe tracking identifier.

        Format: RPT-YYYYMMDD-XXXXXXXX (e.g., RPT-20260829-B4F8E29A)
        """
        date_str = datetime.now(timezone.utc).strftime("%Y%m%d")
        random_suffix = secrets.token_hex(4).upper()
        return f"RPT-{date_str}-{random_suffix}"

    async def get_or_create_citizen_source(self, session: AsyncSession) -> Source:
        """Ensure standard CITIZEN_WEB data source exists in the database."""
        stmt = select(Source).where(Source.source_code == "CITIZEN_WEB")
        result = await session.execute(stmt)
        source = result.scalar_one_or_none()

        if source is None:
            source = Source(
                source_code="CITIZEN_WEB",
                name="Citizen Web Portal",
                source_type="CITIZEN_REPORT",
                base_trust_score=0.6,
                is_active=True,
            )
            session.add(source)
            await session.flush()

        return source

    async def resolve_category(
        self, session: AsyncSession, category_code: str
    ) -> Tuple[Optional[uuid.UUID], Optional[str]]:
        """Resolve category UUID and reported category title."""
        alias_map = {
            "CYCLONE_GALE": "CYCLONE_STORM",
            "EXTREME_HEAT": "HEATWAVE",
        }
        clean_code = category_code.upper().strip()
        canonical_code = alias_map.get(clean_code, clean_code)
        stmt = select(EventCategory).where(EventCategory.category_code == canonical_code)
        result = await session.execute(stmt)
        category = result.scalar_one_or_none()

        if category is not None:
            return category.id, category.title
        if canonical_code != clean_code:
            stmt = select(EventCategory).where(EventCategory.category_code == clean_code)
            result = await session.execute(stmt)
            category = result.scalar_one_or_none()
            if category is not None:
                return category.id, category.title
        return None, category_code

    async def create_citizen_report(
        self,
        session: AsyncSession,
        payload: CitizenReportCreate,
        media_files: Optional[List[UploadFile]] = None,
        user_id: Optional[uuid.UUID] = None,
    ) -> Tuple[WeatherReport, int]:
        """Process and persist a citizen weather report with optional media uploads and user linking."""
        uploaded_keys: List[str] = []
        report_id = uuid.uuid4()
        tracking_id = self.generate_tracking_id()

        try:
            # 1. Resolve source and category
            source = await self.get_or_create_citizen_source(session)
            category_id, reported_category = await self.resolve_category(
                session, payload.category_code
            )

            # 2. Upload media files if present
            media_records: List[ReportMedia] = []
            if media_files:
                if len(media_files) > 3:
                    raise ValueError("Maximum of 3 media files can be attached per report")

                for upload_file in media_files:
                    if upload_file.filename:
                        content_type = upload_file.content_type or "application/octet-stream"
                        file_bytes = await upload_file.read()

                        if len(file_bytes) == 0:
                            continue

                        (
                            storage_key,
                            sha256_hash,
                            file_size,
                            media_type,
                        ) = self.storage.upload_media_file(
                            file_bytes=file_bytes,
                            filename=upload_file.filename,
                            content_type=content_type,
                            bucket_name=settings.S3_BUCKET_NAME,
                            report_id=report_id,
                        )
                        uploaded_keys.append(storage_key)

                        media = ReportMedia(
                            id=uuid.uuid4(),
                            report_id=report_id,
                            media_type=media_type,
                            storage_bucket=settings.S3_BUCKET_NAME,
                            storage_key=storage_key,
                            mime_type=content_type,
                            file_size_bytes=file_size,
                            sha256_hash=sha256_hash,
                        )
                        media_records.append(media)

            # 3. Create WeatherReport entity with geometry
            geom = WKTElement(f"POINT({payload.longitude} {payload.latitude})", srid=4326)
            occurred_time = payload.occurred_at or datetime.now(timezone.utc)

            # 4. Instantiate WeatherReport entity
            report = WeatherReport(
                id=report_id,
                tracking_id=tracking_id,
                source_id=source.id,
                user_id=user_id,
                category_id=category_id,
                reported_category=reported_category,
                severity=payload.severity,
                title=payload.title,
                description=payload.description,
                location_name=payload.location_name,
                geom=geom,
                latitude=payload.latitude,
                longitude=payload.longitude,
                occurred_at=occurred_time,
                processing_status="QUEUED",
                verification_status="PENDING",
                credibility_score=0.0,
            )

            session.add(report)
            for media in media_records:
                session.add(media)

            # Stage outbox row inside the atomic database transaction
            outbox_row = self.realtime_svc.stage_report_created(
                session=session,
                report=report,
                category_code=payload.category_code,
                has_media=len(media_records) > 0,
            )

            # Stage independent orchestration trigger in the same atomic transaction
            orch_outbox_row = self.realtime_svc.stage_orchestration_trigger(
                session=session,
                report=report,
            )

            await session.commit()
            await session.refresh(report)
            _UNFILTERED_COUNT_CACHE["expires_at"] = 0.0

            # Fast-path publish to Redis Stream (worker retries if this fails or network blips)
            await self.realtime_svc.publish_staged_outbox(outbox_row)
            await self.realtime_svc.publish_staged_outbox(orch_outbox_row)

            # Fast-path immediate intelligence pipeline execution (location, duplicate, evidence, observation, credibility)
            try:
                from app.orchestration.incident_pipeline import incident_pipeline

                await incident_pipeline.execute_pipeline(db=session, incident_id=report.id, commit=True)
                await session.refresh(report)
            except Exception as pipe_err:
                logger.warning(
                    "Inline intelligence pipeline execution deferred to worker: %s", pipe_err
                )

            return report, len(media_records)

        except Exception:
            await session.rollback()
            # Clean up uploaded media in storage if database commit fails
            for key in uploaded_keys:
                self.storage.delete_media_file(key, bucket_name=settings.S3_BUCKET_NAME)
            raise

    async def get_report_by_id_or_tracking(
        self, session: AsyncSession, identifier: str
    ) -> Optional[WeatherReport]:
        """Fetch a single report by tracking ID or UUID primary key."""
        clean_id = identifier.strip()
        if not clean_id:
            return None

        # Check if identifier can be parsed as a UUID
        parsed_uuid: Optional[uuid.UUID] = None
        try:
            parsed_uuid = uuid.UUID(clean_id)
        except ValueError:
            parsed_uuid = None

        stmt = select(WeatherReport).options(
            selectinload(WeatherReport.category),
            selectinload(WeatherReport.media),
            selectinload(WeatherReport.verification_events),
        )

        if parsed_uuid is not None:
            stmt = stmt.where(
                or_(
                    WeatherReport.id == parsed_uuid,
                    WeatherReport.tracking_id == clean_id,
                )
            )
        else:
            stmt = stmt.where(WeatherReport.tracking_id == clean_id)

        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_reports(
        self,
        session: AsyncSession,
        page: int = 1,
        page_size: int = 20,
        category: Optional[str] = None,
        severity: Optional[str] = None,
        status: Optional[str] = None,
        from_date: Optional[datetime] = None,
        to_date: Optional[datetime] = None,
        min_credibility: Optional[float] = None,
        bbox: Optional[Tuple[float, float, float, float]] = None,
    ) -> Tuple[List[WeatherReport], int, int, bool, bool]:
        """Query and filter weather reports with PostGIS spatial bounds and pagination."""
        stmt = select(WeatherReport).options(
            joinedload(WeatherReport.category),
            selectinload(WeatherReport.media),
            selectinload(WeatherReport.verification_events),
        )
        count_stmt = select(func.count(WeatherReport.id))

        filters = []

        if category:
            clean_cat = category.strip().upper()
            stmt = stmt.outerjoin(WeatherReport.category)
            count_stmt = count_stmt.outerjoin(WeatherReport.category)
            filters.append(
                or_(
                    EventCategory.category_code == clean_cat,
                    WeatherReport.reported_category.ilike(f"%{clean_cat}%"),
                )
            )

        if severity:
            clean_sev = severity.strip().upper()
            filters.append(WeatherReport.severity == clean_sev)

        if status:
            statuses = [s.strip().upper() for s in status.split(",") if s.strip()]
            if len(statuses) == 1:
                filters.append(WeatherReport.verification_status == statuses[0])
            elif len(statuses) > 1:
                filters.append(WeatherReport.verification_status.in_(statuses))

        if from_date:
            filters.append(WeatherReport.occurred_at >= from_date)

        if to_date:
            filters.append(WeatherReport.occurred_at <= to_date)

        if min_credibility is not None:
            filters.append(WeatherReport.credibility_score >= min_credibility)

        if bbox is not None:
            min_lon, min_lat, max_lon, max_lat = bbox
            envelope = func.ST_MakeEnvelope(min_lon, min_lat, max_lon, max_lat, 4326)
            filters.append(func.ST_Within(WeatherReport.geom, envelope))

        if filters:
            for f in filters:
                stmt = stmt.where(f)
                count_stmt = count_stmt.where(f)

        # 1. Total records count
        if not filters:
            now_mono = time.monotonic()
            if _UNFILTERED_COUNT_CACHE["expires_at"] > now_mono and _UNFILTERED_COUNT_CACHE["count"] > 0:
                total_records = int(_UNFILTERED_COUNT_CACHE["count"])
            else:
                count_res = await session.execute(count_stmt)
                total_records = count_res.scalar() or 0
                _UNFILTERED_COUNT_CACHE["count"] = total_records
                _UNFILTERED_COUNT_CACHE["expires_at"] = now_mono + REPORT_COUNT_CACHE_TTL_SECONDS
        else:
            count_res = await session.execute(count_stmt)
            total_records = count_res.scalar() or 0

        # 2. Paginated data query
        stmt = stmt.order_by(WeatherReport.occurred_at.desc(), WeatherReport.created_at.desc())
        stmt = stmt.offset((page - 1) * page_size).limit(page_size)

        result = await session.execute(stmt)
        reports = list(result.scalars().all())

        # 3. Calculate pagination metadata
        total_pages = max(1, math.ceil(total_records / page_size)) if total_records > 0 else 1
        has_next = page < total_pages
        has_prev = page > 1

        return reports, total_records, total_pages, has_next, has_prev

    async def get_or_create_default_reviewer(self, session: AsyncSession) -> User:
        """Ensure standard Authorized Reviewer user exists for verification audit logging."""
        stmt = select(User).where(User.email == "officer@deoc.gov.in")
        result = await session.execute(stmt)
        user = result.scalar_one_or_none()

        if user is None:
            user = User(
                email="officer@deoc.gov.in",
                full_name="Authorized Reviewer",
                hashed_password="not_used_in_mvp",
                role="DEOC_OFFICER",
                is_active=True,
            )
            session.add(user)
            await session.flush()

        return user

    async def update_verification_status(
        self,
        session: AsyncSession,
        report_id_or_tracking: str,
        new_status: str,
        notes: Optional[str] = None,
        action_metadata: Optional[Dict[str, Any]] = None,
    ) -> WeatherReport:
        """Update report verification status and record persistent VerificationEvent audit trail."""
        report = await self.get_report_by_id_or_tracking(session, report_id_or_tracking)
        if report is None:
            raise ValueError(f"Report not found: {report_id_or_tracking}")

        previous_status = (report.verification_status or "PENDING").upper()
        clean_status = new_status.strip().upper()

        allowed_targets = ALLOWED_VERIFICATION_TRANSITIONS.get(previous_status, set())
        if clean_status not in allowed_targets:
            if not allowed_targets:
                msg = (
                    f"Cannot transition report from terminal state '{previous_status}' "
                    f"to '{clean_status}'. Terminal verification states "
                    "(VERIFIED, REJECTED, DUPLICATE) cannot be modified."
                )
            else:
                targets_str = ", ".join(sorted(allowed_targets))
                msg = (
                    f"Cannot transition report from '{previous_status}' to '{clean_status}'. "
                    f"Allowed transitions from '{previous_status}' are: {targets_str}."
                )
            raise InvalidStateTransitionError(
                current_status=previous_status,
                target_status=clean_status,
                message=msg,
            )

        report.verification_status = clean_status

        if clean_status == "VERIFIED":
            report.processing_status = "COMPLETED"
        elif clean_status in ("REJECTED", "DUPLICATE"):
            report.processing_status = "CLOSED"
        elif clean_status == "UNDER_REVIEW":
            report.processing_status = "IN_PROGRESS"

        reviewer = await self.get_or_create_default_reviewer(session)

        verification_event = VerificationEvent(
            report_id=report.id,
            user_id=reviewer.id,
            previous_status=previous_status,
            new_status=clean_status,
            notes=notes,
            action_metadata=action_metadata,
        )
        session.add(verification_event)

        # Stage outbox row inside the atomic database transaction
        outbox_row = self.realtime_svc.stage_verification_changed(
            session=session,
            report=report,
            previous_status=previous_status,
            new_status=clean_status,
            category_code=report.reported_category,
        )

        await session.commit()

        # Re-query with populate_existing=True to eagerly load verification_events
        stmt = (
            select(WeatherReport)
            .where(WeatherReport.id == report.id)
            .options(
                selectinload(WeatherReport.category),
                selectinload(WeatherReport.media),
                selectinload(WeatherReport.verification_events),
            )
            .execution_options(populate_existing=True)
        )
        res = await session.execute(stmt)
        refreshed = res.scalar_one_or_none()
        final_report = refreshed or report

        # Fast-path publish to Redis Stream (worker retries if this fails or network blips)
        await self.realtime_svc.publish_staged_outbox(outbox_row)

        return final_report

    async def get_or_create_source(
        self,
        session: AsyncSession,
        source_code: str,
        name: Optional[str] = None,
        source_type: str = "EXTERNAL_FEED",
        base_trust_score: Optional[float] = None,
    ) -> Source:
        """Ensure a source catalog record exists by source_code."""
        clean_code = source_code.strip().upper()
        stmt = select(Source).where(Source.source_code == clean_code)
        result = await session.execute(stmt)
        source = result.scalar_one_or_none()

        if source is not None:
            if base_trust_score is not None:
                source.base_trust_score = base_trust_score
            else:
                from app.ingestion.registry import adapter_registry

                registered = adapter_registry.get(clean_code)
                if registered:
                    source.base_trust_score = registered.base_trust_score
            return source

        resolved_trust = base_trust_score
        resolved_name = name
        resolved_type = source_type

        from app.ingestion.registry import adapter_registry

        registered = adapter_registry.get(clean_code)
        if registered:
            if resolved_trust is None:
                resolved_trust = registered.base_trust_score
            if not resolved_name:
                resolved_name = registered.source_name
            resolved_type = registered.source_type

        source = Source(
            source_code=clean_code,
            name=resolved_name or f"Data Source {clean_code}",
            source_type=resolved_type,
            base_trust_score=resolved_trust if resolved_trust is not None else 0.5,
            is_active=True,
        )
        session.add(source)
        await session.flush()

        return source

    async def ingest_normalized_event(
        self,
        session: AsyncSession,
        event: NormalizedIngestionEvent,
    ) -> WeatherReport:
        """Persist a normalized ingestion event into the database with idempotency guarantees."""
        source = await self.get_or_create_source(
            session=session,
            source_code=event.source_code,
            name=f"Ingestion Source {event.source_code}",
        )

        # Idempotency check: look for existing report from same source with same external_id
        if event.external_id:
            stmt = (
                select(WeatherReport)
                .where(
                    WeatherReport.source_id == source.id,
                    WeatherReport.external_id == event.external_id,
                )
                .options(
                    selectinload(WeatherReport.category),
                    selectinload(WeatherReport.media),
                )
            )
            res = await session.execute(stmt)
            existing_report = res.scalar_one_or_none()
            if existing_report is not None:
                # Update existing record payload if new metadata arrived
                existing_report.raw_payload = event.raw_payload
                existing_report.updated_at = datetime.now(timezone.utc)
                await session.commit()
                return existing_report

        category_id, reported_cat = await self.resolve_category(
            session, event.category_code or "OTHER"
        )
        report_id = uuid.uuid4()
        tracking_id = self.generate_tracking_id()
        point_geom = WKTElement(f"POINT({event.longitude} {event.latitude})", srid=4326)

        report = WeatherReport(
            id=report_id,
            tracking_id=tracking_id,
            source_id=source.id,
            external_id=event.external_id,
            category_id=category_id,
            reported_category=reported_cat,
            severity=event.severity,
            title=event.title,
            description=event.description,
            location_name=event.location_name,
            geom=point_geom,
            latitude=event.latitude,
            longitude=event.longitude,
            occurred_at=event.occurred_at,
            processing_status="QUEUED",
            verification_status="PENDING",
            credibility_score=0.0,
            raw_payload=event.raw_payload,
        )
        session.add(report)
        await self._maybe_create_ndma_forecast(session, event)

        # Stage outbox row inside the atomic database transaction
        outbox_row = self.realtime_svc.stage_report_created(
            session=session,
            report=report,
            category_code=reported_cat,
            has_media=False,
        )

        orch_outbox_row = self.realtime_svc.stage_orchestration_trigger(
            session=session,
            report=report,
        )

        await session.commit()

        stmt = (
            select(WeatherReport)
            .where(WeatherReport.id == report.id)
            .options(
                selectinload(WeatherReport.category),
                selectinload(WeatherReport.media),
            )
        )
        res = await session.execute(stmt)
        persisted = res.scalar_one()

        # Fast-path publish to Redis Stream
        await self.realtime_svc.publish_staged_outbox(outbox_row)
        await self.realtime_svc.publish_staged_outbox(orch_outbox_row)

        return persisted


report_service = ReportService()
