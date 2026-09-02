#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import csv
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse, urlunparse

from crawl4ai import AsyncWebCrawler, CacheMode, CrawlerRunConfig
from crawl4ai.content_scraping_strategy import LXMLWebScrapingStrategy
from crawl4ai.deep_crawling import BFSDeepCrawlStrategy

ROOT = Path(__file__).resolve().parents[1]
GENERAL_SERVICE_PATHS = {
    "practice-areas", "practice-area", "services", "service", "areas-of-practice",
    "areas-of-law", "legal-services", "what-we-do", "our-services",
}
SERVICE_ALIASES = {
    "family law": ["family law", "family-law", "familylaw", "family lawyer", "family attorney"],
    "probate": ["probate", "probate law", "probate attorney", "probate lawyer"],
    "estate planning": ["estate planning", "estate-planning", "estateplanning", "estate planner"],
    "wills": ["wills", "will attorney", "will lawyer", "last will"],
    "trusts": ["trusts", "trust attorney", "trust lawyer", "living trust"],
    "immigration": ["immigration", "immigration law", "immigration attorney", "immigration lawyer"],
    "business law": ["business law", "business-law", "businesslaw", "business attorney", "business lawyer"],
}
QUERY_TO_SERVICE = {
    "family law attorney": "family law",
    "probate attorney": "probate",
    "estate planning attorney": "estate planning",
    "immigration attorney": "immigration",
    "business attorney": "business law",
}


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
    path = parsed.path or "/"
    return urlunparse((parsed.scheme or "https", parsed.netloc, path, "", "", ""))


def normalized_host(value: str) -> str:
    host = (urlparse(value).hostname or "").lower().strip(".")
    return host[4:] if host.startswith("www.") else host


def canonical_url(value: str, base: str | None = None) -> str | None:
    try:
        absolute = urljoin(base or value, value)
        parsed = urlparse(absolute)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            return None
        path = re.sub(r"/{2,}", "/", parsed.path or "/")
        if path != "/":
            path = path.rstrip("/")
        return urlunparse((parsed.scheme, parsed.netloc.lower(), path, "", "", ""))
    except Exception:
        return None


def slug_text(value: str) -> str:
    value = value.lower().replace("&", " and ")
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def page_path_tokens(url: str) -> tuple[str, str]:
    path = urlparse(url).path.strip("/").lower()
    normalized = slug_text(path)
    first = path.split("/", 1)[0] if path else ""
    return normalized, first


def is_general_service_page(url: str, title: str) -> bool:
    normalized_path, _ = page_path_tokens(url)
    segments = [segment for segment in urlparse(url).path.lower().split("/") if segment]
    if len(segments) == 1 and segments[0] in GENERAL_SERVICE_PATHS:
        return True
    title_text = slug_text(title)
    if len(segments) <= 1 and any(slug_text(item) == title_text for item in GENERAL_SERVICE_PATHS):
        return True
    if normalized_path in {slug_text(item) for item in GENERAL_SERVICE_PATHS}:
        return True
    return False


def aliases_for(service: str) -> list[str]:
    aliases = SERVICE_ALIASES.get(service.lower(), [service])
    return list(dict.fromkeys([slug_text(service), *[slug_text(x) for x in aliases]]))


def dedicated_service_matches(url: str, title: str, services: list[str]) -> list[str]:
    if is_general_service_page(url, title):
        return []
    path_text, _ = page_path_tokens(url)
    title_text = slug_text(title)
    matches = []
    for service in services:
        aliases = aliases_for(service)
        path_hit = any(alias and alias in path_text for alias in aliases)
        title_hit = any(alias and alias in title_text for alias in aliases)
        if path_hit or title_hit:
            matches.append(service)
    return matches


def target_service_from_query(query: str | None) -> str | None:
    query = slug_text(query or "")
    for source_query, service in QUERY_TO_SERVICE.items():
        if slug_text(source_query) == query:
            return service
    return None


def extract_title(result) -> str:
    metadata = getattr(result, "metadata", None) or {}
    return str(metadata.get("title") or "").strip()


def result_depth(result) -> int:
    metadata = getattr(result, "metadata", None) or {}
    try:
        return int(metadata.get("depth", 0) or 0)
    except Exception:
        return 0


def internal_links_from_result(result, page_url: str, root_host: str) -> list[dict]:
    links = getattr(result, "links", None) or {}
    items = links.get("internal") if isinstance(links, dict) else []
    output = []
    for item in items or []:
        if isinstance(item, str):
            href, text = item, ""
        else:
            href = item.get("href") or item.get("url")
            text = item.get("text") or item.get("anchor") or ""
        if not href:
            continue
        target = canonical_url(href, page_url)
        if not target or normalized_host(target) != root_host:
            continue
        output.append({"source_url": page_url, "target_url": target, "anchor_text": str(text).strip()})
    return output


async def crawl_one(lead: dict, campaign: dict, max_depth: int, max_pages: int) -> tuple[dict, list[dict], list[dict]]:
    website = clean_url(lead.get("website"))
    services = [str(x).strip().lower() for x in (campaign.get("enrichment") or {}).get("target_services", []) if str(x).strip()]
    target_service = target_service_from_query(lead.get("source_query"))
    started = datetime.now(timezone.utc).isoformat()
    summary = {
        "lead_id": lead.get("id"),
        "name": lead.get("name"),
        "website": website,
        "target_service": target_service,
        "crawl_status": "pending",
        "pages_found": 0,
        "dedicated_service_pages": [],
        "dedicated_services_found": [],
        "target_service_dedicated_page": None,
        "crawl_qualification": "review",
        "crawl_started_at": started,
        "crawl_completed_at": None,
        "error": None,
    }
    if not website:
        summary.update({"crawl_status": "skipped", "error": "missing_website", "crawl_completed_at": datetime.now(timezone.utc).isoformat()})
        return summary, [], []

    root_host = normalized_host(website)
    page_rows: list[dict] = []
    link_rows: list[dict] = []
    try:
        config = CrawlerRunConfig(
            deep_crawl_strategy=BFSDeepCrawlStrategy(
                max_depth=max_depth,
                include_external=False,
                max_pages=max_pages,
            ),
            scraping_strategy=LXMLWebScrapingStrategy(),
            cache_mode=CacheMode.BYPASS,
            verbose=False,
            page_timeout=45000,
        )
        async with AsyncWebCrawler() as crawler:
            results = await crawler.arun(url=website, config=config)

        if not isinstance(results, list):
            results = list(results or [])
        seen_urls = set()
        dedicated_pages = []
        dedicated_services = set()
        for result in results:
            page_url = canonical_url(getattr(result, "url", None) or website)
            if not page_url or normalized_host(page_url) != root_host or page_url in seen_urls:
                continue
            seen_urls.add(page_url)
            title = extract_title(result)
            depth = result_depth(result)
            matches = dedicated_service_matches(page_url, title, services)
            page_rows.append({
                "lead_id": lead.get("id"),
                "name": lead.get("name"),
                "website": website,
                "url": page_url,
                "depth": depth,
                "title": title,
                "is_general_services_page": is_general_service_page(page_url, title),
                "matched_services": "|".join(matches),
                "dedicated_service_page": bool(matches),
                "status_code": getattr(result, "status_code", None),
                "success": bool(getattr(result, "success", True)),
            })
            if matches:
                dedicated_pages.append({"url": page_url, "title": title, "services": matches})
                dedicated_services.update(matches)
            link_rows.extend(internal_links_from_result(result, page_url, root_host))

        # De-duplicate the graph rows while preserving the most useful anchor text.
        unique_links = {}
        for row in link_rows:
            key = (row["source_url"], row["target_url"])
            current = unique_links.get(key)
            if current is None or (not current.get("anchor_text") and row.get("anchor_text")):
                unique_links[key] = row
        link_rows = list(unique_links.values())

        target_hit = None
        if target_service:
            target_hit = target_service in dedicated_services
        qualification = "review"
        if target_hit is True:
            qualification = "disqualified"
        elif target_hit is False:
            qualification = "qualified"
        summary.update({
            "crawl_status": "completed",
            "pages_found": len(page_rows),
            "internal_links_found": len(link_rows),
            "dedicated_service_pages": dedicated_pages,
            "dedicated_services_found": sorted(dedicated_services),
            "target_service_dedicated_page": target_hit,
            "crawl_qualification": qualification,
            "crawl_completed_at": datetime.now(timezone.utc).isoformat(),
        })
    except Exception as exc:
        summary.update({
            "crawl_status": "failed",
            "error": f"{type(exc).__name__}: {exc}"[:1200],
            "crawl_completed_at": datetime.now(timezone.utc).isoformat(),
        })
    return summary, page_rows, link_rows


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
        print(json.dumps({"campaign": args.campaign, "crawl": "skipped", "reason": "website_crawl_required=false"}, indent=2))
        return

    crawl_cfg = campaign.get("crawl") or {}
    max_depth = int(args.max_depth if args.max_depth is not None else crawl_cfg.get("max_depth", 2))
    max_pages = int(args.max_pages if args.max_pages is not None else crawl_cfg.get("max_pages_per_site", 30))
    max_leads = min(len(leads), max(1, int(args.limit or len(leads))))

    summaries: list[dict] = []
    pages: list[dict] = []
    links: list[dict] = []
    for index, lead in enumerate(leads[:max_leads], 1):
        print(f"[{index}/{max_leads}] Crawling {lead.get('name')} - {lead.get('website')}")
        summary, page_rows, link_rows = await crawl_one(lead, campaign, max_depth=max_depth, max_pages=max_pages)
        summaries.append(summary)
        pages.extend(page_rows)
        links.extend(link_rows)
        print(f"  status={summary['crawl_status']} pages={summary['pages_found']} dedicated={len(summary['dedicated_service_pages'])} target={summary['target_service']} verdict={summary['crawl_qualification']}")

    summary_by_id = {row.get("lead_id"): row for row in summaries}
    enriched = []
    for lead in leads:
        item = dict(lead)
        crawl = summary_by_id.get(lead.get("id"))
        if crawl:
            item["crawl"] = crawl
        enriched.append(item)

    (out_dir / "crawl_results.json").write_text(json.dumps(summaries, ensure_ascii=False, indent=2), encoding="utf-8")
    (out_dir / "leads_enriched.json").write_text(json.dumps(enriched, ensure_ascii=False, indent=2), encoding="utf-8")
    write_csv(out_dir / "crawl_pages.csv", pages, [
        "lead_id", "name", "website", "url", "depth", "title", "is_general_services_page",
        "matched_services", "dedicated_service_page", "status_code", "success",
    ])
    write_csv(out_dir / "crawl_links.csv", links, ["source_url", "target_url", "anchor_text"])
    aggregate = {
        "campaign": args.campaign,
        "leads_crawled": len(summaries),
        "crawl_completed": sum(1 for row in summaries if row.get("crawl_status") == "completed"),
        "crawl_failed": sum(1 for row in summaries if row.get("crawl_status") == "failed"),
        "total_pages_found": sum(int(row.get("pages_found") or 0) for row in summaries),
        "total_internal_links_found": sum(int(row.get("internal_links_found") or 0) for row in summaries),
        "target_service_disqualified": sum(1 for row in summaries if row.get("crawl_qualification") == "disqualified"),
        "target_service_qualified": sum(1 for row in summaries if row.get("crawl_qualification") == "qualified"),
        "needs_review": sum(1 for row in summaries if row.get("crawl_qualification") == "review"),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    (out_dir / "crawl_summary.json").write_text(json.dumps(aggregate, indent=2), encoding="utf-8")
    print(json.dumps(aggregate, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description="Crawl qualified campaign lead websites with Crawl4AI")
    parser.add_argument("--campaign", required=True)
    parser.add_argument("--out-dir", default=None)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--max-depth", type=int, default=None)
    parser.add_argument("--max-pages", type=int, default=None)
    args = parser.parse_args()
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
