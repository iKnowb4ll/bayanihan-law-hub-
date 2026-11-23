#!/usr/bin/env python3
"""Fetch public Philippine news RSS feeds and write a small, dated JSON feed."""
import json
import re
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from html import unescape
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "news.json"
FEEDS = [
    ("Philippine News Agency", "https://www.pna.gov.ph/latest.rss"),
    ("GMA News", "https://data.gmanetwork.com/gno/rss/news/feed.xml"),
    ("Philippine Star", "https://www.philstar.com/rss/headlines"),
    ("Inquirer", "https://www.inquirer.net/fullfeed"),
]
NOW = datetime.now(timezone.utc)
CUTOFF = NOW - timedelta(days=7)


def local_name(tag):
    return tag.rsplit("}", 1)[-1].lower()


def child_text(node, names):
    for child in list(node):
        if local_name(child.tag) in names:
            if child.text and child.text.strip():
                return child.text.strip()
            href = child.attrib.get("href")
            if href:
                return href.strip()
    return ""


def parse_date(value):
    if not value:
        return None
    value = value.strip()
    try:
        dt = parsedate_to_datetime(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        pass
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def fetch_feed(source, url):
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "BayanihanLawHubNewsBot/1.0 (daily public RSS headlines)"}
    )
    with urllib.request.urlopen(request, timeout=25) as response:
        payload = response.read(4_000_000)
    root = ET.fromstring(payload)
    items = [node for node in root.iter() if local_name(node.tag) in ("item", "entry")]
    found = []
    for item in items:
        title = unescape(child_text(item, {"title"})).strip()
        link = child_text(item, {"link"})
        if not link:
            link_node = next((x for x in list(item) if local_name(x.tag) == "link"), None)
            if link_node is not None:
                link = link_node.attrib.get("href", "")
        date_text = child_text(item, {"pubdate", "published", "updated", "date"})
        published = parse_date(date_text)
        if not title or not link or not published or published < CUTOFF:
            continue
        if not link.startswith(("https://", "http://")):
            continue
        found.append({
            "title": title,
            "url": link,
            "source": source,
            "published": published.isoformat(),
        })
    return found


def main():
    all_items = []
    failures = []
    for source, url in FEEDS:
        try:
            all_items.extend(fetch_feed(source, url))
            print(f"Fetched {source}")
        except Exception as exc:
            failures.append(f"{source}: {exc}")
            print(f"Feed unavailable: {source}: {exc}")

    # Keep the site usable if one publisher's feed is temporarily offline.
    unique = {}
    for item in all_items:
        key = item["url"].split("#", 1)[0]
        if key not in unique:
            unique[key] = item
    items = sorted(unique.values(), key=lambda x: x["published"], reverse=True)[:24]
    if not items:
        raise SystemExit("No recent headlines were fetched; preserving the existing news.json.")

    data = {
        "updated": NOW.isoformat(),
        "updated_display": NOW.astimezone(timezone(timedelta(hours=8))).strftime("%B %d, %Y at %I:%M %p PHT"),
        "count": len(items),
        "sources": [name for name, _ in FEEDS],
        "headlines": items,
        "feed_warnings": failures,
    }
    OUTPUT.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {len(items)} headlines to {OUTPUT}")


if __name__ == "__main__":
    main()
