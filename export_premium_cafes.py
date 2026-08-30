#!/usr/bin/env python3
"""Export non-cheap cafe/restaurant leads from Google Places API (New).

GitHub Actions entrypoint. Uses GOOGLE_API_KEY from Actions secrets and writes
CSV + JSON artifacts for outreach.

Current targeting rule:
- Include known price levels: MODERATE, EXPENSIVE, VERY_EXPENSIVE.
- Exclude INEXPENSIVE and UNSPECIFIED.
- Keep results physically near the October / Sheikh Zayed search area.
"""

from __future__ import annotations

import csv
import json
import math
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

ENDPOINT = "https://places.googleapis.com/v1/places:searchText"
PRICE_LEVELS = [
    "PRICE_LEVEL_MODERATE",
    "PRICE_LEVEL_EXPENSIVE",
    "PRICE_LEVEL_VERY_EXPENSIVE",
]
TARGET_LIMIT = int(os.getenv("TARGET_LIMIT", "100"))
OUT_DIR = Path(os.getenv("OUT_DIR", "out"))

# Main October / Sheikh Zayed coverage. Radius is used both for Google biasing
# and for our own hard distance filter, so open-text queries cannot drift to USA
# or unrelated global results.
CENTERS = [
    (29.9724785, 30.9576332, 17000, "6 October core"),
    (30.0131, 30.9841, 17000, "Sheikh Zayed west"),
    (30.0451, 31.0003, 15000, "Capital Business Park / Zayed"),
    (30.0075, 30.9698, 15000, "Arkan / Americana Plaza"),
    (30.0063, 30.9742, 15000, "Mall of Arabia / Zayed"),
    (29.9717, 31.0167, 15000, "Mall of Egypt / October"),
    (29.9946, 30.9657, 14000, "Palm Hills / Zayed"),
]

SEARCHES: list[dict[str, str | None]] = [
    # Strict cafe / coffee shop pass first.
    {"query": "cafe in 6th of October City, Giza, Egypt", "type": "cafe", "label": "strict cafe"},
    {"query": "coffee shop in 6th of October City, Giza, Egypt", "type": "cafe", "label": "strict cafe"},
    {"query": "premium cafe in 6th of October City, Giza, Egypt", "type": "cafe", "label": "strict cafe"},
    {"query": "كافيهات 6 أكتوبر", "type": "cafe", "label": "strict cafe"},
    {"query": "cafe in Sheikh Zayed City, Giza, Egypt", "type": "cafe", "label": "strict cafe"},
    {"query": "coffee shop in Sheikh Zayed City, Giza, Egypt", "type": "cafe", "label": "strict cafe"},
    {"query": "premium cafe in Sheikh Zayed City, Giza, Egypt", "type": "cafe", "label": "strict cafe"},
    {"query": "كافيهات الشيخ زايد", "type": "cafe", "label": "strict cafe"},

    # Restaurant / restaurant-cafe pass for QServe outreach.
    {"query": "restaurant in 6th of October City, Giza, Egypt", "type": "restaurant", "label": "restaurant"},
    {"query": "premium restaurant in 6th of October City, Giza, Egypt", "type": "restaurant", "label": "restaurant"},
    {"query": "restaurant and cafe in 6th of October City, Giza, Egypt", "type": "restaurant", "label": "restaurant/cafe"},
    {"query": "lounge cafe restaurant in 6th of October City, Giza, Egypt", "type": "restaurant", "label": "lounge/cafe"},
    {"query": "restaurant in Sheikh Zayed City, Giza, Egypt", "type": "restaurant", "label": "restaurant"},
    {"query": "premium restaurant in Sheikh Zayed City, Giza, Egypt", "type": "restaurant", "label": "restaurant"},
    {"query": "restaurant and cafe in Sheikh Zayed City, Giza, Egypt", "type": "restaurant", "label": "restaurant/cafe"},
    {"query": "lounge cafe restaurant in Sheikh Zayed City, Giza, Egypt", "type": "restaurant", "label": "lounge/cafe"},
    {"query": "مطاعم 6 أكتوبر", "type": "restaurant", "label": "restaurant"},
    {"query": "مطاعم الشيخ زايد", "type": "restaurant", "label": "restaurant"},

    # Mall/plaza passes. These keep high commercial intent and help reach 100.
    {"query": "cafes Mall of Arabia 6th of October", "type": None, "label": "mall/plaza"},
    {"query": "restaurants Mall of Arabia 6th of October", "type": None, "label": "mall/plaza"},
    {"query": "cafes Mall of Egypt 6th of October", "type": None, "label": "mall/plaza"},
    {"query": "restaurants Mall of Egypt 6th of October", "type": None, "label": "mall/plaza"},
    {"query": "cafes Arkan Plaza Sheikh Zayed", "type": None, "label": "mall/plaza"},
    {"query": "restaurants Arkan Plaza Sheikh Zayed", "type": None, "label": "mall/plaza"},
    {"query": "cafes Capital Business Park Sheikh Zayed", "type": None, "label": "mall/plaza"},
    {"query": "restaurants Capital Business Park Sheikh Zayed", "type": None, "label": "mall/plaza"},
    {"query": "cafes Palm Hills 6th of October", "type": None, "label": "mall/plaza"},
    {"query": "restaurants Palm Hills 6th of October", "type": None, "label": "mall/plaza"},
]

HOSPITALITY_TYPE_HINTS = {
    "bar",
    "bar_and_grill",
    "bakery",
    "breakfast_restaurant",
    "brunch_restaurant",
    "cafe",
    "coffee_shop",
    "dessert_restaurant",
    "fast_food_restaurant",
    "fine_dining_restaurant",
    "food",
    "ice_cream_shop",
    "meal_delivery",
    "meal_takeaway",
    "restaurant",
    "seafood_restaurant",
    "steak_house",
    "sushi_restaurant",
}

FIELD_MASK = ",".join(
    [
        "places.id",
        "places.displayName",
        "places.formattedAddress",
        "places.priceLevel",
        "places.rating",
        "places.userRatingCount",
        "places.nationalPhoneNumber",
        "places.internationalPhoneNumber",
        "places.websiteUri",
        "places.googleMapsUri",
        "places.businessStatus",
        "places.location",
        "places.primaryType",
        "places.types",
        "places.regularOpeningHours.weekdayDescriptions",
        "nextPageToken",
    ]
)


def haversine_meters(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    radius_m = 6_371_000
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lam = math.radians(lng2 - lng1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lam / 2) ** 2
    return 2 * radius_m * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def is_inside_target_area(place: dict[str, Any]) -> bool:
    location = place.get("location") or {}
    lat = location.get("latitude")
    lng = location.get("longitude")
    if not isinstance(lat, (int, float)) or not isinstance(lng, (int, float)):
        return False
    return any(haversine_meters(lat, lng, center_lat, center_lng) <= radius for center_lat, center_lng, radius, _ in CENTERS)


def is_hospitality_place(place: dict[str, Any]) -> bool:
    primary_type = place.get("primaryType") or ""
    types = set(place.get("types") or [])
    return primary_type in HOSPITALITY_TYPE_HINTS or bool(types.intersection(HOSPITALITY_TYPE_HINTS))


def call_google(api_key: str, body: dict[str, Any]) -> dict[str, Any]:
    request = urllib.request.Request(
        ENDPOINT,
        data=json.dumps(body).encode("utf-8"),
        method="POST",
        headers={
            "Content-Type": "application/json",
            "X-Goog-Api-Key": api_key,
            "X-Goog-FieldMask": FIELD_MASK,
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace")
        print(f"Google Places API returned HTTP {exc.code}", file=sys.stderr)
        print(error_body, file=sys.stderr)
        raise


def normalize_place(place: dict[str, Any], search: dict[str, str | None], area: str) -> dict[str, Any]:
    location = place.get("location") or {}
    hours = place.get("regularOpeningHours", {}).get("weekdayDescriptions") or []
    return {
        "id": place.get("id", ""),
        "name": place.get("displayName", {}).get("text", ""),
        "price_level": place.get("priceLevel", "PRICE_LEVEL_UNSPECIFIED"),
        "rating": place.get("rating", ""),
        "user_rating_count": place.get("userRatingCount", ""),
        "business_status": place.get("businessStatus", ""),
        "phone": place.get("nationalPhoneNumber") or place.get("internationalPhoneNumber", ""),
        "website": place.get("websiteUri", ""),
        "google_maps_url": place.get("googleMapsUri", ""),
        "address": place.get("formattedAddress", ""),
        "latitude": location.get("latitude", ""),
        "longitude": location.get("longitude", ""),
        "primary_type": place.get("primaryType", ""),
        "types": "; ".join(place.get("types", [])),
        "opening_hours": " | ".join(hours),
        "source_query": search["query"],
        "source_type": search["type"] or "open_text",
        "source_label": search["label"],
        "source_area": area,
    }


def search_batch(api_key: str, search: dict[str, str | None], center: tuple[float, float, int, str]) -> list[dict[str, Any]]:
    lat, lng, radius, area = center
    body: dict[str, Any] = {
        "textQuery": search["query"],
        "pageSize": 20,
        "priceLevels": PRICE_LEVELS,
        "locationBias": {
            "circle": {
                "center": {"latitude": lat, "longitude": lng},
                "radius": radius,
            }
        },
    }
    if search["type"]:
        body["includedType"] = search["type"]
        body["strictTypeFiltering"] = True

    results: list[dict[str, Any]] = []
    page = 1
    while page <= 5 and len(results) < TARGET_LIMIT:
        payload = call_google(api_key, body)
        places = payload.get("places", [])
        print(f"{search['label']} | {search['query']!r} / {area} / page {page}: {len(places)} place(s)")
        results.extend(normalize_place(place, search, area) for place in places)
        token = payload.get("nextPageToken")
        if not token:
            break
        body["pageToken"] = token
        page += 1
        time.sleep(2)
    return results


def sort_key(place: dict[str, Any]) -> tuple[int, int, float, int, str]:
    price_score_map = {
        "PRICE_LEVEL_VERY_EXPENSIVE": 3,
        "PRICE_LEVEL_EXPENSIVE": 2,
        "PRICE_LEVEL_MODERATE": 1,
    }
    price_score = price_score_map.get(place["price_level"], 0)
    cafe_score = 2 if "cafe" in place.get("types", "") or "coffee_shop" in place.get("types", "") else 0
    try:
        rating = float(place["rating"] or 0)
    except ValueError:
        rating = 0.0
    try:
        count = int(place["user_rating_count"] or 0)
    except ValueError:
        count = 0
    return (price_score, cafe_score, rating, count, place["name"])


def write_outputs(leads: list[dict[str, Any]]) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    csv_path = OUT_DIR / "noncheap_october_leads.csv"
    json_path = OUT_DIR / "noncheap_october_leads.json"
    fields = [
        "name", "price_level", "rating", "user_rating_count", "business_status",
        "phone", "website", "google_maps_url", "address", "latitude", "longitude",
        "primary_type", "types", "opening_hours", "source_label", "source_query",
        "source_type", "source_area", "id",
    ]
    with csv_path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(leads)
    json_path.write_text(json.dumps(leads, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nWrote {csv_path}")
    print(f"Wrote {json_path}")


def main() -> int:
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        print("ERROR: GOOGLE_API_KEY is not set.", file=sys.stderr)
        return 2
    print(f"Searching for up to {TARGET_LIMIT} non-cheap cafe/restaurant leads in October/Zayed")
    print("Included price levels:", ", ".join(PRICE_LEVELS))
    print("Excluded price levels: PRICE_LEVEL_INEXPENSIVE, PRICE_LEVEL_UNSPECIFIED")

    by_id: dict[str, dict[str, Any]] = {}
    skipped_outside_area = 0
    skipped_non_hospitality = 0
    for search in SEARCHES:
        for center in CENTERS:
            for place in search_batch(api_key, search, center):
                if place.get("price_level") not in PRICE_LEVELS:
                    continue
                raw_place = {
                    "location": {"latitude": place.get("latitude"), "longitude": place.get("longitude")},
                    "primaryType": place.get("primary_type"),
                    "types": place.get("types", "").split("; ") if place.get("types") else [],
                }
                if not is_inside_target_area(raw_place):
                    skipped_outside_area += 1
                    continue
                if not is_hospitality_place(raw_place):
                    skipped_non_hospitality += 1
                    continue
                key = place["id"] or place["google_maps_url"] or place["name"]
                if key and key not in by_id:
                    by_id[key] = place
            if len(by_id) >= TARGET_LIMIT:
                break
        if len(by_id) >= TARGET_LIMIT:
            break

    leads = sorted(by_id.values(), key=sort_key, reverse=True)[:TARGET_LIMIT]
    write_outputs(leads)

    counts_by_price: dict[str, int] = {}
    for lead in leads:
        counts_by_price[lead["price_level"]] = counts_by_price.get(lead["price_level"], 0) + 1

    print(f"\nUnique non-cheap leads found: {len(leads)}")
    print("Counts by price level:", json.dumps(counts_by_price, ensure_ascii=False, sort_keys=True))
    print(f"Skipped outside October/Zayed radius: {skipped_outside_area}")
    print(f"Skipped non-hospitality results: {skipped_non_hospitality}")
    for index, lead in enumerate(leads, start=1):
        print(
            f"{index:03d}. {lead['name']} | {lead['price_level']} | {lead['primary_type']} | "
            f"rating={lead['rating']} reviews={lead['user_rating_count']} | {lead['phone']} | {lead['google_maps_url']}"
        )

    if len(leads) < TARGET_LIMIT:
        print(
            f"\nNOTE: Google returned only {len(leads)} unique non-cheap leads with known "
            "MODERATE/EXPENSIVE/VERY_EXPENSIVE pricing in the searched October/Zayed area."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
