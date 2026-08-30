#!/usr/bin/env python3
"""Export premium cafe leads from Google Places API (New).

The script is designed for GitHub Actions. It keeps GOOGLE_API_KEY in Actions
secrets and exports high-price cafe leads as CSV + JSON artifacts.
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

# Main October / Sheikh Zayed search area discussed in chat.
CENTERS = [
    (29.9724785, 30.9576332, 12000, "6 October core"),
    (30.0131, 30.9841, 12000, "Sheikh Zayed west"),
    (29.9472, 30.9305, 12000, "6 October south"),
    (30.0451, 31.0003, 12000, "Capital Business Park / Zayed"),
]

QUERIES = [
    "cafe in 6th of October City, Giza, Egypt",
    "coffee shop in 6th of October City, Giza, Egypt",
    "premium cafe in 6th of October City, Giza, Egypt",
    "cafe in Sheikh Zayed City, Giza, Egypt",
    "coffee shop in Sheikh Zayed City, Giza, Egypt",
    "premium cafe in Sheikh Zayed City, Giza, Egypt",
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


def normalize_place(place: dict[str, Any], query: str, area: str) -> dict[str, Any]:
    name = place.get("displayName", {}).get("text", "")
    location = place.get("location") or {}
    hours = place.get("regularOpeningHours", {}).get("weekdayDescriptions") or []
    return {
        "id": place.get("id", ""),
        "name": name,
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
        "source_query": query,
        "source_area": area,
    }


def search_batch(api_key: str, query: str, center: tuple[float, float, int, str]) -> list[dict[str, Any]]:
    lat, lng, radius, area = center
    body: dict[str, Any] = {
        "textQuery": query,
        "includedType": "cafe",
        "strictTypeFiltering": True,
        "pageSize": 20,
        "priceLevels": PRICE_LEVELS,
        "locationBias": {
            "circle": {
                "center": {"latitude": lat, "longitude": lng},
                "radius": radius,
            }
        },
    }

    results: list[dict[str, Any]] = []
    page = 1
    while page <= 5 and len(results) < TARGET_LIMIT:
        payload = call_google(api_key, body)
        places = payload.get("places", [])
        print(f"{query!r} / {area} / page {page}: {len(places)} place(s)")
        results.extend(normalize_place(place, query, area) for place in places)

        token = payload.get("nextPageToken")
        if not token:
            break
        body["pageToken"] = token
        page += 1
        time.sleep(2)

    return results


def sort_key(place: dict[str, Any]) -> tuple[int, float, int, str]:
    price_score = 2 if place["price_level"] == "PRICE_LEVEL_VERY_EXPENSIVE" else 1
    try:
        rating = float(place["rating"] or 0)
    except ValueError:
        rating = 0.0
    try:
        count = int(place["user_rating_count"] or 0)
    except ValueError:
        count = 0
    return (price_score, rating, count, place["name"])


def write_outputs(leads: list[dict[str, Any]]) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    csv_path = OUT_DIR / "premium_october_cafes.csv"
    json_path = OUT_DIR / "premium_october_cafes.json"

    fields = [
        "name",
        "price_level",
        "rating",
        "user_rating_count",
        "business_status",
        "phone",
        "website",
        "google_maps_url",
        "address",
        "latitude",
        "longitude",
        "primary_type",
        "types",
        "opening_hours",
        "source_query",
        "source_area",
        "id",
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

    print("Searching for up to", TARGET_LIMIT, "premium cafe leads in October/Zayed")
    print("Price levels:", ", ".join(PRICE_LEVELS))

    by_id: dict[str, dict[str, Any]] = {}
    for center in CENTERS:
        for query in QUERIES:
            batch = search_batch(api_key, query, center)
            for place in batch:
                if place["price_level"] not in PRICE_LEVELS:
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

    print(f"\nUnique high-price cafe leads found: {len(leads)}")
    for index, lead in enumerate(leads[:40], start=1):
        print(
            f"{index:02d}. {lead['name']} | {lead['price_level']} | "
            f"rating={lead['rating']} reviews={lead['user_rating_count']} | {lead['phone']} | {lead['google_maps_url']}"
        )

    if len(leads) < TARGET_LIMIT:
        print(
            f"\nNOTE: Google returned only {len(leads)} unique cafe leads with "
            f"{', '.join(PRICE_LEVELS)} in the searched October/Zayed area."
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
