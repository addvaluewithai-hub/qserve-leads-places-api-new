#!/usr/bin/env python3
from __future__ import annotations

"""Low-D1-read launcher for the V8 Pro-bridge discovery runner.

The production runner historically called batch_state() and write_checkpoint()
inside hot loops. batch_state() performs a COUNT over the batch and
write_checkpoint() also aggregates all tiles, so a 2K batch amplified into
millions of D1 row reads.

This launcher keeps the authoritative batch count in memory for the duration of a
single discovery process, increments it only after a successful durable
persist_resolved(), and writes checkpoints without querying D1. One DB
reconciliation is performed after the runner exits.
"""

import json
from pathlib import Path
from typing import Any

import build_lawyers_v8_aggregate as v8
import build_lawyers_v8_aggregate_probridge as runner

_ORIG_BATCH_STATE = v8.batch_state
_ORIG_REPAIR_RESERVATIONS = v8.repair_reservations
_ORIG_PERSIST_RESOLVED = v8.persist_resolved

_STATE: dict[str, dict[str, Any]] = {}
_QUERY: dict[str, Any] = {}


def _refresh_batch_state(query, batch_id: str) -> dict:
    state = dict(_ORIG_BATCH_STATE(query, batch_id))
    _STATE[batch_id] = state
    _QUERY[batch_id] = query
    return dict(state)


def _cached_batch_state(query, batch_id: str) -> dict:
    _QUERY[batch_id] = query
    if batch_id not in _STATE:
        return _refresh_batch_state(query, batch_id)
    return dict(_STATE[batch_id])


def _repair_reservations(query, campaign: dict, batch_id: str) -> int:
    repaired = _ORIG_REPAIR_RESERVATIONS(query, campaign, batch_id)
    # Repair can add missing discovery_batch_leads_v8 rows. Force exactly one
    # authoritative recount immediately after repair, then stay in-memory.
    _STATE.pop(batch_id, None)
    _QUERY[batch_id] = query
    return repaired


def _persist_resolved(query, campaign: dict, batch_id: str, state: str, tile_id_value: str, row: dict) -> bool:
    ok = _ORIG_PERSIST_RESOLVED(query, campaign, batch_id, state, tile_id_value, row)
    if not ok:
        return False

    cached = _STATE.get(batch_id)
    if cached is not None:
        cached["collected_domains"] = int(cached.get("collected_domains") or 0) + 1
        target = int(cached.get("target_domains") or 0)
        cached["remaining_domains"] = max(0, target - int(cached["collected_domains"]))
        if cached["remaining_domains"] == 0:
            # Keep hot-loop decisions correct without issuing another COUNT.
            cached["status"] = "completed"
    return True


def _write_light_checkpoint(
    out_dir: Path,
    query,
    batch_id: str,
    budgets: dict,
    run_accepted: list[dict],
    last_tile: dict | None,
    stop_reason: str | None = None,
) -> None:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    state = _cached_batch_state(query, batch_id)
    payload = {
        "batch": state,
        "budgets": {
            key: {"sku": b.sku, "cap": b.cap, "used": b.used, "remaining": b.remaining}
            for key, b in budgets.items()
        },
        "run_accepted": len(run_accepted),
        "last_tile": last_tile,
        "stop_reason": stop_reason,
        "checkpoint_mode": "lean_in_memory_batch_count_no_tile_scan",
        "updated_at": v8.now_iso(),
    }
    (out_dir / "checkpoint.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    with (out_dir / "accepted-this-run.jsonl").open("w", encoding="utf-8") as handle:
        for item in run_accepted:
            handle.write(json.dumps(item, ensure_ascii=False) + "\n")


def install_low_read_patch() -> None:
    v8.batch_state = _cached_batch_state
    v8.repair_reservations = _repair_reservations
    v8.persist_resolved = _persist_resolved
    v8.write_checkpoint = _write_light_checkpoint


def reconcile_after_run() -> None:
    for batch_id, query in list(_QUERY.items()):
        try:
            db_state = dict(_ORIG_BATCH_STATE(query, batch_id))
            cached = dict(_STATE.get(batch_id) or {})
            print(
                json.dumps(
                    {
                        "d1_read_fix_reconciliation": {
                            "batch_id": batch_id,
                            "cached_collected": cached.get("collected_domains"),
                            "db_collected": db_state.get("collected_domains"),
                            "db_remaining": db_state.get("remaining_domains"),
                            "db_status": db_state.get("status"),
                        }
                    }
                ),
                flush=True,
            )
        except Exception as exc:
            # Discovery writes remain durable even if a final reporting read is
            # unavailable. Never turn a successful discovery run into a failure
            # solely because the reconciliation read was blocked.
            print(
                json.dumps(
                    {
                        "d1_read_fix_reconciliation_warning": f"{type(exc).__name__}: {exc}",
                        "batch_id": batch_id,
                    }
                ),
                flush=True,
            )


def main() -> None:
    install_low_read_patch()
    try:
        runner.main()
    finally:
        reconcile_after_run()


if __name__ == "__main__":
    main()
