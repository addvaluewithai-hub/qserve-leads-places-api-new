#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse, urlunparse

from crawl4ai import AsyncWebCrawler, CacheMode, CrawlerRunConfig
from crawl4ai.content_scraping_strategy import LXMLWebScrapingStrategy

PAGE_ASSET_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".avif", ".ico",
    ".css", ".js", ".map", ".xml", ".txt", ".zip", ".mp3", ".mp4", ".webm",
    ".woff", ".woff2", ".ttf", ".eot", ".pdf",
}
ASSET_PATH_MARKERS = (
    "/wp-content/uploads/",
    "/wp-includes/",
    "/assets/images/",
    "/images/",
)
GENERIC_ANCHORS = {"", "learn more", "read more", "more", "click here", "view more", "details"}


def clean_url(value: str | None) -> str | None:
    if not value:
        return None
    value = value.strip()
    if not value:
        return None
    if "://" not in value:
        value = f"https://{value}"
    parsed = urlparse(value)
    if not parsed.hostname:
        return None
    return urlunparse((parsed.scheme or "https", parsed.netloc, parsed.path or "/", "", "", ""))


def normalized_host(value: str) -> str:
    host = (urlparse(value).hostname or "").lower().strip(".")
    return host[4:] if host.startswith("www.") else host


def canonical_url(value: str, base: str) -> str | None:
    try:
        absolute = urljoin(base, value)
        parsed = urlparse(absolute)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            return None
        path = parsed.path or "/"
        if path != "/":
            path = path.rstrip("/")
        return urlunparse((parsed.scheme, parsed.netloc.lower(), path, "", "", ""))
    except Exception:
        return None


def is_page_link(url: str) -> bool:
    path = (urlparse(url).path or "/").lower()
    if any(marker in path for marker in ASSET_PATH_MARKERS):
        return False
    suffix = Path(path).suffix.lower()
    if suffix in PAGE_ASSET_EXTENSIONS:
        return False
    return True


def clean_anchor(value: object) -> str:
    text = " ".join(str(value or "").split())
    if len(text) > 140:
        text = text[:137].rstrip() + "..."
    return text


def anchor_quality(text: str) -> tuple[int, int]:
    normalized = text.strip().lower()
    if normalized in GENERIC_ANCHORS:
        return (0, -len(text))
    if 2 <= len(text) <= 80:
        return (2, -len(text))
    return (1, -len(text))


def extract_internal_links(result, homepage: str) -> list[dict]:
    """Collect only page-like same-domain links visible on the rendered homepage.

    This is deliberately not a deep crawl and does not classify services. It removes
    obvious asset/file targets and keeps a compact anchor for each unique page URL.
    """
    root_host = normalized_host(homepage)
    links = getattr(result, "links", None) or {}
    items = links.get("internal") if isinstance(links, dict) else []
    deduped: dict[str, dict] = {}

    for item in items or []:
        if isinstance(item, str):
            href, text = item, ""
        else:
            href = item.get("href") or item.get("url")
            text = item.get("text") or item.get("anchor") or ""
        if not href:
            continue
        target = canonical_url(str(href), homepage)
        if not target or normalized_host(target) != root_host or not is_page_link(target):
            continue

        row = {"url": target, "anchor_text": clean_anchor(text)}
        current = deduped.get(target)
        if current is None or anchor_quality(row["anchor_text"]) > anchor_quality(current.get("anchor_text") or ""):
            deduped[target] = row

    return sorted(deduped.values(), key=lambda row: row["url"])


def load_csv(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


async def fetch_one(crawler: AsyncWebCrawler, lead: dict, source_index: int) -> tuple[dict, list[dict]]:
    homepage = clean_url(lead.get("website"))
    summary = {
        "source_index": source_index,
        "place_id": lead.get("place_id"),
        "name": lead.get("name"),
        "address": lead.get("address"),
        "source_market": lead.get("source_market"),
        "rating": lead.get("rating"),
        "review_count": lead.get("review_count"),
        "website_domain": lead.get("website_domain"),
        "homepage": homepage,
        "prior_open_web_verified": lead.get("website_verified_open_web"),
        "crawl_status": "pending",
        "homepage_status_code": None,
        "homepage_title": None,
        "final_url": None,
        "internal_links_found": 0,
        "attempts": 0,
        "error": None,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }
    if not homepage:
        summary.update({"crawl_status": "skipped", "error": "missing_website"})
        return summary, []

    config = CrawlerRunConfig(
        scraping_strategy=LXMLWebScrapingStrategy(),
        cache_mode=CacheMode.BYPASS,
        page_timeout=30000,
        verbose=False,
    )

    last_error = None
    for attempt in (1, 2):
        summary["attempts"] = attempt
        try:
            result = await crawler.arun(url=homepage, config=config)
            if isinstance(result, list):
                result = result[0] if result else None
            if result is None:
                last_error = "Crawl4AI returned no homepage result"
            elif getattr(result, "success", True):
                metadata = getattr(result, "metadata", None) or {}
                final_url = clean_url(getattr(result, "url", None)) or homepage
                links = extract_internal_links(result, final_url)
                summary.update({
                    "crawl_status": "completed",
                    "homepage_status_code": getattr(result, "status_code", None),
                    "homepage_title": metadata.get("title"),
                    "final_url": final_url,
                    "internal_links_found": len(links),
                    "error": None,
                })
                return summary, links
            else:
                last_error = str(
                    getattr(result, "error_message", None)
                    or getattr(result, "error", None)
                    or "Crawl4AI returned success=false"
                )
                summary["homepage_status_code"] = getattr(result, "status_code", None)
        except Exception as exc:
            last_error = f"{type(exc).__name__}: {exc}"

        if attempt == 1:
            await asyncio.sleep(1)

    summary.update({"crawl_status": "failed", "error": (last_error or "unknown_error")[:1200]})
    return summary, []


async def run(args) -> None:
    input_path = Path(args.input)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    rows = load_csv(input_path)
    start = max(0, int(args.start))
    limit = max(1, int(args.limit))
    selected = rows[start:start + limit]

    summaries: list[dict] = []
    link_rows: list[dict] = []

    async with AsyncWebCrawler() as crawler:
        for offset, lead in enumerate(selected):
            source_index = start + offset
            print(f"[{offset + 1}/{len(selected)}] #{source_index} {lead.get('name')} - {lead.get('website')}")
            summary, links = await fetch_one(crawler, lead, source_index)
            summaries.append(summary)
            for link in links:
                link_rows.append({
                    "source_index": source_index,
                    "place_id": lead.get("place_id"),
                    "name": lead.get("name"),
                    "address": lead.get("address"),
                    "source_market": lead.get("source_market"),
                    "rating": lead.get("rating"),
                    "review_count": lead.get("review_count"),
                    "website_domain": lead.get("website_domain"),
                    "homepage": summary.get("homepage"),
                    "final_url": summary.get("final_url"),
                    "url": link["url"],
                    "anchor_text": link["anchor_text"],
                })
            print(f"  status={summary['crawl_status']} attempts={summary['attempts']} page_links={summary['internal_links_found']}")

    links_by_index: dict[int, list[dict]] = {}
    for row in link_rows:
        links_by_index.setdefault(int(row["source_index"]), []).append({
            "url": row["url"],
            "anchor_text": row["anchor_text"],
        })

    payload = []
    for summary in summaries:
        item = dict(summary)
        item["links"] = links_by_index.get(int(summary["source_index"]), [])
        payload.append(item)

    write_csv(out_dir / "homepage_links.csv", link_rows, [
        "source_index", "place_id", "name", "address", "source_market", "rating", "review_count",
        "website_domain", "homepage", "final_url", "url", "anchor_text",
    ])
    write_csv(out_dir / "homepage_fetch_summary.csv", summaries, [
        "source_index", "place_id", "name", "address", "source_market", "rating", "review_count",
        "website_domain", "homepage", "prior_open_web_verified", "crawl_status", "homepage_status_code",
        "homepage_title", "final_url", "internal_links_found", "attempts", "error", "fetched_at",
    ])
    (out_dir / "homepage_links.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    aggregate = {
        "input": str(input_path),
        "batch_start": start,
        "batch_limit": limit,
        "leads_available": len(rows),
        "leads_attempted": len(summaries),
        "homepage_fetch_completed": sum(1 for r in summaries if r.get("crawl_status") == "completed"),
        "homepage_fetch_failed": sum(1 for r in summaries if r.get("crawl_status") == "failed"),
        "homepage_fetch_skipped": sum(1 for r in summaries if r.get("crawl_status") == "skipped"),
        "homepages_retried": sum(1 for r in summaries if int(r.get("attempts") or 0) > 1),
        "completed_with_zero_internal_links": sum(1 for r in summaries if r.get("crawl_status") == "completed" and int(r.get("internal_links_found") or 0) == 0),
        "total_internal_homepage_page_links": len(link_rows),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    (out_dir / "homepage_links_summary.json").write_text(json.dumps(aggregate, indent=2), encoding="utf-8")
    print(json.dumps(aggregate, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch homepage-only same-domain page links for a CSV working set")
    parser.add_argument("--input", required=True)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--start", type=int, default=0)
    parser.add_argument("--limit", type=int, default=100)
    args = parser.parse_args()
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
