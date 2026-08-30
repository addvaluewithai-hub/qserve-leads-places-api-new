#!/usr/bin/env python3
"""Smoke-test Google Places API (New) price-level filtering.

Defaults target the Google Maps location discussed in chat:
  lat=29.9724785, lng=30.9576332

The script performs:
1. A baseline cafe Text Search to verify the API key/API are working.
2. A filtered cafe Text Search for PRICE_LEVEL_VERY_EXPENSIVE ($$$$).

It never prints the API key. GitHub Actions reads GOOGLE_API_KEY from the
repository's Actions secret with the same name.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

ENDPOINT = "https://places.googleapis.com/v1/places:searchText"
FIELD_MASK = ",".join(
    [
        "places.id",
        "places.displayName",
        "places.formattedAddress",
        "places.priceLevel",
        "places.googleMapsUri",
    ]
)

LAT = float(os.getenv("TEST_LAT", "29.9724785"))
LNG = float(os.getenv("TEST_LNG", "30.9576332"))
RADIUS_METERS = float(os.getenv("TEST_RADIUS_METERS", "3000"))
PRICE_LEVEL = os.getenv("TEST_PRICE_LEVEL", "PRICE_LEVEL_VERY_EXPENSIVE")


def search_places(api_key: str, price_levels: list[str] | None = None) -> dict:
    body: dict = {
        "textQuery": "cafe",
        "includedType": "cafe",
        "strictTypeFiltering": True,
        "pageSize": 20,
        "locationBias": {
            "circle": {
                "center": {"latitude": LAT, "longitude": LNG},
                "radius": RADIUS_METERS,
            }
        },
    }

    if price_levels:
        body["priceLevels"] = price_levels

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


def print_places(title: str, payload: dict) -> None:
    places = payload.get("places", [])
    print(f"\n{title}: {len(places)} result(s)")
    for index, place in enumerate(places, start=1):
        name = place.get("displayName", {}).get("text", "(no name)")
        price = place.get("priceLevel", "PRICE_LEVEL_UNSPECIFIED")
        address = place.get("formattedAddress", "")
        maps_uri = place.get("googleMapsUri", "")
        print(f"{index:>2}. {name} | {price}")
        if address:
            print(f"    {address}")
        if maps_uri:
            print(f"    {maps_uri}")


def main() -> int:
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        print("ERROR: GOOGLE_API_KEY is not set.", file=sys.stderr)
        return 2

    print(
        "Testing Places API (New) near "
        f"{LAT},{LNG} within a {RADIUS_METERS:.0f}m location bias."
    )

    baseline = search_places(api_key)
    print_places("Baseline cafe search", baseline)

    filtered = search_places(api_key, [PRICE_LEVEL])
    print_places(f"Filtered cafe search ({PRICE_LEVEL})", filtered)

    filtered_places = filtered.get("places", [])
    unexpected = [
        place
        for place in filtered_places
        if place.get("priceLevel") != PRICE_LEVEL
    ]

    if unexpected:
        print(
            f"ERROR: Google returned {len(unexpected)} result(s) outside "
            f"the requested {PRICE_LEVEL} filter.",
            file=sys.stderr,
        )
        return 1

    if not filtered_places:
        print(
            "\nPASS: Google accepted the price-level filtered request, but returned "
            "no matching cafes in this search area."
        )
    else:
        print(
            f"\nPASS: Returned {len(filtered_places)} cafe(s), all marked "
            f"{PRICE_LEVEL}."
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
