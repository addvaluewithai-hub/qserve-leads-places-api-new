#!/usr/bin/env python3
from __future__ import annotations

"""Read-only A/B benchmark for ZIP exact-gate vs area-gate discovery.

This script intentionally performs NO D1 writes. It uses the same Google response
to score two policies:
  STRICT  = returned state matches target state + postal_code == target ZIP
  RELAXED = returned state matches target state; ZIP is only the 10 km search seed

It then crawls the union of net-new quality candidates once and compares unique
crawler-confirmed domains after global Place-ID/domain dedupe.
"""

import argparse
import asyncio
import json
import os
from urllib.parse import urlparse

import requests
import tldextract
from crawl4ai import AsyncWebCrawler

import build_next_1000_lawyers_zip as core
from crawl_working_set_homepages import fetch_one
from d1_helpers import ROOT, make_query_client, result_rows
from zip_manager import load_campaign, load_plan, load_zip_universe

SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"
TLD_EXTRACT = tldextract.TLDExtract(suffix_list_urls=None)

BLOCKED = {
    "google.com", "googleusercontent.com", "facebook.com", "instagram.com",
    "linkedin.com", "twitter.com", "x.com", "youtube.com", "tiktok.com",
    "yelp.com", "avvo.com", "justia.com", "findlaw.com", "lawyers.com",
    "martindale.com", "martindale-hubbell.com", "superlawyers.com", "lawinfo.com",
    "yellowpages.com", "mapquest.com", "bbb.org", "chamberofcommerce.com",
    "alignable.com", "linktr.ee", "bio.site", "beacons.ai", "business.site",
}


def business_domain(value: str | None) -> str | None:
    if not value:
        return None
    try:
        normalized = value if "://" in value else f"https://{value}"
        host = (urlparse(normalized).hostname or "").lower().strip(".")
        if host.startswith("www."):
            host = host[4:]
        parts = TLD_EXTRACT(host)
        return f"{parts.domain}.{parts.suffix}".lower() if parts.domain and parts.suffix else (host or None)
    except Exception:
        return None


def blocked(value: str | None) -> bool:
    domain = business_domain(value)
    return not domain or domain in BLOCKED or any(domain.endswith("." + item) for item in BLOCKED)


def component_value(components: list[dict] | None, wanted: str) -> str | None:
    for item in components or []:
        if wanted not in (item.get("types") or []):
            continue
        value = item.get("shortText") or item.get("longText")
        if value:
            return str(value).strip()
    return None


def postal_code(components: list[dict] | None) -> str | None:
    value = component_value(components, "postal_code")
    if not value:
        return None
    digits = "".join(ch for ch in value if ch.isdigit())
    return digits[:5] if len(digits) >= 5 else None


def state_code(components: list[dict] | None) -> str | None:
    value = component_value(components, "administrative_area_level_1")
    return value.upper() if value else None


def existing_global(query) -> tuple[set[str], set[str]]:
    ids = {
        str(r["lead_id"])
        for r in result_rows(query("SELECT lead_id FROM lead_domains"))
        if r.get("lead_id")
    }
    domains: set[str] = set()
    for row in result_rows(query("SELECT website_domain FROM lead_domains")):
        domain = business_domain(row.get("website_domain"))
        if domain:
            domains.add(domain)
    for row in result_rows(query(
        "SELECT lead_id,website_domain FROM outreach_suppression WHERE suppressed=1 AND (reengage_after IS NULL OR reengage_after > CURRENT_TIMESTAMP)"
    )):
        if row.get("lead_id"):
            ids.add(str(row["lead_id"]))
        domain = business_domain(row.get("website_domain"))
        if domain:
            domains.add(domain)
    return ids, domains


def already_requested_zips(query, campaign_id: str) -> set[str]:
    out: set[str] = set()
    for row in result_rows(query(
        "SELECT context FROM api_usage_ledger WHERE campaign_id=? AND sku='places_text_search_enterprise'",
        [campaign_id],
    )):
        context = str(row.get("context") or "")
        for part in context.split(";"):
            if part.startswith("zip="):
                out.add(part.split("=", 1)[1].strip())
    return out


def choose_zips(query, campaign: dict, plan: dict, state: str, count: int) -> list[dict]:
    used = already_requested_zips(query, campaign["id"])
    rows = [r for r in load_zip_universe(plan) if str(r.get("state_code") or "").upper() == state.upper()]
    rows.sort(key=lambda r: (int(r.get("city_priority") if r.get("city_priority") is not None else 1000), str(r.get("city") or ""), str(r.get("zip_code") or "")))
    selected = [r for r in rows if str(r["zip_code"]) not in used][:count]
    if len(selected) < count:
        raise SystemExit(f"Only {len(selected)} unrequested ZIPs available for {state}; need {count}")
    return selected


def google_search(key: str, campaign: dict, row: dict) -> dict:
    google = campaign.get("google") or {}
    zip_code = str(row["zip_code"])
    half_span = float(google.get("zip_location_restriction_half_span_km") or 10.0)
    body = {
        "textQuery": str(google.get("query_template") or "lawyer in {zip_code}").format(zip_code=zip_code),
        "includedType": google.get("included_type") or "lawyer",
        "strictTypeFiltering": bool(google.get("strict_type_filtering", True)),
        "minRating": float(google.get("min_rating_search_filter") or 4.0),
        "pageSize": 20,
        "regionCode": "US",
        "languageCode": "en",
        "locationRestriction": {
            "rectangle": core.restriction_rectangle(float(row["latitude"]), float(row["longitude"]), half_span)
        },
    }
    headers = {
        "X-Goog-Api-Key": key,
        "Content-Type": "application/json",
        "X-Goog-FieldMask": "places.id,places.addressComponents,places.businessStatus,places.rating,places.userRatingCount,places.websiteUri,nextPageToken",
    }
    response = requests.post(SEARCH_URL, headers=headers, json=body, timeout=60)
    response.raise_for_status()
    return response.json()


def quality(place: dict, target_zip: str, target_state: str) -> dict | None:
    components = place.get("addressComponents") or []
    p_state = state_code(components)
    p_zip = postal_code(components)
    if p_state != target_state:
        return None
    place_id = place.get("id")
    website = place.get("websiteUri")
    rating = place.get("rating")
    reviews = place.get("userRatingCount")
    status = place.get("businessStatus")
    if not place_id or not website or blocked(str(website)):
        return None
    if status != "OPERATIONAL":
        return None
    if rating is None or float(rating) < 4.0:
        return None
    if reviews is None or int(reviews) < 20:
        return None
    return {
        "place_id": str(place_id),
        "website_seed": str(website),
        "seed_domain": business_domain(str(website)),
        "postal_code": p_zip,
        "is_exact_zip": p_zip == target_zip,
        "rating": float(rating),
        "reviews": int(reviews),
    }


async def crawl_union(candidates: list[dict], workers: int = 4) -> list[dict]:
    queue: asyncio.Queue[tuple[int, dict]] = asyncio.Queue()
    for idx, item in enumerate(candidates):
        queue.put_nowait((idx, item))
    results: list[dict] = []

    async def worker() -> None:
        async with AsyncWebCrawler() as crawler:
            while True:
                try:
                    idx, item = queue.get_nowait()
                except asyncio.QueueEmpty:
                    return
                try:
                    lead = {"place_id": item["place_id"], "website": item["website_seed"], "website_domain": item["seed_domain"], "source_market": item["source_zip"]}
                    summary, _links = await fetch_one(crawler, lead, idx)
                    final_url = summary.get("final_url") or summary.get("homepage")
                    final_domain = business_domain(final_url)
                    results.append({**item, "crawl_status": summary.get("crawl_status"), "final_url": final_url, "final_domain": final_domain, "blocked_final": blocked(final_url)})
                finally:
                    queue.task_done()

    if candidates:
        await asyncio.gather(*(worker() for _ in range(min(workers, len(candidates)))))
    return results


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--campaign", default="lawyers-us")
    parser.add_argument("--state", default="TX")
    parser.add_argument("--requests", type=int, default=10)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()

    key = os.environ["GOOGLE_API_KEY"]
    query = make_query_client()  # read-only use only; do NOT apply schema or write
    campaign = load_campaign(args.campaign)
    plan = load_plan(campaign)
    existing_ids, existing_domains = existing_global(query)
    zips = choose_zips(query, campaign, plan, args.state.upper(), args.requests)

    per_zip = []
    union: dict[str, dict] = {}
    for row in zips:
        target_zip = str(row["zip_code"])
        payload = google_search(key, campaign, row)
        raw = payload.get("places") or []
        state_matches = 0
        exact = 0
        strict_quality = 0
        relaxed_quality = 0
        for place in raw:
            components = place.get("addressComponents") or []
            if state_code(components) == args.state.upper():
                state_matches += 1
            if state_code(components) == args.state.upper() and postal_code(components) == target_zip:
                exact += 1
            item = quality(place, target_zip, args.state.upper())
            if not item:
                continue
            relaxed_quality += 1
            if item["is_exact_zip"]:
                strict_quality += 1
            if item["place_id"] in existing_ids or item["seed_domain"] in existing_domains:
                continue
            item["source_zip"] = target_zip
            item["source_city"] = row.get("city")
            current = union.get(item["place_id"])
            if current is None or (item["is_exact_zip"] and not current["is_exact_zip"]):
                union[item["place_id"]] = item
        per_zip.append({
            "zip": target_zip,
            "city": row.get("city"),
            "raw": len(raw),
            "state_matches": state_matches,
            "exact_zip": exact,
            "strict_quality": strict_quality,
            "relaxed_quality": relaxed_quality,
        })
        print(json.dumps(per_zip[-1]))

    crawled = asyncio.run(crawl_union(list(union.values()), args.workers))
    strict_domains: set[str] = set()
    relaxed_domains: set[str] = set()
    crawl_completed = 0
    for item in crawled:
        if item.get("crawl_status") != "completed" or item.get("blocked_final") or not item.get("final_domain"):
            continue
        crawl_completed += 1
        domain = item["final_domain"]
        if domain in existing_domains:
            continue
        relaxed_domains.add(domain)
        if item.get("is_exact_zip"):
            strict_domains.add(domain)

    summary = {
        "benchmark": "strict_exact_zip_vs_relaxed_10km_area",
        "state": args.state.upper(),
        "google_requests": len(zips),
        "d1_writes": 0,
        "zip_half_span_km": float((campaign.get("google") or {}).get("zip_location_restriction_half_span_km") or 10.0),
        "zips": [r["zip"] for r in per_zip],
        "raw_places": sum(r["raw"] for r in per_zip),
        "state_match_places": sum(r["state_matches"] for r in per_zip),
        "exact_zip_places": sum(r["exact_zip"] for r in per_zip),
        "strict_quality_passes": sum(r["strict_quality"] for r in per_zip),
        "relaxed_quality_passes": sum(r["relaxed_quality"] for r in per_zip),
        "union_net_new_candidates_before_crawl": len(union),
        "crawl_completed": crawl_completed,
        "strict_net_new_crawler_domains": len(strict_domains),
        "relaxed_net_new_crawler_domains": len(relaxed_domains),
        "incremental_domains_from_relaxation": len(relaxed_domains - strict_domains),
        "strict_domains_per_request": round(len(strict_domains) / max(1, len(zips)), 3),
        "relaxed_domains_per_request": round(len(relaxed_domains) / max(1, len(zips)), 3),
        "yield_multiplier": round(len(relaxed_domains) / max(1, len(strict_domains)), 3),
        "note": "Google requests are intentionally not written to the D1 usage ledger; this benchmark performs read-only D1 access and its artifact is the authoritative usage record for these benchmark calls.",
    }

    out = ROOT / "out" / "zip-relaxation-ab"
    out.mkdir(parents=True, exist_ok=True)
    (out / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    (out / "per_zip.json").write_text(json.dumps(per_zip, indent=2), encoding="utf-8")
    (out / "crawled.json").write_text(json.dumps(crawled, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
