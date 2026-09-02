#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import urlparse

import requests

from benchmark_lawyer_discovery import MIN_RATING, ground_one, search_market

OUT = Path("out/lawyers-1000-working-set")
TARGET = 1000
MIN_REVIEWS = 20
GROUNDING_WORKERS = 4
GROUNDING_SUBMIT_DELAY_SECONDS = 0.25

# Broad US market list. Texas is intentionally not the only source and is placed late in
# the list; the job stops as soon as 1,000 unique verified domains are reached.
MARKETS = [
    "Phoenix, AZ", "Tucson, AZ", "Las Vegas, NV", "Reno, NV", "Denver, CO",
    "Colorado Springs, CO", "Albuquerque, NM", "Salt Lake City, UT", "Boise, ID",
    "Spokane, WA", "Tacoma, WA", "Portland, OR", "Eugene, OR", "Sacramento, CA",
    "Fresno, CA", "Bakersfield, CA", "San Diego, CA", "San Jose, CA", "Oakland, CA",
    "Santa Rosa, CA", "Honolulu, HI", "Anchorage, AK", "Oklahoma City, OK", "Tulsa, OK",
    "Kansas City, MO", "St. Louis, MO", "Springfield, MO", "Omaha, NE", "Lincoln, NE",
    "Wichita, KS", "Des Moines, IA", "Cedar Rapids, IA", "Minneapolis, MN", "Duluth, MN",
    "Milwaukee, WI", "Madison, WI", "Green Bay, WI", "Chicago, IL", "Rockford, IL",
    "Indianapolis, IN", "Fort Wayne, IN", "Louisville, KY", "Lexington, KY", "Nashville, TN",
    "Knoxville, TN", "Chattanooga, TN", "Memphis, TN", "Birmingham, AL", "Huntsville, AL",
    "Montgomery, AL", "Mobile, AL", "Jackson, MS", "Little Rock, AR", "New Orleans, LA",
    "Baton Rouge, LA", "Shreveport, LA", "Orlando, FL", "Tampa, FL", "Jacksonville, FL",
    "Tallahassee, FL", "Fort Myers, FL", "Sarasota, FL", "West Palm Beach, FL", "Miami, FL",
    "Charlotte, NC", "Raleigh, NC", "Greensboro, NC", "Asheville, NC", "Charleston, SC",
    "Columbia, SC", "Greenville, SC", "Richmond, VA", "Norfolk, VA", "Roanoke, VA",
    "Washington, DC", "Baltimore, MD", "Wilmington, DE", "Philadelphia, PA", "Pittsburgh, PA",
    "Harrisburg, PA", "Allentown, PA", "Cleveland, OH", "Columbus, OH", "Cincinnati, OH",
    "Toledo, OH", "Detroit, MI", "Grand Rapids, MI", "Buffalo, NY", "Rochester, NY",
    "Albany, NY", "Hartford, CT", "New Haven, CT", "Providence, RI", "Boston, MA",
    "Worcester, MA", "Portland, ME", "Manchester, NH", "Burlington, VT", "Newark, NJ",
    "Trenton, NJ", "Virginia Beach, VA", "Savannah, GA", "Atlanta, GA", "Augusta, GA",
    "Fort Worth, TX", "Austin, TX", "San Antonio, TX", "Houston, TX", "El Paso, TX",
]

TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.I | re.S)


def canonical_domain(url: str | None) -> str | None:
    if not url:
        return None
    try:
        host = (urlparse(url).hostname or "").lower().strip(".")
        if host.startswith("www."):
            host = host[4:]
        return host or None
    except Exception:
        return None


def verify_website(url: str | None) -> dict:
    if not url:
        return {"website_verified_open_web": False, "website_http_status": None, "website_final_url": None, "website_title": None, "website_verify_error": "missing_url"}
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; QServeLeadVerifier/1.0; +https://github.com/addvaluewithai-hub/qserve-leads-places-api-new)"
    }
    try:
        response = requests.get(url, headers=headers, allow_redirects=True, timeout=20)
        final_url = response.url
        final_domain = canonical_domain(final_url)
        original_domain = canonical_domain(url)
        text = response.text[:500000] if "text" in (response.headers.get("content-type") or "").lower() or response.text else response.text[:500000]
        title = None
        match = TITLE_RE.search(text or "")
        if match:
            title = re.sub(r"\s+", " ", match.group(1)).strip()[:300]
        # 403/429 can still be a real business site blocking bots. Domain continuity plus
        # a real HTTP response is enough for the initial working set; Crawl4AI handles the browser pass later.
        verified = bool(final_domain and original_domain and (final_domain == original_domain or final_domain.endswith("." + original_domain) or original_domain.endswith("." + final_domain)))
        return {
            "website_verified_open_web": verified,
            "website_http_status": response.status_code,
            "website_final_url": final_url,
            "website_title": title,
            "website_verify_error": None,
        }
    except Exception as exc:
        return {
            "website_verified_open_web": False,
            "website_http_status": None,
            "website_final_url": None,
            "website_title": None,
            "website_verify_error": f"{type(exc).__name__}: {exc}"[:600],
        }


def ground_and_verify(key: str, candidate: dict) -> dict:
    row = ground_one(key, candidate)
    qualifies_google = (
        row.get("grounding_identity_match")
        and row.get("website_domain")
        and float(row.get("rating") or 0) >= MIN_RATING
        and int(row.get("review_count") or 0) >= MIN_REVIEWS
    )
    row["passed_google_quality_gate"] = bool(qualifies_google)
    if qualifies_google:
        row.update(verify_website(row.get("website")))
    else:
        row.update({
            "website_verified_open_web": False,
            "website_http_status": None,
            "website_final_url": None,
            "website_title": None,
            "website_verify_error": "quality_gate_failed",
        })
    return row


def safe_public_row(row: dict) -> dict:
    # Keep the initial artifact useful without preserving the full generated grounding summary.
    return {
        "place_id": row.get("place_id"),
        "name": row.get("name"),
        "address": row.get("address"),
        "source_market": row.get("source_market"),
        "website": row.get("website_final_url") or row.get("website"),
        "website_domain": canonical_domain(row.get("website_final_url") or row.get("website")),
        "website_title": row.get("website_title"),
        "website_http_status": row.get("website_http_status"),
        "google_maps_source": row.get("google_maps_source"),
        "rating": row.get("rating"),
        "review_count": row.get("review_count"),
        "grounding_identity_match": row.get("grounding_identity_match"),
        "website_verified_open_web": row.get("website_verified_open_web"),
    }


def write_csv(path: Path, rows: list[dict]) -> None:
    fields = [
        "place_id", "name", "address", "source_market", "website", "website_domain",
        "website_title", "website_http_status", "google_maps_source", "rating", "review_count",
        "grounding_identity_match", "website_verified_open_web",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    key = os.getenv("GOOGLE_API_KEY")
    if not key:
        raise SystemExit("GOOGLE_API_KEY is missing")
    OUT.mkdir(parents=True, exist_ok=True)

    seen_place_ids: set[str] = set()
    selected_by_domain: dict[str, dict] = {}
    search_log = []
    grounding_calls = 0
    identity_matches = 0
    websites_from_grounding = 0
    quality_gate_passes = 0
    website_open_web_verified = 0

    for market_index, market in enumerate(MARKETS, 1):
        if len(selected_by_domain) >= TARGET:
            break

        meta, rows = search_market(key, market)
        search_log.append(meta)
        fresh = []
        for row in rows:
            if row["place_id"] in seen_place_ids:
                continue
            seen_place_ids.add(row["place_id"])
            if row.get("business_status") != "OPERATIONAL":
                continue
            row["matched_markets"] = [market]
            fresh.append(row)

        print(
            f"MARKET {market_index}: {market} search={meta['http_status']} raw={len(rows)} "
            f"fresh_operational={len(fresh)} working={len(selected_by_domain)}/{TARGET}"
        )

        if not fresh:
            continue

        with ThreadPoolExecutor(max_workers=GROUNDING_WORKERS) as pool:
            futures = []
            for row in fresh:
                futures.append(pool.submit(ground_and_verify, key, row))
                # Global pacing keeps search_places Grounding calls below the documented 300/min quota.
                time.sleep(GROUNDING_SUBMIT_DELAY_SECONDS)

            for future in as_completed(futures):
                grounded = future.result()
                grounding_calls += 1
                if grounded.get("grounding_identity_match"):
                    identity_matches += 1
                if grounded.get("grounding_identity_match") and grounded.get("website_domain"):
                    websites_from_grounding += 1
                if grounded.get("passed_google_quality_gate"):
                    quality_gate_passes += 1
                if grounded.get("website_verified_open_web"):
                    website_open_web_verified += 1

                if not grounded.get("passed_google_quality_gate"):
                    continue

                # A real HTTP response may be blocked by bot protection. For the initial working set,
                # accept a quality-gated domain even if the basic requests verifier cannot fully render it;
                # Crawl4AI will perform the browser homepage verification later.
                domain = canonical_domain(grounded.get("website_final_url") or grounded.get("website"))
                if not domain:
                    continue

                candidate = safe_public_row(grounded)
                existing = selected_by_domain.get(domain)
                if existing is None or int(candidate.get("review_count") or 0) > int(existing.get("review_count") or 0):
                    selected_by_domain[domain] = candidate

        print(f"  → working domains now {len(selected_by_domain)}/{TARGET}")

    selected = list(selected_by_domain.values())
    selected.sort(key=lambda r: (-int(r.get("review_count") or 0), r.get("name") or ""))
    selected = selected[:TARGET]

    summary = {
        "target_working_domains": TARGET,
        "working_domains_collected": len(selected),
        "minimum_rating": MIN_RATING,
        "minimum_reviews": MIN_REVIEWS,
        "text_search_requests_attempted": len(search_log),
        "text_search_requests_successful": sum(1 for x in search_log if x.get("http_status") == 200),
        "unique_place_ids_seen": len(seen_place_ids),
        "grounding_calls_attempted": grounding_calls,
        "grounding_identity_matches": identity_matches,
        "websites_resolved_with_identity_match": websites_from_grounding,
        "quality_gate_passes_before_domain_dedupe": quality_gate_passes,
        "basic_open_web_website_verifications": website_open_web_verified,
        "markets_used": [x["market"] for x in search_log],
        "stopped_early_after_target": len(selected) >= TARGET and len(search_log) < len(MARKETS),
        "notes": [
            "Discovery uses Text Search Pro with only Place ID, name, address and business status plus minRating=4.7.",
            "Grounding Lite supplies website/rating/review-count; no Place Details Enterprise and no review text are requested.",
            "The working-set unit is a unique website domain, so duplicate offices are collapsed.",
            "Crawl4AI homepage-link collection and service-gap qualification happen after this initial 1,000-domain working set is created.",
        ],
    }

    (OUT / "lawyers_1000.json").write_text(json.dumps(selected, ensure_ascii=False, indent=2), encoding="utf-8")
    write_csv(OUT / "lawyers_1000.csv", selected)
    (OUT / "search_log.json").write_text(json.dumps(search_log, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))

    if len(selected) < TARGET:
        raise SystemExit(f"Only collected {len(selected)} unique working domains; add more markets and rerun")


if __name__ == "__main__":
    main()
