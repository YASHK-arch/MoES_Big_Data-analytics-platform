"""Analyze the saved K1 RSS snapshot against the AUDIT database only."""

import asyncio
import json
import os
import sys
import uuid
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = REPO_ROOT / "back-end"
sys.path.insert(0, str(BACKEND_ROOT))

def parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def is_location_gate_failure(explanation: str) -> bool:
    return explanation.startswith(
        (
            "Evidence refers to foreign territory",
            "Distance (",
            "Evidence is in a different city",
            "Evidence is in a different state",
            "Neither incident nor evidence has coordinates",
        )
    )


async def main() -> None:
    from app.ingestion.schemas import NormalizedEvidenceEvent
    from app.intelligence.evidence_candidate_generator import evidence_candidate_generator
    from app.intelligence.evidence_scorer import EvidenceRelationship, evidence_scorer
    from app.intelligence.gazetteer import INDIAN_CITIES
    from app.intelligence.resolver import location_resolver
    from app.models.evidence import EvidenceItem

    database_url = os.environ.get("DATABASE_URL", "")
    database_name = urlparse(database_url).path.lstrip("/")
    if database_name != "weather_platform_audit":
        raise RuntimeError(f"BLOCKED: expected weather_platform_audit, got {database_name or 'no database'}")
    snapshot_path = REPO_ROOT / "audit" / "rss_snapshot_k1.json"
    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    unresolved_places: Counter[str] = Counter()
    for feed in snapshot["feeds"]:
        for item in feed["normalized_items"]:
            location = item.get("raw_payload", {}).get("location", {})
            if location.get("city") or location.get("state"):
                continue
            if location.get("place_name"):
                unresolved_places[location["place_name"]] += 1
            for candidate in item.get("resolver_candidates", []):
                if candidate.get("place_name"):
                    unresolved_places[candidate["place_name"]] += 1
    print("TOP10_UNRESOLVED_PLACE_CANDIDATES", unresolved_places.most_common(10))

    engine = create_async_engine(database_url, pool_pre_ping=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    candidate_count = 0
    linked_count = 0
    gate_fail_count = 0
    try:
        async with session_factory() as session:
            for feed in snapshot["feeds"]:
                for item in feed["normalized_items"]:
                    event = NormalizedEvidenceEvent.model_validate(item)
                    evidence_id = uuid.uuid5(uuid.NAMESPACE_URL, event.url or event.external_id)
                    evidence = EvidenceItem(
                        id=evidence_id,
                        source_id=uuid.UUID(int=0),
                        external_id=event.external_id,
                        evidence_type=event.evidence_type,
                        title=event.title,
                        url=event.url,
                        publisher_domain=event.publisher_domain,
                        published_at=event.published_at,
                        captured_at=datetime.now(timezone.utc),
                        text_snippet=event.text_snippet,
                    )
                    candidates, truncated = await evidence_candidate_generator.get_incident_candidates_for_evidence(
                        session, evidence
                    )
                    candidate_count += len(candidates)
                    evi_location = item.get("raw_payload", {}).get("location", {})
                    for report in candidates:
                        report_location = location_resolver.resolve(
                            text=f"{report.location_name or ''} {report.title}",
                            location_name=report.location_name,
                        )
                        incident_city = report_location.city
                        incident_state = report_location.state
                        if report.latitude is not None and report.longitude is not None:
                            for city_data in INDIAN_CITIES.values():
                                if "lat" not in city_data or "lon" not in city_data:
                                    continue
                                distance = evidence_scorer.haversine_distance_meters(
                                    report.latitude,
                                    report.longitude,
                                    city_data["lat"],
                                    city_data["lon"],
                                )
                                if distance <= 50000.0:
                                    incident_city = incident_city or city_data.get("city")
                                    incident_state = incident_state or city_data.get("state")
                                    break
                        assessment = evidence_scorer.score_link(
                            incident_id=report.id,
                            evidence_id=evidence_id,
                            incident_title=report.title,
                            incident_desc=report.description,
                            incident_cat=report.reported_category or "OTHER",
                            incident_lat=report.latitude,
                            incident_lon=report.longitude,
                            incident_time=report.occurred_at,
                            incident_loc_name=report.location_name,
                            evidence_title=event.title,
                            evidence_snippet=event.text_snippet,
                            evidence_source_type="RSS",
                            evidence_pub_time=event.published_at or evidence.captured_at,
                            evidence_url=event.url,
                            evidence_domain=event.publisher_domain,
                        )
                        linked = assessment.relationship_type != EvidenceRelationship.IRRELEVANT
                        gate_fail = is_location_gate_failure(assessment.explanation)
                        if linked:
                            linked_count += 1
                        if gate_fail:
                            gate_fail_count += 1
                        if linked or gate_fail:
                            print(
                                "LINK_CHECK "
                                + json.dumps(
                                    {
                                        "title": event.title,
                                        "evidence_state": evi_location.get("state"),
                                        "evidence_city": evi_location.get("city"),
                                        "incident_id": str(report.id),
                                        "incident_state": incident_state,
                                        "incident_city": incident_city,
                                        "distance_meters": assessment.signals.spatial_distance_meters,
                                        "location_gate": "FAIL" if gate_fail else "PASS",
                                        "linked": linked,
                                        "relationship": assessment.relationship_type.value,
                                        "score": assessment.overall_score,
                                        "reason": assessment.explanation,
                                        "candidate_query_truncated": truncated,
                                    },
                                    ensure_ascii=False,
                                    sort_keys=True,
                                )
                            )
        print(f"AUDIT_DB={database_name} CANDIDATES={candidate_count} LINKED={linked_count} LOCATION_GATE_FAILS={gate_fail_count}")
        if not linked_count:
            print("LINK_RESULT=none: no candidate passed the production link policy")
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
