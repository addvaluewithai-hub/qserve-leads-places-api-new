#!/usr/bin/env python3
"""Count-first adapter for V8 Aggregate.

Google Places Aggregate returns an error if INSIGHT_PLACES is requested for an area
containing more than 100 matching places. The original V8 runner asked for COUNT and
PLACES together. This adapter keeps the tested V8 persistence/resume logic intact but
forces the safe sequence:

1. INSIGHT_COUNT only.
2. If count > 100, return the count so the runner splits the tile.
3. If 1 <= count <= 100, request INSIGHT_PLACES in a second Aggregate call.

The D1 ledger still records every Aggregate request before it is made, preserving the
zero-paid safety bias.
"""
from __future__ import annotations

import build_lawyers_v8_aggregate as v8

_original_aggregate_call = v8.aggregate_call


def aggregate_call_count_first(key, ledger, budget, tile, insights):
    requested = set(insights or [])
    if requested == {"INSIGHT_COUNT", "INSIGHT_PLACES"}:
        count, _, count_payload = _original_aggregate_call(
            key, ledger, budget, tile, ["INSIGHT_COUNT"]
        )
        if count <= 0 or count > 100:
            return count, [], count_payload
        _, ids, places_payload = _original_aggregate_call(
            key, ledger, budget, tile, ["INSIGHT_PLACES"]
        )
        return count, ids, {
            "count": count,
            "placeInsights": (places_payload or {}).get("placeInsights") or [],
        }
    return _original_aggregate_call(key, ledger, budget, tile, insights)


v8.aggregate_call = aggregate_call_count_first


if __name__ == "__main__":
    v8.main()
