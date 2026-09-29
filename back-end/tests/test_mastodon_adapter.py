import hashlib
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import pool, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.ingestion.exceptions import AdapterFetchError, NormalizationError
from app.ingestion.mastodon_adapter import MastodonSocialAdapter
from app.ingestion.registry import adapter_registry
from app.ingestion.schemas import NormalizedEvidenceEvent
from app.models.evidence import EvidenceItem
from app.services.evidence_service import EvidenceService
from app.workers.evidence_worker import EvidenceWorker

# Sample synthetic Mastodon statuses JSON
SAMPLE_MASTODON_STATUSES = [
    {
        "id": "117171487218050079",
        "created_at": "2026-08-28T05:30:07.621Z",
        "visibility": "public",
        "url": "https://mastodon.social/@jagritsingh/117171487218050079",
        "uri": "https://mastodon.social/users/jagritsingh/statuses/117171487218050079",
        "content": (
            "<p>Heavy waterlogging near Andheri station right now, knee deep "
            '<a href="https://mastodon.social/tags/mumbairains">#<span>mumbairains</span></a> '
            '<a href="https://mastodon.social/tags/imd">#<span>imd</span></a></p>'
        ),
        "language": "en",
        "account": {
            "id": "9901",
            "username": "jagritsingh",
            "acct": "jagritsingh",
            "display_name": "Jagrit Singh",
        },
        "media_attachments": [
            {
                "id": "5501",
                "type": "image",
                "url": "https://mastodon.social/media/5501.jpg",
                "preview_url": "https://mastodon.social/media/preview_5501.jpg",
                "description": "Flooded street in Andheri",
            }
        ],
        "tags": [{"name": "mumbairains"}, {"name": "imd"}],
        "reblogs_count": 5,
        "favourites_count": 12,
    },
    {
        "id": "116955500820651144",
        "created_at": "2026-07-21T02:01:56.724Z",
        "visibility": "public",
        "url": "https://mastodon.social/@Mathrubhumi_English/116955500820651144",
        "content": (
            "<p>Heavy rain continued to lash Mumbai as IMD issued an orange alert. "
            "&amp; Thane on high alert.</p>"
        ),
        "language": "en",
        "account": {
            "id": "9902",
            "username": "Mathrubhumi_English",
            "acct": "Mathrubhumi_English",
            "display_name": "Mathrubhumi English",
        },
        "media_attachments": [],
        "tags": [{"name": "mumbairains"}, {"name": "orangealert"}],
        "reblogs_count": 2,
        "favourites_count": 4,
    },
]


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


def test_mastodon_adapter_registry_lookup():
    """Verify MASTODON_PUBLIC adapter registration in adapter registry."""
    adapter = adapter_registry.get("MASTODON_PUBLIC")
    assert adapter is not None
    assert isinstance(adapter, MastodonSocialAdapter)
    assert adapter.source_code == "MASTODON_PUBLIC"
    assert adapter.base_trust_score == 0.60


def test_mastodon_instance_and_hashtag_configuration():
    """Verify custom instance URL and hashtag list configuration."""
    custom_adapter = MastodonSocialAdapter(
        instance_url="https://mstdn.social/",
        hashtags=["chennairains", "cyclone"],
        max_results_per_tag=10,
    )
    assert custom_adapter.instance_url == "https://mstdn.social"
    assert custom_adapter.hashtags == ["chennairains", "cyclone"]
    assert custom_adapter.max_results_per_tag == 10


def test_mastodon_default_hashtags_include_imd_variants():
    """Verify default MASTODON_HASHTAGS in settings includes imd, imdweather, and imdindia."""
    from app.core.config import Settings
    fresh_settings = Settings()
    assert "imd" in fresh_settings.MASTODON_HASHTAGS
    assert "imdweather" in fresh_settings.MASTODON_HASHTAGS
    assert "imdindia" in fresh_settings.MASTODON_HASHTAGS

    adapter = MastodonSocialAdapter()
    assert "imd" in adapter.hashtags
    assert "imdweather" in adapter.hashtags
    assert "imdindia" in adapter.hashtags


def test_mastodon_html_sanitization_and_title_derivation():
    """Verify stripping of HTML tags, entity unescaping, and neutral title generation."""
    raw_html = "<p>Floods &amp; landslides hit <b>Wayanad</b> district! <a href='https://link'>#alert</a></p>"
    clean = MastodonSocialAdapter.sanitize_html(raw_html)
    assert clean == "Floods & landslides hit Wayanad district! #alert"

    # Title derivation
    short_title = MastodonSocialAdapter.derive_title(clean)
    assert short_title == "Mastodon post: Floods & landslides hit Wayanad district! #alert"

    long_text = "A" * 100
    long_title = MastodonSocialAdapter.derive_title(long_text)
    assert len(long_title) == 95
    assert long_title.endswith("...")


def test_mastodon_parse_status_field_mapping():
    """Verify complete field normalization, media preservation, and external ID generation."""
    adapter = MastodonSocialAdapter(instance_url="https://mastodon.social")
    status = SAMPLE_MASTODON_STATUSES[0]
    norm = adapter.parse_status(status)

    assert norm.source_code == "MASTODON_PUBLIC"
    assert norm.evidence_type == "SOCIAL_POST"
    assert norm.url == "https://mastodon.social/@jagritsingh/117171487218050079"
    assert norm.publisher_domain == "mastodon.social"
    assert norm.language == "en"
    assert norm.published_at == datetime(2026, 8, 28, 5, 30, 7, 621000, tzinfo=timezone.utc)
    expected_hash = hashlib.sha256(norm.url.encode("utf-8")).hexdigest()
    assert norm.sha256_hash == expected_hash
    assert norm.external_id == f"MASTODON-{expected_hash}"

    # Verify raw payload preserves tags, author, and media metadata (no download)
    assert norm.raw_payload["tags"] == ["mumbairains", "imd"]
    assert norm.raw_payload["account_handle"] == "jagritsingh"
    assert len(norm.raw_payload["media_attachments"]) == 1
    assert norm.raw_payload["media_attachments"][0]["type"] == "image"


def test_mastodon_visibility_filter():
    """Verify non-public statuses (unlisted, private, direct) are strictly rejected."""
    adapter = MastodonSocialAdapter()

    # Private status raises NormalizationError
    private_status = dict(SAMPLE_MASTODON_STATUSES[0])
    private_status["visibility"] = "private"
    with pytest.raises(NormalizationError) as exc_info:
        adapter.parse_status(private_status)
    assert "visibility" in str(exc_info.value)

    # Direct status raises NormalizationError
    direct_status = dict(SAMPLE_MASTODON_STATUSES[0])
    direct_status["visibility"] = "direct"
    with pytest.raises(NormalizationError) as exc_info:
        adapter.parse_status(direct_status)
    assert "visibility" in str(exc_info.value)


def test_mastodon_external_id_determinism_and_collision_safety():
    """Verify deterministic external IDs across duplicate and distinct post URLs."""
    adapter = MastodonSocialAdapter()
    st1 = SAMPLE_MASTODON_STATUSES[0]
    st2 = SAMPLE_MASTODON_STATUSES[1]

    norm1 = adapter.parse_status(st1)
    norm2 = adapter.parse_status(st2)

    # Distinct statuses have distinct external IDs
    assert norm1.external_id != norm2.external_id

    # Same status re-parsed has identical external ID
    norm1_repeat = adapter.parse_status(st1)
    assert norm1_repeat.external_id == norm1.external_id


@pytest.mark.asyncio
async def test_mastodon_fetch_hashtag_timeline_success():
    """Verify fetching public timeline for a hashtag."""
    mock_transport = httpx.MockTransport(
        lambda request: httpx.Response(200, json=SAMPLE_MASTODON_STATUSES)
    )
    async with httpx.AsyncClient(transport=mock_transport) as client:
        adapter = MastodonSocialAdapter(http_client=client, min_interval_seconds=0.0)
        raw_events = await adapter.fetch_hashtag_timeline("mumbairains", limit=2)

    assert len(raw_events) == 2
    assert raw_events[0].source_code == "MASTODON_PUBLIC"
    assert raw_events[0].external_id is not None
    assert raw_events[0].external_id.startswith("MASTODON-")


@pytest.mark.asyncio
async def test_mastodon_fetch_raw_events_deduplication_across_tags():
    """Verify deduplication when the same status appears under multiple hashtags."""
    mock_transport = httpx.MockTransport(
        lambda request: httpx.Response(200, json=SAMPLE_MASTODON_STATUSES)
    )
    async with httpx.AsyncClient(transport=mock_transport) as client:
        adapter = MastodonSocialAdapter(
            http_client=client,
            hashtags=["mumbairains", "flood"],  # Two tags returning the same mock statuses
            min_interval_seconds=0.0,
        )
        all_raw = await adapter.fetch_raw_events()

    # Deduplicated by external_id across tag iterations
    assert len(all_raw) == 2


@pytest.mark.asyncio
async def test_mastodon_fetch_errors_and_rate_limits():
    """Verify handling HTTP 429, 500, timeouts, and rate limit headers."""
    # HTTP 500
    mock_transport_500 = httpx.MockTransport(
        lambda request: httpx.Response(500, text="Mastodon server error")
    )
    async with httpx.AsyncClient(transport=mock_transport_500) as client:
        adapter = MastodonSocialAdapter(http_client=client, min_interval_seconds=0.0)
        with pytest.raises(AdapterFetchError) as exc_info:
            await adapter.fetch_hashtag_timeline("weather")
        assert "500" in str(exc_info.value)

    # HTTP Timeout
    async def mock_timeout(request):
        raise httpx.ConnectTimeout("Connection timed out")

    mock_transport_timeout = httpx.MockTransport(mock_timeout)
    async with httpx.AsyncClient(transport=mock_transport_timeout) as client:
        adapter = MastodonSocialAdapter(http_client=client, min_interval_seconds=0.0)
        with pytest.raises(AdapterFetchError) as exc_info:
            await adapter.fetch_hashtag_timeline("weather")
        assert "Network error" in str(exc_info.value)


@pytest.mark.asyncio
async def test_mastodon_evidence_persistence_and_idempotency(db_session: AsyncSession):
    """Verify social post persistence in PostgreSQL and idempotency on repeated ingestion."""
    ev_svc = EvidenceService()
    unique_suffix = uuid.uuid4().hex[:8]
    test_url = f"https://mastodon.social/@user/status-{unique_suffix}"
    url_hash = hashlib.sha256(test_url.encode("utf-8")).hexdigest()
    ext_id = f"MASTODON-{url_hash}"

    event = NormalizedEvidenceEvent(
        source_code="MASTODON_PUBLIC",
        external_id=ext_id,
        evidence_type="SOCIAL_POST",
        title=f"Mastodon post: Flooding in sector {unique_suffix}",
        url=test_url,
        publisher_domain="mastodon.social",
        language="English",
        published_at=datetime.now(timezone.utc),
        sha256_hash=url_hash,
        raw_payload={"status_id": unique_suffix, "tags": ["flood"]},
    )

    # 1. First ingestion -> Creates new EvidenceItem
    ev1 = await ev_svc.ingest_normalized_evidence(db_session, event)
    assert ev1.id is not None
    assert ev1.external_id == ext_id
    assert ev1.evidence_type == "SOCIAL_POST"

    # 2. Second ingestion with same external_id -> Updates existing row without duplication
    event_updated = NormalizedEvidenceEvent(
        source_code="MASTODON_PUBLIC",
        external_id=ext_id,
        evidence_type="SOCIAL_POST",
        title=f"Mastodon post: Flooding in sector {unique_suffix} (Updated)",
        url=test_url,
        publisher_domain="mastodon.social",
        language="English",
        published_at=datetime.now(timezone.utc),
        sha256_hash=url_hash,
        raw_payload={"status_id": unique_suffix, "tags": ["flood", "update"]},
    )
    ev2 = await ev_svc.ingest_normalized_evidence(db_session, event_updated)
    assert ev2.id == ev1.id
    assert "Updated" in ev2.title

    # Confirm count in database is exactly 1
    count_stmt = select(EvidenceItem).where(EvidenceItem.external_id == ext_id)
    count_res = await db_session.execute(count_stmt)
    assert len(count_res.scalars().all()) == 1


@pytest.mark.asyncio
async def test_mastodon_worker_consumption_and_ack():
    """Verify EvidenceWorker consuming and acknowledging Mastodon social posts."""
    mock_stream = MagicMock()
    mock_ev_svc = MagicMock()

    test_ev = NormalizedEvidenceEvent(
        source_code="MASTODON_PUBLIC",
        external_id="MASTODON-aabbccddeeff",
        evidence_type="SOCIAL_POST",
        title="Mastodon post: Rain update",
        url="https://mastodon.social/@user/123",
        publisher_domain="mastodon.social",
    )

    mock_stream.read_evidence = AsyncMock(return_value=[("4001-0", test_ev)])
    mock_stream.ack_evidence = AsyncMock(return_value=True)

    fake_evidence = MagicMock()
    fake_evidence.external_id = "MASTODON-aabbccddeeff"
    mock_ev_svc.ingest_normalized_evidence = AsyncMock(return_value=fake_evidence)

    worker = EvidenceWorker(
        stream_svc=mock_stream,
        ev_svc=mock_ev_svc,
        consumer_name="test-mstdn-worker",
    )

    results = await worker.process_batch(count=1)

    assert len(results) == 1
    msg_id, ev_result = results[0]
    assert msg_id == "4001-0"
    assert ev_result is fake_evidence

    mock_stream.read_evidence.assert_called_once()
    mock_ev_svc.ingest_normalized_evidence.assert_called_once()
    mock_stream.ack_evidence.assert_called_once_with("4001-0")


@pytest.mark.asyncio
async def test_mastodon_worker_recoverable_failure_no_ack():
    """Verify EvidenceWorker does NOT ack message if persistence encounters an unhandled error."""
    mock_stream = MagicMock()
    mock_ev_svc = MagicMock()

    test_ev = NormalizedEvidenceEvent(
        source_code="MASTODON_PUBLIC",
        external_id="MASTODON-FAIL-01",
        evidence_type="SOCIAL_POST",
        title="Failing Post",
        url="https://mastodon.social/@user/fail",
    )

    mock_stream.read_evidence = AsyncMock(return_value=[("4002-0", test_ev)])
    mock_stream.ack_evidence = AsyncMock(return_value=True)

    mock_ev_svc.ingest_normalized_evidence = AsyncMock(
        side_effect=RuntimeError("Database lock timeout")
    )

    worker = EvidenceWorker(
        stream_svc=mock_stream,
        ev_svc=mock_ev_svc,
        consumer_name="test-mstdn-worker",
    )

    results = await worker.process_batch(count=1)

    assert len(results) == 1
    msg_id, ev_result = results[0]
    assert msg_id == "4002-0"
    assert ev_result is None

    # CRITICAL: Message must NOT be acknowledged
    mock_stream.ack_evidence.assert_not_called()
