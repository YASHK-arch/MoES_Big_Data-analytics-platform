"""Fetch each configured RSS feed once and save an auditable K1 snapshot."""

from __future__ import annotations

import asyncio
import hashlib
import json
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import httpx

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = REPO_ROOT / "back-end"
sys.path.insert(0, str(BACKEND_ROOT))


def item_elements(root: ET.Element) -> list[ET.Element]:
    items = root.findall(".//{*}item")
    return items or root.findall(".//{*}entry")


def read_item(adapter, item: ET.Element, feed_url: str) -> dict[str, str]:
    title_elem = adapter._find_elem(item, "title")
    title = adapter.clean_html(title_elem.text if title_elem is not None else "")
    link_elem = adapter._find_elem(item, "link")
    url = ""
    if link_elem is not None:
        url = (link_elem.get("href") or link_elem.text or "").strip()
    if not url:
        id_elem = adapter._find_elem(item, "guid", "id")
        if id_elem is not None and (id_elem.text or "").startswith("http"):
            url = (id_elem.text or "").strip()
    description_elem = adapter._find_elem(item, "description", "summary", "content")
    description = adapter.clean_html(description_elem.text if description_elem is not None else "")
    date_elem = adapter._find_elem(item, "pubDate", "published", "updated")
    pub_date = date_elem.text.strip() if date_elem is not None and date_elem.text else ""
    return {
        "title": title,
        "url": adapter.canonicalize_url(url) if url else "",
        "description": description,
        "pub_date_raw": pub_date,
        "feed_url": feed_url,
    }


async def main() -> None:
    from app.core.config import settings
    from app.ingestion.rss_adapter import RSSNewsAdapter
    from app.intelligence.resolver import location_resolver

    adapter = RSSNewsAdapter()
    seen_hashes: set[str] = set()
    snapshot = {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "configured_feeds": list(settings.RSS_NEWS_FEEDS),
        "max_items_per_feed": adapter.max_items_per_feed,
        "feeds": [],
    }
    client = httpx.AsyncClient(
        timeout=httpx.Timeout(adapter.timeout_seconds),
        headers={"User-Agent": adapter.user_agent},
        verify=False,
        follow_redirects=True,
    )
    try:
        for feed_url in settings.RSS_NEWS_FEEDS:
            feed = {
                "configured_url": feed_url,
                "robots_allowed": False,
                "http_status": None,
                "final_url": None,
                "entries": 0,
                "cap_rejected": 0,
                "missing_title_rejected": 0,
                "missing_url_rejected": 0,
                "duplicate_rejected": 0,
                "fetched": 0,
                "normalized": 0,
                "normalization_rejected": 0,
                "error": None,
                "response_excerpt": None,
                "raw_items": [],
                "normalized_items": [],
            }
            snapshot["feeds"].append(feed)
            domain = urlparse(feed_url).netloc.lower()
            try:
                feed["robots_allowed"] = await adapter._robots_checker.can_fetch(client, feed_url)
                if not feed["robots_allowed"]:
                    feed["error"] = "robots.txt denied feed request; feed GET not sent"
                    print(f"FEED {feed_url} robots=DENY http=NOT_REQUESTED")
                    continue
                await adapter._apply_domain_rate_limit(domain)
                response = await client.get(feed_url)
                feed["http_status"] = response.status_code
                feed["final_url"] = str(response.url)
                if response.status_code != 200:
                    feed["response_excerpt"] = response.text[:1000]
                    print(
                        f"FEED {feed_url} robots=ALLOW http={response.status_code} "
                        f"final_url={response.url} response={response.text[:500]!r}"
                    )
                    continue

                root = ET.fromstring(response.content)
                entries = item_elements(root)
                feed["entries"] = len(entries)
                feed["cap_rejected"] = max(0, len(entries) - adapter.max_items_per_feed)
                eligible = entries[: adapter.max_items_per_feed]
                hashes_before = set(seen_hashes)
                raw_events = adapter.parse_feed_xml(response.content, feed_url, seen_hashes)
                feed["fetched"] = len(raw_events)
                local_hashes = set(hashes_before)
                for entry in eligible:
                    raw_item = read_item(adapter, entry, feed_url)
                    feed["raw_items"].append(raw_item)
                    if not raw_item["title"]:
                        feed["missing_title_rejected"] += 1
                        continue
                    if not raw_item["url"]:
                        feed["missing_url_rejected"] += 1
                        continue
                    digest = hashlib.sha256(raw_item["url"].encode("utf-8")).hexdigest()
                    if digest in local_hashes:
                        feed["duplicate_rejected"] += 1
                    else:
                        local_hashes.add(digest)
                for raw_event in raw_events:
                    try:
                        normalized = adapter.parse_article(raw_event.payload)
                        row = normalized.model_dump(mode="json")
                        resolution = location_resolver.resolve(
                            text=f"{normalized.title} {normalized.text_snippet or ''}"
                        )
                        row["resolver_candidates"] = [
                            candidate.model_dump(mode="json") for candidate in resolution.candidates
                        ]
                        row["resolver_status"] = resolution.resolution_status.value
                        feed["normalized_items"].append(row)
                    except Exception as exc:
                        feed["normalization_rejected"] += 1
                        feed["error"] = f"normalization: {type(exc).__name__}: {exc}"
                feed["normalized"] = len(feed["normalized_items"])
                print(
                    f"FEED {feed_url} robots=ALLOW http=200 entries={feed['entries']} "
                    f"cap_rejected={feed['cap_rejected']} fetched={feed['fetched']} "
                    f"missing_title={feed['missing_title_rejected']} "
                    f"missing_url={feed['missing_url_rejected']} "
                    f"duplicates={feed['duplicate_rejected']} normalized={feed['normalized']} "
                    f"normalization_rejected={feed['normalization_rejected']}"
                )
            except Exception as exc:
                feed["error"] = f"{type(exc).__name__}: {exc}"
                print(f"FEED {feed_url} ERROR={feed['error']}")
    finally:
        await client.aclose()

    output = REPO_ROOT / "audit" / "rss_snapshot_k1.json"
    output.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"SNAPSHOT={output.relative_to(REPO_ROOT)}")
    print(f"FEEDS={len(snapshot['feeds'])} RAW_ITEMS={sum(len(feed['raw_items']) for feed in snapshot['feeds'])}")


if __name__ == "__main__":
    asyncio.run(main())
