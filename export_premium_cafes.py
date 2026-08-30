#!/usr/bin/env python3
"""Export premium cafe/restaurant leads from Google Places API (New).

GitHub Actions entrypoint. Uses GOOGLE_API_KEY from Actions secrets and writes
CSV + JSON artifacts for outreach.
"""

from __future__ import annotations

import csv
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

ENDPOINT = "https://places.googleapis.com/v1/places:searchText"
PRICE_LEVELS = ["PRICE_LEVEL_EXPENSIVE", "PRICE_LEVEL_VERY_EXPENSIVE"]
TARGET_LIMIT = int(os.getenv("TARGET_LIMIT", "100"))
OUT_DIR = Path(os.getenv("OUT_DIR", "out"))

CENTERS = [
    (29.9724785, 30.9576332, 15000, "6 October core"),
    (30.0131, 30.9841, 15000, "Sheikh Zayed west"),
    (30.0451, 31.0003, 15000, "Capital Business Park / Zayed"),
    (30.0075, 30.9698, 15000, "Arkan / Americana Plaza"),
    (30.0063, 30.9742, 15000, "Mall of Arabia / Zayed"),
    (29.9717, 31.0167, 15000, "Mall of Egypt / October"),
]

SEARCHES: list[dict[str, str | None]] = [
    # Strict cafe first: this is the purest interpretation of the request.
    {"query": "cafe in 6th of October City, Giza, Egypt", "type": "cafe", "label": "strict cafe"},
    {"query": "coffee shop in 6th of October City, Giza, Egypt", "type": "cafe", "label": "strict cafe"},
    {"query": "premium cafe in 6th of October City, Giza, Egypt", "type": "cafe", "label": "strict cafe"},
    {"query": "cafe in Sheikh Zayed City, Giza, Egypt", "type": "cafe", "label": "strict cafe"},
    {"query": "coffee shop in Sheikh Zayed City, Giza, Egypt", "type": "cafe", "label": "strict cafe"},
    {"query": "premium cafe in Sheikh Zayed City, Giza, Egypt", "type": "cafe", "label": "strict cafe"},
    # Broader premium hospitality venues for outreach when Google has too few high-price cafes.
    {"query": "restaurant in 6th of October City, Giza, Egypt", "type": "restaurant", "label": "restaurant"},
    {"query": "premium restaurant in 6th of October City, Giza, Egypt", "type": "restaurant", "label": "restaurant"},
    {"query": "restaurant and cafe in 6th of October City, Giza, Egypt", "type": "restaurant", "label": "restaurant/cafe"},
    {"query": "lounge cafe restaurant in 6th of October City, Giza, Egypt", "type": "restaurant", "label": "lounge/cafe"},
    {"query": "restaurant in Sheikh Zayed City, Giza, Egypt", "type": "restaurant", "label": "restaurant"},
    {"query": "premium restaurant in Sheikh Zayed City, Giza, Egypt", "type": "restaurant", "label": "restaurant"},
    {"query": "restaurant and cafe in Sheikh Zayed City, Giza, Egypt", "type": "restaurant", "label": "restaurant/cafe"},
    {"query": "lounge cafe restaurant in Sheikh Zayed City, Giza, Egypt", "type": "restaurant", "label": "lounge/cafe"},
    # No strict type fallback, but still with high priceLevels.
    {"query": "expensive cafe 6th of October City Egypt", "type": None, "label": "open text"},
    {"query": "expensive restaurant 6th of October City Egypt", "type": None, "label": "open text"},
    {"query": "expensive cafe Sheikh Zayed City Egypt", "type": None, "label": "open text"},
    {"query": "expensive restaurant Sheikh Zayed City Egypt", "type": None, "label": "open text"},
]

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
    price_score = 2 if place["price_level"] == "PRICE_LEVEL_VERY_EXPENSIVE" else 1
    cafe_score = 2 if "cafe" in place.get("types", "") else 1 if place.get("source_label") in {"strict cafe", "restaurant/cafe", "lounge/cafe"} else 0
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
    csv_path = OUT_DIR / "premium_october_venues.csv"
    json_path = OUT_DIR / "premium_october_venues.json"
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
    print(f"Searching for up to {TARGET_LIMIT} premium venues in October/Zayed")
    print("Price levels:", ", ".join(PRICE_LEVELS))

    by_id: dict[str, dict[str, Any]] = {}
    strict_cafe_count = 0
    for search in SEARCHES:
        for center in CENTERS:
            for place in search_batch(api_key, search, center):
                if place["price_level"] not in PRICE_LEVELS:
                    continue
                key = place["id"] or place["google_maps_url"] or place["name"]
                if key and key not in by_id:
                    by_id[key] = place
                    if place.get("source_label") == "strict cafe":
                        strict_cafe_count += 1
            if len(by_id) >= TARGET_LIMIT:
                break
        if len(by_id) >= TARGET_LIMIT:
            break

    leads = sorted(by_id.values(), key=sort_key, reverse=True)[:TARGET_LIMIT]
    write_outputs(leads)

    print(f"\nUnique high-price venues found: {len(leads)}")
    print(f"Strict high-price cafes inside that set: {strict_cafe_count}")
    for index, lead in enumerate(leads, start=1):
        print(
            f"{index:03d}. {lead['name']} | {lead['price_level']} | {lead['primary_type']} | "
            f"rating={lead['rating']} reviews={lead['user_rating_count']} | {lead['phone']} | {lead['google_maps_url']}"
        )

    if len(leads) < TARGET_LIMIT:
        print(
            f"\nNOTE: Google returned only {len(leads)} unique high-price venues with "
            f"{', '.join(PRICE_LEVELS)} in the searched October/Zayed area."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
