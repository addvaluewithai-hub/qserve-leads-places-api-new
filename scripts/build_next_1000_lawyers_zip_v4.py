#!/usr/bin/env python3
from __future__ import annotations

"""ZIP V4 production wrapper.

Fixes a territory-order bug in V3: states inside the same phase shared the same
numeric priority, so SQL ordering could drift toward alphabetical state order
instead of the explicit order in market_plans/lawyers-us-zips.json.

V4 makes the market-plan state order executable, and ensures enough ZIP rows
from the first priority state are materialized before discovery.
"""

import zip_manager
from d1_helpers import result_rows
import build_next_1000_lawyers_zip_v3 as v3

PRIORITY_STATE_ZIP_WINDOW = 1200

_original_load_zip_universe = zip_manager.load_zip_universe
_original_sync_zip_plan = zip_manager.sync_zip_plan
_original_next_zips = zip_manager.next_zips


def _state_rank(plan: dict) -> dict[str, tuple[int, int, int]]:
    ranks: dict[str, tuple[int, int, int]] = {}
    for phase_index, phase in enumerate(plan.get("phases") or []):
        phase_priority = int(phase.get("priority") or 100)
        for state_index, state in enumerate(phase.get("states") or []):
            code = str(state.get("state") or "").upper().strip()
            if code:
                ranks[code] = (phase_priority, phase_index, state_index)
    return ranks


def _ordered_universe(plan: dict) -> list[dict]:
    rows = _original_load_zip_universe(plan)
    ranks = _state_rank(plan)
    fallback = (999999, 999999, 999999)
    return sorted(
        rows,
        key=lambda row: (
            ranks.get(str(row.get("state_code") or "").upper(), fallback),
            int(row.get("city_priority") or 1000),
            str(row.get("city") or ""),
            str(row.get("zip_code") or ""),
        ),
    )


def _priority_state_code(plan: dict) -> str | None:
    phases = plan.get("phases") or []
    if not phases:
        return None
    states = phases[0].get("states") or []
    if not states:
        return None
    code = str(states[0].get("state") or "").upper().strip()
    return code or None


def _sync_with_priority_state_window(query, campaign: dict, plan: dict) -> dict:
    # First run the normal sliding-queue sync, but with the universe ordered by
    # explicit market-plan state order.
    result = _original_sync_zip_plan(query, campaign, plan)

    priority_state = _priority_state_code(plan)
    if not priority_state:
        return result

    universe = _ordered_universe(plan)
    desired = [r for r in universe if r.get("state_code") == priority_state][:PRIORITY_STATE_ZIP_WINDOW]
    existing = {
        str(r["zip_code"])
        for r in result_rows(query("SELECT zip_code FROM zip_coverage WHERE campaign_id=?", [campaign["id"]]))
        if r.get("zip_code")
    }
    missing = [row for row in desired if row["zip_code"] not in existing]
    if missing:
        zip_manager._bulk_insert_zip_rows(query, campaign["id"], missing)

    result = dict(result)
    result["priority_state"] = priority_state
    result["priority_state_window"] = len(desired)
    result["priority_state_rows_added"] = len(missing)
    return result


def _ordered_next_zips(query, campaign: dict, plan: dict, limit: int) -> list[dict]:
    # Ask for the full materialized candidate window, then apply the explicit
    # state order in Python. Current production calls use max_zips=5000.
    rows = _original_next_zips(query, campaign, plan, max(int(limit), 5000))
    ranks = _state_rank(plan)
    fallback = (999999, 999999, 999999)
    rows.sort(
        key=lambda row: (
            0 if row.get("status") == "queued" else 1 if row.get("status") == "partial" else 2,
            ranks.get(str(row.get("state_code") or "").upper(), fallback),
            int(row.get("city_priority") or 1000),
            str(row.get("zip_code") or ""),
        )
    )
    return rows[: int(limit)]


# Patch the functions resolved by the existing production core at runtime.
zip_manager.load_zip_universe = _ordered_universe
v3.hardened.core.sync_zip_plan = _sync_with_priority_state_window
v3.hardened.core.next_zips = _ordered_next_zips


if __name__ == "__main__":
    v3.hardened.core.main()
