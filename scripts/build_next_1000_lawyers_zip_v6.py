#!/usr/bin/env python3
from __future__ import annotations

"""ZIP V6: use ZIPs as coverage seeds, not exact-address gates.

V5 proved that requiring postal_code == target ZIP discarded too many otherwise
valid law firms. V6 keeps the ZIP centroid + Google locationRestriction as the
search unit, keeps exact-postal counts only as a diagnostic, and accepts every
result returned inside the restricted search area that passes the normal
quality gate.

The campaign config also reduces the restriction half-span from 25 km to 10 km
and keeps global Place-ID/domain dedupe, Crawl4AI confirmation, and resumable
cohorts unchanged.
"""

import build_next_1000_lawyers_zip_v5 as v5

v4 = v5.v4
v3 = v4.v3
hardened = v3.hardened
core = hardened.core


def relaxed_area_quality_candidates(payload: dict, campaign: dict, target_zip: str):
    quality = campaign.get("quality") or {}
    google = campaign.get("google") or {}
    allowed = set(quality.get("allowed_business_statuses") or ["OPERATIONAL"])
    min_rating = float(quality.get("min_rating") or 4.0)
    min_reviews = int(quality.get("min_reviews") or 20)
    exact_required = bool(google.get("exact_postal_code_required", False))

    raw_places = payload.get("places") or []
    exact_zip_count = 0
    passed = []

    for place in raw_places:
        postal = core.postal_code_from_components(place.get("addressComponents"))
        if postal == target_zip:
            exact_zip_count += 1
        if exact_required and postal != target_zip:
            continue

        place_id = place.get("id")
        website_seed = place.get("websiteUri")
        rating = place.get("rating")
        review_count = place.get("userRatingCount")
        status = place.get("businessStatus")

        if not place_id or not website_seed:
            continue
        if status not in allowed:
            continue
        if rating is None or float(rating) < min_rating:
            continue
        if review_count is None or int(review_count) < min_reviews:
            continue

        passed.append({
            "place_id": str(place_id),
            "website_seed": str(website_seed),
            "seed_business_domain": core.business_domain(str(website_seed)),
        })

    return passed, {
        "raw_places": len(raw_places),
        "exact_zip_places": exact_zip_count,
        "quality_passes": len(passed),
    }


# V2's hardened quality filter calls this runtime variable before applying the
# directory/social-domain rejection layer, so patching here preserves every
# later V2/V3/V4/V5 protection.
hardened._original_quality_candidates = relaxed_area_quality_candidates


if __name__ == "__main__":
    v5.main()
