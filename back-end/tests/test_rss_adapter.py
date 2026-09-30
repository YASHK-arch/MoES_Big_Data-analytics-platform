import hashlib
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from app.ingestion.registry import adapter_registry
from app.ingestion.rss_adapter import RobotsTxtChecker, RSSNewsAdapter
from app.ingestion.schemas import NormalizedEvidenceEvent
from app.intelligence.evidence_scorer import evidence_scorer
from app.intelligence.schemas import EvidenceRelationship

RSS_20_SAMPLE = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>India Weather Watch</title>
    <link>https://weather-news.in</link>
    <description>Latest weather and disaster updates across India</description>
    <item>
      <title>Heavy rains cause severe waterlogging in Puri, Odisha</title>
      <link>https://weather-news.in/odisha/heavy-rains-in-puri?utm_source=feed&amp;utm_medium=rss</link>
      <description><![CDATA[<p>Continuous downpour has submerged Grand Road and beach areas in Puri town, Odisha.</p>]]></description>
      <pubDate>Thu, 28 Aug 2026 08:30:00 GMT</pubDate>
      <guid>https://weather-news.in/odisha/heavy-rains-in-puri</guid>
    </item>
    <item>
      <title>Heavy rains cause severe waterlogging in Puri, Odisha</title>
      <link>https://weather-news.in/odisha/heavy-rains-in-puri?utm_source=twitter</link>
      <description>Duplicate article test link with different tracking params</description>
      <pubDate>Thu, 28 Aug 2026 08:30:00 GMT</pubDate>
    </item>
    <item>
      <title>Torrential monsoon rain floods streets across Kurla, Mumbai</title>
      <link>https://weather-news.in/mumbai/kurla-flooding-monsoon</link>
      <description>Arterial roads and railway tracks in Kurla and Dadar, Mumbai are submerged.</description>
      <pubDate>Thu, 28 Aug 2026 09:00:00 GMT</pubDate>
    </item>
  </channel>
</rss>
"""

ATOM_10_SAMPLE = """<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>National Disaster Bulletins</title>
  <link href="https://disaster-bulletin.in"/>
  <updated>2026-08-28T10:00:00Z</updated>
  <entry>
    <title>High alert issued for heavy rainfall across Shimla, Himachal Pradesh</title>
    <link href="https://disaster-bulletin.in/bulletins/shimla-rain-alert"/>
    <id>urn:bulletin:shimla-2026-08-28</id>
    <updated>2026-08-28T09:45:00Z</updated>
    <summary>Landslide warning and cloudburst alerts announced in Shimla hills.</summary>
  </entry>
</feed>
"""

ROBOTS_TXT_DISALLOWED = """User-agent: *
Disallow: /blocked-feed.xml
Allow: /
"""

ROBOTS_TXT_ALLOWED = """User-agent: *
Allow: /
"""


class TestRSSNewsAdapter:
    """Comprehensive test suite for Indian weather RSS news ingestion adapter."""

    def test_adapter_registry_registration(self):
        """Adapter must be registered in adapter_registry with correct priors."""
        adapter = adapter_registry.get("RSS_NEWS")
        assert adapter is not None
        assert adapter.source_code == "RSS_NEWS"
        assert adapter.source_type == "RSS"
        assert adapter.base_trust_score == 0.70

    def test_url_canonicalization_and_deduplication(self):
        """Adapter strips tracking queries and generates canonical SHA-256 hash."""
        url_1 = "https://example.com/weather/puri-rain/?utm_source=rss&utm_medium=feed#top"
        url_2 = "https://example.com/weather/puri-rain?utm_campaign=daily&fbclid=xyz123"

        canon_1 = RSSNewsAdapter.canonicalize_url(url_1)
        canon_2 = RSSNewsAdapter.canonicalize_url(url_2)

        assert canon_1 == "https://example.com/weather/puri-rain"
        assert canon_2 == "https://example.com/weather/puri-rain"

        hash_1 = hashlib.sha256(canon_1.encode("utf-8")).hexdigest()
        hash_2 = hashlib.sha256(canon_2.encode("utf-8")).hexdigest()
        assert hash_1 == hash_2

    def test_parse_rss_20_and_deduplication(self):
        """Test parsing RSS 2.0 with XML unescaping and deduplication of tracking URLs."""
        adapter = RSSNewsAdapter(feed_urls=["https://weather-news.in/feed.xml"])
        seen_hashes = set()
        events = adapter.parse_feed_xml(
            RSS_20_SAMPLE, "https://weather-news.in/feed.xml", seen_hashes
        )

        # The 2nd item is duplicate of 1st after URL canonicalization -> only 2 unique events
        assert len(events) == 2

        puri_raw = events[0]
        assert puri_raw.source_code == "RSS_NEWS"
        assert "Puri" in puri_raw.payload["title"]
        assert puri_raw.payload["url"] == "https://weather-news.in/odisha/heavy-rains-in-puri"
        assert "Grand Road" in puri_raw.payload["description"]
        assert "<p>" not in puri_raw.payload["description"]  # HTML tags cleaned

        mumbai_raw = events[1]
        assert "Kurla, Mumbai" in mumbai_raw.payload["title"]
        assert mumbai_raw.payload["url"] == "https://weather-news.in/mumbai/kurla-flooding-monsoon"

    def test_parse_atom_10(self):
        """Test parsing Atom 1.0 format with ISO-8601 timestamps."""
        adapter = RSSNewsAdapter(feed_urls=["https://disaster-bulletin.in/atom.xml"])
        events = adapter.parse_feed_xml(ATOM_10_SAMPLE, "https://disaster-bulletin.in/atom.xml")

        assert len(events) == 1
        shimla_raw = events[0]
        assert "Shimla" in shimla_raw.payload["title"]
        assert (
            shimla_raw.payload["url"] == "https://disaster-bulletin.in/bulletins/shimla-rain-alert"
        )
        assert "Landslide warning" in shimla_raw.payload["description"]

    def test_parse_article_caps_persisted_summary_and_raw_payload(self):
        adapter = RSSNewsAdapter()
        full_description = "x" * 700

        evidence = adapter.parse_article(
            {
                "title": "Heavy rain report in Puri",
                "url": "https://weather-news.in/puri-rain",
                "description": full_description,
            }
        )

        assert evidence.text_snippet is not None
        assert len(evidence.text_snippet) == 500
        assert evidence.raw_payload["description"] == evidence.text_snippet
        assert len(evidence.raw_payload["description"]) == 500

    @pytest.mark.asyncio
    async def test_robots_txt_respect(self):
        """Verify robots.txt compliance skips disallowed feed paths."""
        checker = RobotsTxtChecker("NationalWeatherPlatform-RSS/1.0")

        # Mock client to simulate robots.txt
        mock_client = AsyncMock(spec=httpx.AsyncClient)

        def mock_get(url, **kwargs):
            resp = MagicMock()
            if url.endswith("/robots.txt"):
                resp.status_code = 200
                resp.text = ROBOTS_TXT_DISALLOWED
            else:
                resp.status_code = 200
                resp.content = RSS_20_SAMPLE.encode("utf-8")
            return resp

        mock_client.get = AsyncMock(side_effect=mock_get)

        # Disallowed feed
        can_fetch_disallowed = await checker.can_fetch(
            mock_client, "https://weather-news.in/blocked-feed.xml"
        )
        assert can_fetch_disallowed is False

        # Allowed feed
        can_fetch_allowed = await checker.can_fetch(
            mock_client, "https://weather-news.in/allowed-feed.xml"
        )
        assert can_fetch_allowed is True

    @pytest.mark.asyncio
    async def test_mocked_http_ingest(self):
        """Verify full ingest() cycle using a mocked httpx client."""
        feed_url = "https://weather-news.in/feed.xml"

        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.is_closed = False

        def mock_get(url, **kwargs):
            resp = MagicMock()
            if "robots.txt" in url:
                resp.status_code = 200
                resp.text = ROBOTS_TXT_ALLOWED
            elif url == feed_url:
                resp.status_code = 200
                resp.content = RSS_20_SAMPLE.encode("utf-8")
            else:
                resp.status_code = 404
            return resp

        mock_client.get = AsyncMock(side_effect=mock_get)

        adapter = RSSNewsAdapter(
            feed_urls=[feed_url],
            min_interval_seconds=0.01,
            check_robots=True,
            http_client=mock_client,
        )

        normalized_items = await adapter.ingest()
        assert len(normalized_items) == 2

        for item in normalized_items:
            assert isinstance(item, NormalizedEvidenceEvent)
            assert item.source_code == "RSS_NEWS"
            assert item.evidence_type == "NEWS_ARTICLE"
            assert item.url is not None
            assert item.sha256_hash is not None
            assert "location" in item.raw_payload

    def test_location_resolution_and_l1_gate_compatibility(self):
        """L1 Gate Test: RSS article about Puri must NOT link to Mumbai incident."""
        adapter = RSSNewsAdapter()

        # 1. Parse article mentioning Puri, Odisha
        puri_payload = {
            "title": "Severe waterlogging reported across Puri after heavy rainfall",
            "url": "https://odishanews.in/puri-waterlogging",
            "description": "Grand Road in Puri town flooded under 2 feet of water following overnight rain.",
            "pub_date_raw": "Thu, 28 Aug 2026 08:30:00 GMT",
        }
        puri_evidence = adapter.parse_article(puri_payload)

        # Verify location resolved to city=Puri, state=Odisha
        loc = puri_evidence.raw_payload["location"]
        assert loc["city"] == "Puri"
        assert loc["state"] == "Odisha"

        # 2. Evaluate against a Mumbai incident (no coords and with coords)
        # Case A: Incident with coordinates in Mumbai (19.0760, 72.8777)
        assessment_coords = evidence_scorer.score_link(
            incident_id=uuid.uuid4(),
            evidence_id=uuid.uuid4(),
            incident_title="Severe waterlogging in Kurla, Mumbai",
            incident_desc="Heavy monsoon rain submerged railway tracks in Kurla.",
            incident_cat="FLOOD_WATERLOGGING",
            incident_lat=19.0760,
            incident_lon=72.8777,
            incident_time=datetime(2026, 8, 28, 8, 0, tzinfo=timezone.utc),
            incident_loc_name="Kurla, Mumbai, Maharashtra",
            evidence_title=puri_evidence.title,
            evidence_snippet=puri_evidence.text_snippet,
            evidence_source_type="RSS",
            evidence_pub_time=puri_evidence.published_at,
            evidence_url=puri_evidence.url,
            evidence_domain=puri_evidence.publisher_domain,
        )

        # Gate 3 (spatial > 50km) and Gate 4 (different cities: Puri vs Mumbai) must trigger IRRELEVANT
        assert assessment_coords.relationship_type == EvidenceRelationship.IRRELEVANT
        assert assessment_coords.overall_score == 0.0

        # Case B: Incident without coordinates (only name: 'Mumbai, Maharashtra')
        assessment_no_coords = evidence_scorer.score_link(
            incident_id=uuid.uuid4(),
            evidence_id=uuid.uuid4(),
            incident_title="Flooding across arterial roads in Mumbai",
            incident_desc="Severe monsoon flooding halts vehicular traffic in Mumbai.",
            incident_cat="FLOOD_WATERLOGGING",
            incident_lat=None,
            incident_lon=None,
            incident_time=datetime(2026, 8, 28, 8, 0, tzinfo=timezone.utc),
            incident_loc_name="Mumbai, Maharashtra",
            evidence_title=puri_evidence.title,
            evidence_snippet=puri_evidence.text_snippet,
            evidence_source_type="RSS",
            evidence_pub_time=puri_evidence.published_at,
            evidence_url=puri_evidence.url,
            evidence_domain=puri_evidence.publisher_domain,
        )

        # Gate 4 (different cities) and Gate 4b (different states) must trigger IRRELEVANT
        assert assessment_no_coords.relationship_type == EvidenceRelationship.IRRELEVANT
        assert assessment_no_coords.overall_score == 0.0
        assert (
            "different city" in assessment_no_coords.explanation
            or "different state" in assessment_no_coords.explanation
        )

    def test_positive_corroboration_same_city(self):
        """Positive Test: RSS article about Mumbai links to Mumbai incident."""
        adapter = RSSNewsAdapter()

        mumbai_payload = {
            "title": "Severe waterlogging halts suburban trains in Kurla, Mumbai",
            "url": "https://mumbainews.in/kurla-trains-halted",
            "description": "Continuous torrential rains in Mumbai submerge tracks at Kurla station.",
            "pub_date_raw": "Thu, 28 Aug 2026 08:30:00 GMT",
        }
        mumbai_evidence = adapter.parse_article(mumbai_payload)

        assessment = evidence_scorer.score_link(
            incident_id=uuid.uuid4(),
            evidence_id=uuid.uuid4(),
            incident_title="Severe waterlogging in Kurla, Mumbai",
            incident_desc="Heavy monsoon rain submerged railway tracks in Kurla.",
            incident_cat="FLOOD_WATERLOGGING",
            incident_lat=19.0760,
            incident_lon=72.8777,
            incident_time=datetime(2026, 8, 28, 8, 0, tzinfo=timezone.utc),
            incident_loc_name="Kurla, Mumbai, Maharashtra",
            evidence_title=mumbai_evidence.title,
            evidence_snippet=mumbai_evidence.text_snippet,
            evidence_source_type="RSS",
            evidence_pub_time=mumbai_evidence.published_at,
            evidence_url=mumbai_evidence.url,
            evidence_domain=mumbai_evidence.publisher_domain,
        )

        assert assessment.relationship_type in (
            EvidenceRelationship.SUPPORTING,
            EvidenceRelationship.RELATED,
        )
        assert assessment.overall_score > 0.50
