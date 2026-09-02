#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import math
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"
DETAILS_URL = "https://places.googleapis.com/v1/places/{place_id}"
SEARCH_FIELDS = ",".join([
    "places.id",
    "places.displayName",
    "places.formattedAddress",
    "places.priceLevel",
    "places.rating",
    "places.userRatingCount",
    "places.nationalPhoneNumber",
    "places.websiteUri",
    "places.googleMapsUri",
    "places.businessStatus",
    "places.location",
    "places.primaryType",
    "places.types",
    "places.regularOpeningHours",
])
DETAIL_FIELDS = "id,reviews"


def api_json(url: str, *, api_key: str, body: dict | None = None, field_mask: str | None = None):
    headers = {"X-Goog-Api-Key": api_key}
    data = None
    method = "GET"
    if body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(body).encode("utf-8")
        method = "POST"
    if field_mask:
        headers["X-Goog-FieldMask"] = field_mask
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Google Places HTTP {exc.code}: {detail[:800]}") from exc


def load_campaign(campaign_id: str) -> dict:
    path = ROOT / "campaigns" / f"{campaign_id}.json"
    if not path.exists():
        raise SystemExit(f"Campaign config not found: {path}")
    config = json.loads(path.read_text(encoding="utf-8"))
    if config.get("id") != campaign_id:
        raise SystemExit(f"Campaign id mismatch in {path}")
    return config


def parse_time(value: str | None):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def days_since(value: str | None):
    dt = parse_time(value)
    if not dt:
        return None
    return max(0, int((datetime.now(timezone.utc) - dt.astimezone(timezone.utc)).total_seconds() // 86400))


def normalize_place(place: dict, area: str, query: str, term: str) -> dict:
    location = place.get("location") or {}
    opening = place.get("regularOpeningHours") or {}
    display = place.get("displayName") or {}
    return {
        "id": place.get("id"),
        "name": display.get("text") or "Unnamed business",
        "price_level": place.get("priceLevel") or "PRICE_LEVEL_UNSPECIFIED",
        "rating": place.get("rating"),
        "user_rating_count": place.get("userRatingCount") or 0,
        "business_status": place.get("businessStatus"),
        "phone": place.get("nationalPhoneNumber"),
        "website": place.get("websiteUri"),
        "google_maps_url": place.get("googleMapsUri"),
        "address": place.get("formattedAddress"),
        "latitude": location.get("latitude"),
        "longitude": location.get("longitude"),
        "primary_type": place.get("primaryType"),
        "types": json.dumps(place.get("types") or [], ensure_ascii=False),
        "opening_hours": json.dumps(opening, ensure_ascii=False),
        "source_area": area,
        "source_query": query,
        "source_term": term,
        "discovered_at": datetime.now(timezone.utc).isoformat(),
    }


def coarse_pass(row: dict, quality: dict) -> tuple[bool, list[str]]:
    reasons = []
    allowed = quality.get("allowed_business_statuses") or []
    if allowed and row.get("business_status") not in allowed:
        reasons.append("business_not_operational")
    if float(row.get("rating") or 0) < float(quality.get("min_rating") or 0):
        reasons.append("rating_below_minimum")
    if int(row.get("user_rating_count") or 0) < int(quality.get("min_reviews") or 0):
        reasons.append("review_count_below_minimum")
    if quality.get("require_phone") and not row.get("phone"):
        reasons.append("missing_phone")
    if quality.get("require_website") and not row.get("website"):
        reasons.append("missing_website")
    allowed_prices = quality.get("allowed_price_levels") or []
    if allowed_prices and row.get("price_level") not in allowed_prices:
        reasons.append("price_level_not_allowed")
    return not reasons, reasons


def enrich_reviews(row: dict, api_key: str, quality: dict) -> None:
    place_id = urllib.parse.quote(str(row["id"]), safe="")
    payload = api_json(DETAILS_URL.format(place_id=place_id), api_key=api_key, field_mask=DETAIL_FIELDS)
    reviews = payload.get("reviews") or []
    published = [review.get("publishTime") for review in reviews if review.get("publishTime")]
    latest = max(published) if published else None
    recency_days = int(quality.get("review_recency_days") or 365)
    recent = [value for value in published if (days_since(value) is not None and days_since(value) <= recency_days)]
    ratings = [float(r.get("rating")) for r in reviews if r.get("rating") is not None]
    row.update({
        "latest_sampled_review_at": latest,
        "latest_sampled_review_age_days": days_since(latest),
        "sampled_review_count": len(reviews),
        "recent_sampled_reviews": len(recent),
        "sampled_review_avg": round(sum(ratings) / len(ratings), 2) if ratings else None,
        "review_signal_checked_at": datetime.now(timezone.utc).isoformat(),
        "review_signal_note": "Google Places returns at most 5 reviews sorted by relevance; this is a sampled freshness signal, not a complete review history.",
    })


def clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def score(row: dict, campaign: dict) -> int:
    weights = campaign.get("scoring") or {}
    quality = campaign.get("quality") or {}
    total = 0.0
    rating = float(row.get("rating") or 0)
    total += clamp01((rating - 3.5) / 1.5) * float(weights.get("rating_weight") or 0)
    reviews = max(0, int(row.get("user_rating_count") or 0))
    total += clamp01(math.log10(reviews + 1) / math.log10(1001)) * float(weights.get("review_volume_weight") or 0)
    max_age = max(1, int(quality.get("review_recency_days") or 365))
    age = row.get("latest_sampled_review_age_days")
    freshness = 0.0 if age is None else clamp01(1 - (float(age) / max_age))
    total += freshness * float(weights.get("review_freshness_weight") or 0)
    total += clamp01(float(row.get("recent_sampled_reviews") or 0) / 5.0) * float(weights.get("recent_review_sample_weight") or 0)
    total += (1 if row.get("website") else 0) * float(weights.get("website_weight") or 0)
    total += (1 if row.get("phone") else 0) * float(weights.get("phone_weight") or 0)
    price_rank = {
        "PRICE_LEVEL_INEXPENSIVE": 0.25,
        "PRICE_LEVEL_MODERATE": 0.5,
        "PRICE_LEVEL_EXPENSIVE": 0.75,
        "PRICE_LEVEL_VERY_EXPENSIVE": 1.0,
    }.get(row.get("price_level"), 0.0)
    total += price_rank * float(weights.get("price_weight") or 0)
    return max(0, min(100, round(total)))


def final_qualification(row: dict, campaign: dict, coarse_reasons: list[str]) -> tuple[bool, str]:
    reasons = list(coarse_reasons)
    quality = campaign.get("quality") or {}
    min_recent = int(quality.get("min_recent_sampled_reviews") or 0)
    if min_recent and int(row.get("recent_sampled_reviews") or 0) < min_recent:
        reasons.append("no_recent_review_in_returned_sample")
    qualified = not reasons
    return qualified, "qualified" if qualified else ",".join(reasons)


def search_campaign(campaign: dict, api_key: str, limit: int, max_pages: int) -> list[dict]:
    google = campaign["google"]
    quality = campaign.get("quality") or {}
    seen: dict[str, dict] = {}
    stop_after = max(limit * 4, limit + 20)

    for area in google.get("areas") or []:
        label = area["label"]
        for term in area.get("terms") or [label]:
            for query in google.get("queries") or [google.get("included_type")]:
                page_token = None
                for _ in range(max_pages):
                    body = {
                        "textQuery": f"{query} in {term}",
                        "includedType": google.get("included_type"),
                        "strictTypeFiltering": bool(google.get("strict_type_filtering", True)),
                        "pageSize": 20,
                        "regionCode": google.get("region_code"),
                        "languageCode": google.get("language_code", "en"),
                    }
                    if page_token:
                        body["pageToken"] = page_token
                    payload = api_json(SEARCH_URL, api_key=api_key, body=body, field_mask=SEARCH_FIELDS)
                    for place in payload.get("places") or []:
                        place_id = place.get("id")
                        if not place_id:
                            continue
                        row = normalize_place(place, label, query, term)
                        passed, coarse_reasons = coarse_pass(row, quality)
                        row["coarse_qualified"] = passed
                        row["coarse_reasons"] = coarse_reasons
                        current = seen.get(place_id)
                        if current is None or (passed and not current.get("coarse_qualified")):
                            seen[place_id] = row
                    page_token = payload.get("nextPageToken")
                    if not page_token:
                        break
                    time.sleep(1.5)
                if sum(1 for r in seen.values() if r.get("coarse_qualified")) >= stop_after:
                    break
            if sum(1 for r in seen.values() if r.get("coarse_qualified")) >= stop_after:
                break
        if sum(1 for r in seen.values() if r.get("coarse_qualified")) >= stop_after:
            break
    return list(seen.values())


def write_outputs(campaign: dict, rows: list[dict], out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    qualified = [r for r in rows if r.get("qualified")]
    (out_dir / "all_candidates.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    (out_dir / "leads.json").write_text(json.dumps(qualified, ensure_ascii=False, indent=2), encoding="utf-8")
    (out_dir / "campaign.json").write_text(json.dumps(campaign, ensure_ascii=False, indent=2), encoding="utf-8")
    fields = [
        "id", "name", "rating", "user_rating_count", "business_status", "phone", "website",
        "google_maps_url", "address", "primary_type", "source_area", "source_query", "source_term",
        "quality_score", "latest_sampled_review_at", "latest_sampled_review_age_days",
        "sampled_review_count", "recent_sampled_reviews", "sampled_review_avg", "qualification_reason",
    ]
    with (out_dir / "leads.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(qualified)
    summary = {
        "campaign": campaign["id"],
        "discovered": len(rows),
        "coarse_qualified": sum(1 for r in rows if r.get("coarse_qualified")),
        "qualified": len(qualified),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a reusable Google Places lead campaign")
    parser.add_argument("--campaign", required=True)
    parser.add_argument("--limit", type=int, default=int(os.getenv("TARGET_LIMIT", "100")))
    parser.add_argument("--max-pages", type=int, default=2)
    parser.add_argument("--out-dir", default=None)
    args = parser.parse_args()

    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise SystemExit("GOOGLE_API_KEY is required")
    campaign = load_campaign(args.campaign)
    rows = search_campaign(campaign, api_key, max(1, args.limit), max(1, args.max_pages))

    coarse = [r for r in rows if r.get("coarse_qualified")]
    coarse.sort(key=lambda r: (float(r.get("rating") or 0), int(r.get("user_rating_count") or 0)), reverse=True)
    for index, row in enumerate(coarse):
        if index >= max(args.limit * 2, args.limit + 10):
            break
        try:
            enrich_reviews(row, api_key, campaign.get("quality") or {})
        except Exception as exc:
            row.update({
                "latest_sampled_review_at": None,
                "latest_sampled_review_age_days": None,
                "sampled_review_count": 0,
                "recent_sampled_reviews": 0,
                "sampled_review_avg": None,
                "review_signal_checked_at": datetime.now(timezone.utc).isoformat(),
                "review_signal_note": f"review enrichment failed: {exc}",
            })
        row["quality_score"] = score(row, campaign)
        row["qualified"], row["qualification_reason"] = final_qualification(row, campaign, row.get("coarse_reasons") or [])

    for row in rows:
        if "qualified" not in row:
            row["quality_score"] = score(row, campaign)
            row["qualified"] = False
            row["qualification_reason"] = ",".join(row.get("coarse_reasons") or ["not_enriched"])

    qualified = sorted([r for r in rows if r.get("qualified")], key=lambda r: r.get("quality_score", 0), reverse=True)[: args.limit]
    qualified_ids = {r["id"] for r in qualified}
    for row in rows:
        row["qualified"] = row.get("id") in qualified_ids
        if row.get("coarse_qualified") and row.get("id") not in qualified_ids and row.get("qualification_reason") == "qualified":
            row["qualification_reason"] = "qualified_but_below_campaign_limit"

    out_dir = Path(args.out_dir) if args.out_dir else ROOT / "out" / campaign["id"]
    write_outputs(campaign, rows, out_dir)


if __name__ == "__main__":
    main()
