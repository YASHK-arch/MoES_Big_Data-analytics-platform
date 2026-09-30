import asyncio
import email.utils
import hashlib
import html
import logging
import re
import time
import urllib.robotparser
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Union
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import httpx

from app.core.config import settings
from app.ingestion.exceptions import AdapterFetchError, NormalizationError
from app.ingestion.schemas import NormalizedEvidenceEvent, RawIngestionEvent
from app.intelligence.resolver import location_resolver

logger = logging.getLogger(__name__)
RSS_SUMMARY_MAX_LENGTH = 500


class RobotsTxtChecker:
    """Polite robots.txt parser and cache for external feeds."""

    def __init__(self, user_agent: str, cache_ttl_seconds: float = 3600.0) -> None:
        self.user_agent = user_agent
        self.cache_ttl = cache_ttl_seconds
        self._parsers: Dict[str, tuple[urllib.robotparser.RobotFileParser, float]] = {}

    async def can_fetch(self, client: httpx.AsyncClient, target_url: str) -> bool:
        """Check whether fetching target_url is permitted by robots.txt."""
        try:
            parsed = urlparse(target_url)
            base_url = f"{parsed.scheme}://{parsed.netloc}"
            robots_url = f"{base_url}/robots.txt"

            now = time.monotonic()
            if base_url in self._parsers:
                parser, cached_time = self._parsers[base_url]
                if now - cached_time < self.cache_ttl:
                    return parser.can_fetch(self.user_agent, target_url)

            parser = urllib.robotparser.RobotFileParser()
            try:
                resp = await client.get(robots_url, timeout=5.0)
                if resp.status_code == 200:
                    parser.parse(resp.text.splitlines())
                else:
                    # 404 or other non-200 generally implies robots.txt not enforced
                    parser.parse(["User-agent: *", "Allow: /"])
            except Exception as e:
                logger.debug(f"robots.txt fetch failed for {base_url} ({e}); defaulting to allow.")
                parser.parse(["User-agent: *", "Allow: /"])

            self._parsers[base_url] = (parser, now)
            return parser.can_fetch(self.user_agent, target_url)
        except Exception as e:
            logger.warning(f"Error evaluating robots.txt for {target_url}: {e}")
            return True


class RSSNewsAdapter:
    """Ingestion adapter for Indian weather and disaster news RSS feeds.

    Features:
    1. Ingests configured Indian news RSS/Atom feeds (IMD, DD News, The Hindu, NDTV, etc.).
    2. URL canonicalization and SHA-256 deduplication to prevent redundant evidence.
    3. Respects robots.txt policies and enforces per-domain polite rate limiting.
    4. Extracts spatial entities (city, state, coordinates) using the gazetteer location
       resolver, ensuring strict compatibility with downstream L1 gate corroboration.
    """

    def __init__(
        self,
        feed_urls: Optional[List[str]] = None,
        min_interval_seconds: Optional[float] = None,
        timeout_seconds: Optional[float] = None,
        max_items_per_feed: Optional[int] = None,
        user_agent: Optional[str] = None,
        check_robots: Optional[bool] = None,
        http_client: Optional[httpx.AsyncClient] = None,
    ) -> None:
        self.source_code = "RSS_NEWS"
        self.source_name = "Indian Weather & Disaster News RSS"
        self.source_type = "RSS"
        self.base_trust_score = 0.70
        self.feed_urls = (
            feed_urls
            if feed_urls is not None
            else getattr(settings, "RSS_NEWS_FEEDS", [])
        )
        self.min_interval_seconds = (
            min_interval_seconds
            if min_interval_seconds is not None
            else getattr(settings, "RSS_MIN_REQUEST_INTERVAL_SECONDS", 1.0)
        )
        self.timeout_seconds = (
            timeout_seconds
            if timeout_seconds is not None
            else getattr(settings, "RSS_REQUEST_TIMEOUT_SECONDS", 15.0)
        )
        self.max_items_per_feed = (
            max_items_per_feed
            if max_items_per_feed is not None
            else getattr(settings, "RSS_MAX_ITEMS_PER_FEED", 50)
        )
        self.user_agent = (
            user_agent
            if user_agent is not None
            else getattr(settings, "RSS_USER_AGENT", "NationalWeatherPlatform-RSS/1.0")
        )
        self.check_robots = (
            check_robots
            if check_robots is not None
            else getattr(settings, "RSS_CHECK_ROBOTS_TXT", True)
        )
        self._http_client = http_client
        self._robots_checker = RobotsTxtChecker(self.user_agent)
        self._last_request_per_domain: Dict[str, float] = {}

    async def _get_client(self) -> httpx.AsyncClient:
        if self._http_client and not self._http_client.is_closed:
            return self._http_client
        return httpx.AsyncClient(
            timeout=httpx.Timeout(self.timeout_seconds),
            headers={"User-Agent": self.user_agent},
            verify=False,
            follow_redirects=True,
        )

    async def _apply_domain_rate_limit(self, domain: str) -> None:
        """Enforce per-domain rate limiting to prevent overwhelming source servers."""
        now = time.monotonic()
        last_req = self._last_request_per_domain.get(domain, 0.0)
        elapsed = now - last_req
        if elapsed < self.min_interval_seconds:
            wait_time = self.min_interval_seconds - elapsed
            logger.debug(f"Rate limiting domain '{domain}': waiting {wait_time:.2f}s")
            await asyncio.sleep(wait_time)
        self._last_request_per_domain[domain] = time.monotonic()

    @staticmethod
    def canonicalize_url(url: str) -> str:
        """Canonicalize URL by stripping tracking parameters, fragments, and trailing slashes."""
        if not url:
            return ""
        parsed = urlparse(url.strip())
        tracking_prefixes = ("utm_", "fbclid", "gclid", "ref", "ref_", "mc_", "rss")
        filtered_queries = [
            (k, v)
            for k, v in parse_qsl(parsed.query, keep_blank_values=True)
            if not any(k.lower().startswith(prefix) for prefix in tracking_prefixes)
        ]
        clean_path = parsed.path.rstrip("/") if parsed.path != "/" else "/"
        return urlunparse(
            (
                parsed.scheme.lower(),
                parsed.netloc.lower(),
                clean_path,
                parsed.params,
                urlencode(filtered_queries),
                "",  # remove fragment
            )
        )

    @staticmethod
    def clean_html(raw_html: Optional[str]) -> str:
        """Strip HTML tags and unescape HTML entities into clean text."""
        if not raw_html:
            return ""
        unescaped = html.unescape(raw_html)
        no_tags = re.sub(r"<[^>]+>", " ", unescaped)
        cleaned = re.sub(r"\s+", " ", no_tags).strip()
        return cleaned

    @staticmethod
    def parse_datetime(date_str: Optional[str]) -> Optional[datetime]:
        """Parse RFC 822/2822 (RSS) or ISO-8601 (Atom) date string to UTC datetime."""
        if not date_str:
            return None
        date_str = date_str.strip()
        # 1. Try RFC 2822 (standard RSS pubDate: 'Mon, 29 Aug 2026 10:00:00 GMT')
        try:
            parsed_tuple = email.utils.parsedate_to_datetime(date_str)
            if parsed_tuple:
                if parsed_tuple.tzinfo is None:
                    return parsed_tuple.replace(tzinfo=timezone.utc)
                return parsed_tuple.astimezone(timezone.utc)
        except Exception:
            pass

        # 2. Try ISO-8601 (standard Atom updated/published: '2026-08-29T10:00:00Z')
        try:
            iso_clean = date_str.replace("Z", "+00:00")
            dt = datetime.fromisoformat(iso_clean)
            if dt.tzinfo is None:
                return dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except Exception:
            pass

        return None

    def _strip_ns(self, tag: str) -> str:
        if "}" in tag:
            return tag.split("}", 1)[1]
        return tag

    @staticmethod
    def _find_elem(parent: ET.Element, *tag_names: str) -> Optional[ET.Element]:
        """Safely find subelement without evaluating truth value of elements."""
        for name in tag_names:
            el = parent.find(name)
            if el is not None:
                return el
            el = parent.find(f".//{{*}}{name}")
            if el is not None:
                return el
        return None

    def parse_feed_xml(
        self,
        xml_content: Union[str, bytes],
        feed_url: str,
        seen_hashes: Optional[Set[str]] = None,
    ) -> List[RawIngestionEvent]:
        """Parse XML string/bytes into deduplicated RawIngestionEvent objects."""
        if isinstance(xml_content, str):
            xml_bytes = xml_content.encode("utf-8")
        else:
            xml_bytes = xml_content

        try:
            root = ET.fromstring(xml_bytes)
        except ET.ParseError as e:
            raise AdapterFetchError(
                f"Failed to parse XML from feed '{feed_url}': {e}",
                source_code=self.source_code,
            )

        root_tag = self._strip_ns(root.tag).lower()
        items: List[ET.Element] = []

        # RSS 2.0 (<rss><channel><item>...)
        if root_tag == "rss":
            channel = self._find_elem(root, "channel")
            if channel is not None:
                found_items = channel.findall("item")
                if not found_items:
                    found_items = channel.findall(".//{*}item")
                items = found_items
            else:
                items = root.findall(".//{*}item")
        # Atom (<feed><entry>...)
        elif root_tag == "feed":
            found_entries = root.findall("entry")
            if not found_entries:
                found_entries = root.findall(".//{*}entry")
            items = found_entries
        else:
            items = root.findall(".//{*}item") or root.findall(".//{*}entry")

        raw_events: List[RawIngestionEvent] = []
        hashes = seen_hashes if seen_hashes is not None else set()

        for item in items[: self.max_items_per_feed]:
            try:
                # Extract fields
                title_elem = self._find_elem(item, "title")
                title = self.clean_html(title_elem.text if title_elem is not None else "")
                if not title:
                    continue

                # Link: in RSS it's <link>http...</link>; in Atom it's <link href="http..."/>
                link_elem = self._find_elem(item, "link")
                raw_url = ""
                if link_elem is not None:
                    raw_url = link_elem.get("href") or link_elem.text or ""
                raw_url = raw_url.strip()

                # If no link, check guid/id
                if not raw_url:
                    id_elem = self._find_elem(item, "guid", "id")
                    if id_elem is not None and (id_elem.text or "").startswith("http"):
                        raw_url = (id_elem.text or "").strip()

                if not raw_url:
                    continue

                canonical_url = self.canonicalize_url(raw_url)
                url_hash = hashlib.sha256(canonical_url.encode("utf-8")).hexdigest()

                # Deduplication check
                if url_hash in hashes:
                    logger.debug(f"Skipping duplicate RSS item with hash {url_hash[:8]}")
                    continue
                hashes.add(url_hash)

                # Description / Content / Summary
                desc_elem = self._find_elem(item, "description", "summary", "content")
                description = self.clean_html(desc_elem.text if desc_elem is not None else "")

                # Publication Date
                date_elem = self._find_elem(item, "pubDate", "published", "updated")
                raw_date = date_elem.text.strip() if date_elem is not None and date_elem.text else None

                parsed_payload = {
                    "title": title,
                    "url": canonical_url,
                    "description": description,
                    "pub_date_raw": raw_date,
                    "feed_url": feed_url,
                    "url_hash": url_hash,
                }

                raw_events.append(
                    RawIngestionEvent(
                        source_code=self.source_code,
                        external_id=f"RSS-{url_hash}",
                        payload=parsed_payload,
                    )
                )
            except Exception as e:
                logger.warning(f"Error parsing RSS item from {feed_url}: {e}")

        return raw_events

    async def fetch_raw_events(self) -> List[RawIngestionEvent]:
        """Fetch raw articles from all configured Indian weather RSS feeds."""
        all_raw_events: List[RawIngestionEvent] = []
        seen_hashes: Set[str] = set()

        client = await self._get_client()
        should_close = client != self._http_client

        try:
            for feed_url in self.feed_urls:
                domain = urlparse(feed_url).netloc.lower()

                # Check robots.txt if enabled
                if self.check_robots:
                    allowed = await self._robots_checker.can_fetch(client, feed_url)
                    if not allowed:
                        logger.warning(
                            f"robots.txt disallows scraping feed: {feed_url}. Skipping feed."
                        )
                        continue

                # Polite rate limiting per domain
                await self._apply_domain_rate_limit(domain)

                try:
                    resp = await client.get(feed_url)
                    if resp.status_code != 200:
                        logger.warning(
                            f"RSS feed '{feed_url}' returned HTTP {resp.status_code}. Skipping."
                        )
                        continue

                    feed_events = self.parse_feed_xml(resp.content, feed_url, seen_hashes)
                    all_raw_events.extend(feed_events)
                except httpx.RequestError as e:
                    logger.warning(f"Network error fetching RSS feed '{feed_url}': {e}")
                except Exception as e:
                    logger.warning(f"Unexpected error processing feed '{feed_url}': {e}")

            logger.info(f"Fetched {len(all_raw_events)} deduplicated RSS events across feeds.")
            return all_raw_events
        finally:
            if should_close:
                await client.aclose()

    def parse_article(self, payload: Dict[str, Any]) -> NormalizedEvidenceEvent:
        """Parse raw article payload into NormalizedEvidenceEvent with spatial resolution."""
        title = payload.get("title", "").strip()
        url = payload.get("url", "").strip()
        if not title:
            raise NormalizationError("Missing required 'title' in RSS article", field="title")
        if not url:
            raise NormalizationError("Missing required 'url' in RSS article", field="url")

        url_hash = payload.get("url_hash") or hashlib.sha256(url.encode("utf-8")).hexdigest()
        external_id = f"RSS-{url_hash}"

        description = payload.get("description", "").strip()
        summary = description[:RSS_SUMMARY_MAX_LENGTH]
        pub_date = self.parse_datetime(payload.get("pub_date_raw"))

        # Domain extraction
        domain = urlparse(url).netloc.lower()

        # Spatial place name resolution for L1 gate compatibility
        full_text = f"{title} {description}".strip()
        loc_res = location_resolver.resolve(text=full_text)

        resolved_location = {
            "place_name": loc_res.place_name,
            "city": loc_res.city,
            "state": loc_res.state,
            "latitude": loc_res.latitude,
            "longitude": loc_res.longitude,
            "country": loc_res.country,
            "confidence": loc_res.confidence,
        }

        raw_payload = dict(payload)
        raw_payload["description"] = summary
        raw_payload["location"] = resolved_location

        return NormalizedEvidenceEvent(
            source_code=self.source_code,
            external_id=external_id,
            evidence_type="NEWS_ARTICLE",
            title=title,
            url=url,
            publisher_domain=domain or None,
            language="English",
            published_at=pub_date,
            text_snippet=summary or None,
            sha256_hash=url_hash,
            raw_payload=raw_payload,
        )

    async def normalize(self, raw_event: RawIngestionEvent) -> NormalizedEvidenceEvent:
        """Normalize a raw RSS ingestion event into NormalizedEvidenceEvent."""
        return self.parse_article(raw_event.payload)

    async def ingest(self) -> List[NormalizedEvidenceEvent]:
        """Run full fetch, deduplication, and normalization pipeline for RSS feeds."""
        raw_events = await self.fetch_raw_events()
        normalized_evidence: List[NormalizedEvidenceEvent] = []

        for raw in raw_events:
            try:
                norm = await self.normalize(raw)
                normalized_evidence.append(norm)
            except Exception as e:
                logger.warning(f"Skipping malformed RSS article '{raw.external_id}': {e}")

        logger.info(
            f"Normalized {len(normalized_evidence)}/{len(raw_events)} RSS news evidence events"
        )
        return normalized_evidence
