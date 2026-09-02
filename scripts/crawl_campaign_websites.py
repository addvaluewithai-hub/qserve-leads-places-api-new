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

ROOT = Path(__file__).resolve().parents[1]


def load_json(path: Path):
    if not path.exists():
        raise SystemExit(f"Missing file: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


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


def target_service_from_query(query: str | None) -> str | None:
    mapping = {
        "family law attorney": "family law",
        "probate attorney": "probate",
        "estate planning attorney": "estate planning",
        "immigration attorney": "immigration",
        "business attorney": "business law",
    }
    return mapping.get((query or "").strip().lower())


def extract_internal_links(result, homepage: str) -> list[dict]:
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
        if not target or normalized_host(target) != root_host:
            continue
        current = deduped.get(target)
        row = {"url": target, "anchor_text": str(text).strip()}
        if current is None or (not current.get("anchor_text") and row["anchor_text"]):
            deduped[target] = row

    return sorted(deduped.values(), key=lambda row: row["url"])


async def fetch_homepage_links(crawler: AsyncWebCrawler, lead: dict) -> tuple[dict, list[dict]]:
    homepage = clean_url(lead.get("website"))
    base = {
        "lead_id": lead.get("id"),
        "name": lead.get("name"),
        "source_area": lead.get("source_area"),
        "source_query": lead.get("source_query"),
        "target_service": target_service_from_query(lead.get("source_query")),
        "homepage": homepage,
        "crawl_status": "pending",
        "homepage_status_code": None,
        "homepage_title": None,
        "internal_links_found": 0,
        "attempts": 0,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "error": None,
    }
    if not homepage:
        base.update({"crawl_status": "skipped", "error": "missing_website"})
        return base, []

    config = CrawlerRunConfig(
        scraping_strategy=LXMLWebScrapingStrategy(),
        cache_mode=CacheMode.BYPASS,
        page_timeout=30000,
        verbose=False,
    )

    last_error = None
    for attempt in (1, 2):
        base["attempts"] = attempt
        try:
            result = await crawler.arun(url=homepage, config=config)
            if isinstance(result, list):
                result = result[0] if result else None
            if result is None:
                last_error = "Crawl4AI returned no homepage result"
            elif getattr(result, "success", True):
                metadata = getattr(result, "metadata", None) or {}
                links = extract_internal_links(result, homepage)
                base.update({
                    "crawl_status": "completed",
                    "homepage_status_code": getattr(result, "status_code", None),
                    "homepage_title": metadata.get("title"),
                    "internal_links_found": len(links),
                    "error": None,
                })
                return base, links
            else:
                last_error = str(
                    getattr(result, "error_message", None)
                    or getattr(result, "error", None)
                    or "Crawl4AI returned success=false"
                )
                base["homepage_status_code"] = getattr(result, "status_code", None)
        except Exception as exc:
            last_error = f"{type(exc).__name__}: {exc}"

        if attempt == 1:
            await asyncio.sleep(1)

    base.update({"crawl_status": "failed", "error": (last_error or "unknown_error")[:1200]})
    return base, []


def write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


async def run(args) -> None:
    out_dir = Path(args.out_dir) if args.out_dir else ROOT / "out" / args.campaign
    campaign = load_json(out_dir / "campaign.json")
    leads = load_json(out_dir / "leads.json")
    enrichment = campaign.get("enrichment") or {}
    if not enrichment.get("website_crawl_required"):
        print(json.dumps({"campaign": args.campaign, "homepage_link_collection": "skipped"}, indent=2))
        return

    max_leads = min(len(leads), max(1, int(args.limit or len(leads))))
    summaries: list[dict] = []
    link_rows: list[dict] = []

    async with AsyncWebCrawler() as crawler:
        for index, lead in enumerate(leads[:max_leads], 1):
            print(f"[{index}/{max_leads}] Fetching homepage links: {lead.get('name')} - {lead.get('website')}")
            summary, links = await fetch_homepage_links(crawler, lead)
            summaries.append(summary)
            for link in links:
                link_rows.append({
                    "lead_id": lead.get("id"),
                    "name": lead.get("name"),
                    "source_area": lead.get("source_area"),
                    "source_query": lead.get("source_query"),
                    "target_service": summary.get("target_service"),
                    "homepage": summary.get("homepage"),
                    "url": link["url"],
                    "anchor_text": link["anchor_text"],
                })
            print(f"  status={summary['crawl_status']} attempts={summary['attempts']} links={summary['internal_links_found']}")

    payload = []
    links_by_lead: dict[str, list[dict]] = {}
    for row in link_rows:
        links_by_lead.setdefault(str(row.get("lead_id")), []).append({
            "url": row["url"],
            "anchor_text": row["anchor_text"],
        })
    for summary in summaries:
        item = dict(summary)
        item["links"] = links_by_lead.get(str(summary.get("lead_id")), [])
        payload.append(item)

    (out_dir / "homepage_links.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    (out_dir / "homepage_fetch_summary.json").write_text(json.dumps(summaries, ensure_ascii=False, indent=2), encoding="utf-8")
    write_csv(out_dir / "homepage_links.csv", link_rows, [
        "lead_id", "name", "source_area", "source_query", "target_service", "homepage", "url", "anchor_text",
    ])

    aggregate = {
        "campaign": args.campaign,
        "leads_attempted": len(summaries),
        "homepage_fetch_completed": sum(1 for row in summaries if row.get("crawl_status") == "completed"),
        "homepage_fetch_failed": sum(1 for row in summaries if row.get("crawl_status") == "failed"),
        "homepages_retried": sum(1 for row in summaries if int(row.get("attempts") or 0) > 1),
        "total_internal_homepage_links": len(link_rows),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    (out_dir / "homepage_links_summary.json").write_text(json.dumps(aggregate, indent=2), encoding="utf-8")
    print(json.dumps(aggregate, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch same-domain links from campaign lead homepages with Crawl4AI")
    parser.add_argument("--campaign", required=True)
    parser.add_argument("--out-dir", default=None)
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
