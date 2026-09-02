#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import run_campaign as engine

ROOT = Path(__file__).resolve().parents[1]
ORIGINAL_API_JSON = engine.api_json
USAGE = {
    "text_search_calls": 0,
    "place_details_review_calls": 0,
    "other_google_places_calls": 0,
}


def tracked_api_json(url: str, *, api_key: str, body=None, field_mask=None):
    result = ORIGINAL_API_JSON(url, api_key=api_key, body=body, field_mask=field_mask)
    if "places:searchText" in url:
        USAGE["text_search_calls"] += 1
    elif "/v1/places/" in url and field_mask and "reviews" in field_mask:
        USAGE["place_details_review_calls"] += 1
    else:
        USAGE["other_google_places_calls"] += 1
    return result


def arg_value(name: str, default=None):
    try:
        index = sys.argv.index(name)
    except ValueError:
        return default
    return sys.argv[index + 1] if index + 1 < len(sys.argv) else default


def main() -> None:
    campaign = arg_value("--campaign")
    if not campaign:
        raise SystemExit("--campaign is required")

    engine.api_json = tracked_api_json
    try:
        engine.main()
    finally:
        out_arg = arg_value("--out-dir")
        out_dir = Path(out_arg) if out_arg else ROOT / "out" / campaign
        out_dir.mkdir(parents=True, exist_ok=True)

        # Current public list prices as of 2026-09-02, before monthly free usage caps.
        # Search requests include Enterprise-tier fields (rating/website/etc.).
        # Review details request the reviews field, which is Enterprise + Atmosphere.
        text_rate = 35.0 / 1000.0
        review_rate = 25.0 / 1000.0
        nominal = USAGE["text_search_calls"] * text_rate + USAGE["place_details_review_calls"] * review_rate
        payload = {
            "campaign": campaign,
            **USAGE,
            "pricing_reference_date": "2026-09-02",
            "pricing_note": "Nominal list-price estimate before monthly free usage caps and volume discounts; verify Google Maps Platform pricing before financial reporting.",
            "text_search_assumed_sku": "Places API Text Search Enterprise",
            "text_search_list_price_per_1000_usd": 35.0,
            "place_details_assumed_sku": "Places API Place Details Enterprise + Atmosphere",
            "place_details_list_price_per_1000_usd": 25.0,
            "nominal_cost_before_free_cap_usd": round(nominal, 4),
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
        (out_dir / "google_api_usage.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(json.dumps({"google_api_usage": payload}, indent=2))


if __name__ == "__main__":
    main()
