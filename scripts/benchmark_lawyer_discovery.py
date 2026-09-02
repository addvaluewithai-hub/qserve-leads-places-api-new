#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
import math
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import urlparse

import requests

SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"
GROUNDING_URL = "https://mapstools.googleapis.com/mcp"
OUT = Path("out/lawyer-discovery-benchmark")

# Ten deliberately diverse non-Texas markets for a representative benchmark.
MARKETS = [
    "Phoenix, AZ",
    "Tampa, FL",
    "Charlotte, NC",
    "Columbus, OH",
    "Indianapolis, IN",
    "Nashville, TN",
    "Kansas City, MO",
    "Denver, CO",
    "Sacramento, CA",
    "Richmond, VA",
]

MIN_RATING = 4.7
PAGE_SIZE = 20
FIELD_MASK = ",".join([
    "places.id",
    "places.displayName",
    "places.formattedAddress",
    "places.businessStatus",
])

URL_RE = re.compile(r"https?://[^\s<>()\[\]{}]+", re.I)
RATING_RE = re.compile(r"\((\d(?:\.\d)?)\s*[★⭐]\s*,\s*([\d,]+)\)")


def api_post(url: str, *, key: str, body: dict, field_mask: str | None = None, timeout: int = 60):
    headers = {"X-Goog-Api-Key": key, "Content-Type": "application/json"}
    if field_mask:
        headers["X-Goog-FieldMask"] = field_mask
    response = requests.post(url, headers=headers, json=body, timeout=timeout)
    return response


def clean_domain(url: str | None) -> str | None:
    if not url:
        return None
    try:
        host = (urlparse(url).hostname or "").lower().strip(".")
        if host.startswith("www."):
            host = host[4:]
        return host or None
    except Exception:
        return None


def external_urls(summary: str) -> list[str]:
    found = []
    seen = set()
    for raw in URL_RE.findall(summary or ""):
        url = raw.rstrip(".,;:!?\"'")
        domain = clean_domain(url)
        if not domain:
            continue
        if domain == "google.com" or domain.endswith(".google.com") or domain.endswith("googleusercontent.com"):
            continue
        if url not in seen:
            found.append(url)
            seen.add(url)
    return found


def parse_grounding_response(payload: dict, expected_place_id: str) -> dict:
    result = payload.get("result") or {}
    structured = result.get("structuredContent") or {}
    summary = structured.get("summary") or ""
    places = structured.get("places") or []
    returned_ids = [p.get("id") for p in places if p.get("id")]
    identity_match = expected_place_id in returned_ids

    urls = external_urls(summary)
    website = urls[0] if urls else None
    domain = clean_domain(website)

    rating = None
    review_count = None
    match = RATING_RE.search(summary)
    if match:
        rating = float(match.group(1))
        review_count = int(match.group(2).replace(",", ""))

    maps_url = None
    for place in places:
        if place.get("id") == expected_place_id:
            maps_url = ((place.get("googleMapsLinks") or {}).get("placeUrl"))
            break

    return {
        "grounding_summary": summary,
        "grounding_returned_place_ids": returned_ids,
        "grounding_identity_match": identity_match,
        "website": website,
        "website_domain": domain,
        "rating": rating,
        "review_count": review_count,
        "google_maps_source": maps_url,
    }


def ground_one(key: str, candidate: dict) -> dict:
    query = (
        f"{candidate['name']}, {candidate['address']} official website rating review count"
    )
    body = {
        "method": "tools/call",
        "params": {
            "name": "search_places",
            "arguments": {
                "textQuery": query,
                "languageCode": "en",
                "regionCode": "US",
            },
        },
        "jsonrpc": "2.0",
        "id": candidate["place_id"],
    }

    last_error = None
    for attempt in range(4):
        try:
            response = api_post(GROUNDING_URL, key=key, body=body, timeout=90)
            if response.status_code == 200:
                parsed = parse_grounding_response(response.json(), candidate["place_id"])
                return {**candidate, **parsed, "grounding_http_status": 200, "grounding_error": None}
            last_error = f"HTTP {response.status_code}: {response.text[:600]}"
            if response.status_code not in {429, 500, 502, 503, 504}:
                break
        except Exception as exc:
            last_error = f"{type(exc).__name__}: {exc}"
        time.sleep(1.5 * (attempt + 1))

    return {
        **candidate,
        "grounding_summary": "",
        "grounding_returned_place_ids": [],
        "grounding_identity_match": False,
        "website": None,
        "website_domain": None,
        "rating": None,
        "review_count": None,
        "google_maps_source": None,
        "grounding_http_status": None,
        "grounding_error": last_error,
    }


def search_market(key: str, market: str) -> tuple[dict, list[dict]]:
    body = {
        "textQuery": f"lawyer in {market}",
        "includedType": "lawyer",
        "strictTypeFiltering": True,
        "minRating": MIN_RATING,
        "pageSize": PAGE_SIZE,
        "regionCode": "US",
        "languageCode": "en",
    }
    response = api_post(SEARCH_URL, key=key, body=body, field_mask=FIELD_MASK, timeout=60)
    meta = {
        "market": market,
        "http_status": response.status_code,
        "result_count": 0,
        "error": None,
    }
    if response.status_code != 200:
        meta["error"] = response.text[:1200]
        return meta, []

    payload = response.json()
    rows = []
    for place in payload.get("places") or []:
        display = place.get("displayName") or {}
        place_id = place.get("id")
        if not place_id:
            continue
        rows.append({
            "place_id": place_id,
            "name": display.get("text") or "Unnamed business",
            "address": place.get("formattedAddress") or "",
            "business_status": place.get("businessStatus"),
            "source_market": market,
        })
    meta["result_count"] = len(rows)
    return meta, rows


def dedupe_place_ids(rows: list[dict]) -> list[dict]:
    by_id: dict[str, dict] = {}
    for row in rows:
        current = by_id.get(row["place_id"])
        if current is None:
            current = dict(row)
            current["matched_markets"] = [row["source_market"]]
            by_id[row["place_id"]] = current
        elif row["source_market"] not in current["matched_markets"]:
            current["matched_markets"].append(row["source_market"])
    return list(by_id.values())


def valid_working_leads(rows: list[dict], min_reviews: int) -> list[dict]:
    valid = []
    for row in rows:
        if row.get("business_status") != "OPERATIONAL":
            continue
        if not row.get("grounding_identity_match"):
            continue
        if not row.get("website_domain"):
            continue
        if float(row.get("rating") or 0) < MIN_RATING:
            continue
        if int(row.get("review_count") or 0) < min_reviews:
            continue
        valid.append(row)

    # Working-set unit is one website/domain, not one branch/location.
    best_by_domain: dict[str, dict] = {}
    for row in valid:
        domain = row["website_domain"]
        existing = best_by_domain.get(domain)
        if existing is None or int(row.get("review_count") or 0) > int(existing.get("review_count") or 0):
            best_by_domain[domain] = row
    return list(best_by_domain.values())


def write_csv(path: Path, rows: list[dict]) -> None:
    fields = [
        "place_id", "name", "address", "business_status", "source_market", "matched_markets",
        "grounding_identity_match", "website", "website_domain", "rating", "review_count",
        "google_maps_source", "grounding_http_status", "grounding_error", "grounding_summary",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            out = dict(row)
            if isinstance(out.get("matched_markets"), list):
                out["matched_markets"] = " | ".join(out["matched_markets"])
            writer.writerow(out)


def main() -> None:
    key = os.getenv("GOOGLE_API_KEY")
    if not key:
        raise SystemExit("GOOGLE_API_KEY is missing")
    OUT.mkdir(parents=True, exist_ok=True)

    search_meta = []
    raw_rows = []
    for market in MARKETS:
        meta, rows = search_market(key, market)
        search_meta.append(meta)
        raw_rows.extend(rows)
        print(f"SEARCH {market}: status={meta['http_status']} results={meta['result_count']}")

    unique_rows = dedupe_place_ids(raw_rows)
    operational_rows = [r for r in unique_rows if r.get("business_status") == "OPERATIONAL"]

    grounded = []
    # 4 workers stays comfortably below the documented 300 search_places queries/minute quota.
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(ground_one, key, row) for row in operational_rows]
        for index, future in enumerate(as_completed(futures), 1):
            row = future.result()
            grounded.append(row)
            print(
                f"GROUND {index}/{len(futures)}: {row['name']} "
                f"match={row.get('grounding_identity_match')} website={bool(row.get('website'))} "
                f"rating={row.get('rating')} reviews={row.get('review_count')}"
            )

    # Restore deterministic order for artifact inspection.
    grounded.sort(key=lambda r: (r.get("source_market") or "", r.get("name") or ""))

    threshold_yields = {}
    for threshold in (10, 20, 50):
        working = valid_working_leads(grounded, threshold)
        threshold_yields[str(threshold)] = {
            "unique_domains": len(working),
            "projected_text_search_requests_for_1000": (
                math.ceil(1000 * len(MARKETS) / len(working)) if working else None
            ),
            "projected_grounding_calls_for_1000": (
                math.ceil(1000 * len(operational_rows) / len(working)) if working else None
            ),
        }
        (OUT / f"working_leads_min_reviews_{threshold}.json").write_text(
            json.dumps(working, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    summary = {
        "benchmark": "10-request generic lawyer discovery",
        "markets": MARKETS,
        "min_rating_search_filter": MIN_RATING,
        "page_size": PAGE_SIZE,
        "text_search_requests_attempted": len(MARKETS),
        "text_search_requests_successful": sum(1 for m in search_meta if m["http_status"] == 200),
        "raw_places_returned": len(raw_rows),
        "unique_place_ids": len(unique_rows),
        "operational_unique_place_ids": len(operational_rows),
        "grounding_calls_attempted": len(operational_rows),
        "grounding_identity_matches": sum(1 for r in grounded if r.get("grounding_identity_match")),
        "websites_resolved_with_identity_match": sum(
            1 for r in grounded if r.get("grounding_identity_match") and r.get("website_domain")
        ),
        "unique_website_domains_resolved": len({
            r["website_domain"] for r in grounded
            if r.get("grounding_identity_match") and r.get("website_domain")
        }),
        "rating_and_review_count_parsed": sum(
            1 for r in grounded if r.get("rating") is not None and r.get("review_count") is not None
        ),
        "working_set_yield_by_min_reviews": threshold_yields,
        "notes": [
            "Text Search requests use only ID, display name, formatted address and business status with minRating=4.7.",
            "No Place Details requests and no review text are used.",
            "Grounding website data is trusted only when the Grounding response contains the same Place ID.",
            "One working lead is deduped by verified website domain, so multiple offices of the same firm count once.",
            "Projection assumes roughly linear yield; production should add a safety margin for market overlap and saturation.",
        ],
    }

    (OUT / "search_requests.json").write_text(json.dumps(search_meta, indent=2), encoding="utf-8")
    (OUT / "raw_places.json").write_text(json.dumps(raw_rows, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT / "grounded_results.json").write_text(json.dumps(grounded, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    write_csv(OUT / "grounded_results.csv", grounded)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
