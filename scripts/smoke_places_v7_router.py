#!/usr/bin/env python3
from __future__ import annotations

import json
import os

from places_v7_router import PlacesV7Router, UsageLedger

MARKETS = ["Phoenix, AZ", "Tampa, FL"]


def main() -> None:
    key = os.getenv("GOOGLE_API_KEY")
    if not key:
        raise SystemExit("GOOGLE_API_KEY missing")

    # Tiny in-memory caps intentionally force the route transition in one smoke run:
    # market 1 -> Pro + Grounding, market 2 -> Enterprise direct.
    ledger = UsageLedger(query=None, campaign_id="lawyers-us", run_id="v7-router-smoke")
    router = PlacesV7Router(
        key,
        ledger=ledger,
        pro_cap=10,
        grounding_cap=10,
        enterprise_cap=5,
    )

    output = {"before": router.budget_snapshot(), "markets": []}
    for market in MARKETS:
        body = router.search_body(
            text_query=f"lawyer in {market}",
            min_rating=4.0,
            page_size=10,
        )
        result = router.search_and_resolve_page(body, f"smoke_market={market}")
        output["markets"].append({
            "market": market,
            "search_mode": result.get("search_mode"),
            "resolved_count": len(result.get("places") or []),
            "methods": sorted({r.get("resolution_method") for r in (result.get("places") or [])}),
            "unresolved_place_ids": result.get("unresolved_place_ids") or [],
            "sample": (result.get("places") or [])[:3],
        })

    output["after"] = router.budget_snapshot()
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
