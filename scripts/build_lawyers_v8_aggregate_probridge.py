#!/usr/bin/env python3
from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import uuid
from pathlib import Path

import requests

import build_lawyers_v8_aggregate as v8

SKU_DETAILS_PRO = "places_place_details_pro"
DETAILS_PRO_URL = "https://places.googleapis.com/v1/places/{place_id}"


def details_pro_one(key: str, pid: str) -> dict:
    try:
        r = requests.get(
            DETAILS_PRO_URL.format(place_id=pid),
            headers={
                "X-Goog-Api-Key": key,
                "X-Goog-FieldMask": "id,displayName,formattedAddress,businessStatus",
            },
            timeout=60,
        )
        if r.status_code != 200:
            return {"place_id": pid, "ok": False, "reason": f"details_pro_http_{r.status_code}"}
        p = r.json()
        if p.get("businessStatus") not in {None, "OPERATIONAL"}:
            return {"place_id": pid, "ok": False, "reason": "not_operational"}
        name = v8.display_name(p.get("displayName"))
        address = str(p.get("formattedAddress") or "").strip()
        if not name:
            return {"place_id": pid, "ok": False, "reason": "missing_display_name"}
        return {"place_id": pid, "ok": True, "name": name, "address": address}
    except Exception as exc:
        return {"place_id": pid, "ok": False, "reason": f"{type(exc).__name__}: {exc}"}


def grounding_context_one(key: str, item: dict) -> dict:
    pid = str(item["place_id"])
    name = str(item.get("name") or "").strip()
    address = str(item.get("address") or "").strip()
    body = {
        "method": "tools/call",
        "params": {
            "name": "search_places",
            "arguments": {
                "textQuery": f"{name}, {address} official website",
                "languageCode": "en",
                "regionCode": "US",
            },
        },
        "jsonrpc": "2.0",
        "id": pid,
    }
    try:
        r = requests.post(
            v8.GROUNDING_URL,
            headers={"X-Goog-Api-Key": key, "Content-Type": "application/json"},
            json=body,
            timeout=90,
        )
        if r.status_code != 200:
            return {"place_id": pid, "ok": False, "reason": f"grounding_http_{r.status_code}"}
        payload = r.json()
        structured = ((payload.get("result") or {}).get("structuredContent") or {})
        places = structured.get("places") or []
        ids = [v8.normalize_place_id(p.get("id") or p.get("place")) for p in places]
        if pid not in ids:
            return {"place_id": pid, "ok": False, "reason": "place_id_identity_mismatch", "returned_ids": [x for x in ids if x]}
        urls = v8.external_urls(structured.get("summary") or "")
        same = next((p for p in places if v8.normalize_place_id(p.get("id") or p.get("place")) == pid), {})
        direct = same.get("websiteUri") or same.get("website")
        if direct and not v8.blocked_domain(direct):
            urls = [direct, *[u for u in urls if v8.business_domain(u) != v8.business_domain(direct)]]
        if not urls:
            return {"place_id": pid, "ok": False, "reason": "no_external_website"}
        return {
            "place_id": pid,
            "ok": True,
            "url": urls[0],
            "domain": v8.business_domain(urls[0]),
            "name": name,
            "method": "maps_grounding_lite_via_place_details_pro",
        }
    except Exception as exc:
        return {"place_id": pid, "ok": False, "reason": f"{type(exc).__name__}: {exc}"}


def parallel_ids(fn, key: str, ids: list[str], workers: int) -> list[dict]:
    if not ids:
        return []
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(max(1, workers), len(ids))) as ex:
        return list(ex.map(lambda pid: fn(key, pid), ids))


def parallel_items(fn, key: str, items: list[dict], workers: int) -> list[dict]:
    if not items:
        return []
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(max(1, workers), len(items))) as ex:
        return list(ex.map(lambda item: fn(key, item), items))


def main() -> None:
    ap = argparse.ArgumentParser(description="V8 Aggregate count-first -> Place Details Pro context -> Grounding Lite -> Enterprise fallback")
    ap.add_argument("--campaign", default="lawyers-us")
    ap.add_argument("--batch-id", default="lawyers-us:v8-batch-01-of-09")
    ap.add_argument("--target", type=int, default=2000)
    ap.add_argument("--out-dir", default="out/lawyers-us-v8-batch1-2000")
    ap.add_argument("--workers", type=int, default=8)
    args = ap.parse_args()

    key = os.getenv("GOOGLE_API_KEY")
    if not key:
        raise SystemExit("GOOGLE_API_KEY required")

    campaign = v8.zip_manager.load_campaign(args.campaign)
    plan = v8.zip_manager.load_plan(campaign)
    google = campaign.get("google") or {}
    query = v8.make_query_client()
    v8.apply_schema(query)
    v8.ensure_v8_schema(query)
    batch = v8.ensure_batch(query, campaign["id"], args.batch_id, args.target)
    repaired = v8.repair_reservations(query, campaign, args.batch_id)
    batch = v8.batch_state(query, args.batch_id)
    print(json.dumps({"batch_start": batch, "repaired_reservations": repaired}, indent=2), flush=True)
    if batch["remaining_domains"] <= 0:
        print("Batch already complete; no API calls required.")
        return

    run_id = f"v8-{uuid.uuid4()}"
    ledger = v8.Ledger(query, campaign["id"], run_id)
    budgets = {
        "aggregate": v8.Budget(v8.SKU_AGG, int(google.get("monthly_places_aggregate_request_budget") or 4800), ledger.used(v8.SKU_AGG)),
        "details_pro": v8.Budget(SKU_DETAILS_PRO, int(google.get("monthly_place_details_pro_request_budget") or 4800), ledger.used(SKU_DETAILS_PRO)),
        "grounding": v8.Budget(v8.SKU_GROUND, int(google.get("monthly_grounding_lite_request_budget") or 9500), ledger.used(v8.SKU_GROUND)),
        "details": v8.Budget(v8.SKU_DETAILS_ENT, int(google.get("monthly_place_details_enterprise_request_budget") or 900), ledger.used(v8.SKU_DETAILS_ENT)),
    }

    padding = float(google.get("aggregate_state_bbox_padding_degrees") or 0.12)
    roots = v8.seed_roots(query, args.batch_id, plan, padding)
    print(json.dumps({"root_tiles_added": roots, "budgets": {k: b.__dict__ | {"remaining": b.remaining} for k, b in budgets.items()}}, indent=2), flush=True)

    existing_ids, existing_domains = v8.global_seen(query)
    run_accepted: list[dict] = []
    out_dir = v8.ROOT / args.out_dir
    stop_reason = None
    last_tile = None
    canary_attempt_target = int(google.get("grounding_place_id_canary_attempts") or 10)
    canary_min_success = int(google.get("grounding_place_id_canary_min_successes") or 8)

    while True:
        batch = v8.batch_state(query, args.batch_id)
        if batch["remaining_domains"] <= 0:
            stop_reason = "target_reached"
            break
        if budgets["aggregate"].remaining <= 0:
            stop_reason = "aggregate_free_guard_exhausted"
            break
        tile = v8.next_tile(query, args.batch_id)
        if not tile:
            stop_reason = "aggregate_tile_queue_exhausted"
            break
        last_tile = {k: tile.get(k) for k in ["id", "state_code", "depth", "south", "west", "north", "east"]}

        if v8.bbox_area_m2(tile) > 1.8e12:
            v8.split_tile(query, tile, "pre_split_area_guard")
            v8.write_checkpoint(out_dir, query, args.batch_id, budgets, run_accepted, last_tile)
            continue

        try:
            count, _, _ = v8.aggregate_call(key, ledger, budgets["aggregate"], tile, ["INSIGHT_COUNT"])
            ids: list[str] = []
            if 0 < count <= 100:
                if budgets["aggregate"].remaining <= 0:
                    stop_reason = "aggregate_free_guard_exhausted"
                    break
                _, ids, _ = v8.aggregate_call(key, ledger, budgets["aggregate"], tile, ["INSIGHT_PLACES"])
        except Exception as exc:
            msg = f"{type(exc).__name__}: {exc}"
            query("UPDATE aggregate_tiles_v8 SET status='failed',last_error=?,updated_at=CURRENT_TIMESTAMP WHERE id=?", [msg[:1200], tile["id"]])
            v8.write_checkpoint(out_dir, query, args.batch_id, budgets, run_accepted, last_tile, "aggregate_error")
            if "SERVICE_DISABLED" in msg or "PERMISSION_DENIED" in msg or "403" in msg:
                stop_reason = "aggregate_service_unavailable"
                break
            continue

        if count <= 0:
            query("UPDATE aggregate_tiles_v8 SET status='empty',place_count=0,place_ids_returned=0,updated_at=CURRENT_TIMESTAMP WHERE id=?", [tile["id"]])
            v8.write_checkpoint(out_dir, query, args.batch_id, budgets, run_accepted, last_tile)
            continue
        if count > 100:
            query("UPDATE aggregate_tiles_v8 SET place_count=?,place_ids_returned=0,updated_at=CURRENT_TIMESTAMP WHERE id=?", [count, tile["id"]])
            v8.split_tile(query, tile, f"count={count}>100")
            v8.write_checkpoint(out_dir, query, args.batch_id, budgets, run_accepted, last_tile)
            continue
        if not ids:
            query("UPDATE aggregate_tiles_v8 SET status='failed',place_count=?,last_error='count<=100 but no place IDs returned',updated_at=CURRENT_TIMESTAMP WHERE id=?", [count, tile["id"]])
            v8.write_checkpoint(out_dir, query, args.batch_id, budgets, run_accepted, last_tile)
            continue

        fresh = [pid for pid in ids if pid not in existing_ids]
        query("UPDATE aggregate_tiles_v8 SET place_count=?,place_ids_returned=?,fresh_place_ids=?,updated_at=CURRENT_TIMESTAMP WHERE id=?", [count, len(ids), len(fresh), tile["id"]])
        if not fresh:
            query("UPDATE aggregate_tiles_v8 SET status='leaf_complete',updated_at=CURRENT_TIMESTAMP WHERE id=?", [tile["id"]])
            v8.write_checkpoint(out_dir, query, args.batch_id, budgets, run_accepted, last_tile)
            continue

        needed = int(v8.batch_state(query, args.batch_id)["remaining_domains"])
        candidates = fresh[: min(len(fresh), needed + 20)]
        resolved: list[dict] = []

        # Bridge Aggregate IDs to Grounding text context using Place Details Pro only for fresh IDs.
        if candidates and budgets["details_pro"].remaining > 0 and budgets["grounding"].remaining > 0:
            n = min(len(candidates), budgets["details_pro"].remaining, budgets["grounding"].remaining)
            bridge_ids = candidates[:n]
            ledger.reserve(budgets["details_pro"], n, f"tile={tile['id']};state={tile['state_code']};context_for_grounding")
            context_results = parallel_ids(details_pro_one, key, bridge_ids, args.workers)
            context_ok = [r for r in context_results if r.get("ok")]
            context_failed = [r for r in context_results if not r.get("ok")]
            for r in context_failed:
                v8.record_unresolved(query, args.batch_id, tile["state_code"], tile["id"], r)

            if context_ok:
                ledger.reserve(budgets["grounding"], len(context_ok), f"tile={tile['id']};state={tile['state_code']};name_address_resolution")
                ground_results = parallel_items(grounding_context_one, key, context_ok, args.workers)
                _, canary_failed = v8.update_canary(query, args.batch_id, ground_results, canary_attempt_target, canary_min_success)
                for r in ground_results:
                    if r.get("ok") and r.get("domain") and not v8.blocked_domain(r.get("domain")):
                        resolved.append(r)
                    else:
                        v8.record_unresolved(query, args.batch_id, tile["state_code"], tile["id"], r)
                if canary_failed:
                    stop_reason = "grounding_place_id_canary_failed"
                    v8.write_checkpoint(out_dir, query, args.batch_id, budgets, run_accepted, last_tile, stop_reason)
                    break
            candidates = candidates[n:]

        # Enterprise websiteUri fallback only after the Pro/Grounding free path cannot be spent.
        free_bridge_exhausted = budgets["details_pro"].remaining <= 0 or budgets["grounding"].remaining <= 0
        if candidates and free_bridge_exhausted and budgets["details"].remaining > 0:
            n = min(len(candidates), budgets["details"].remaining)
            detail_ids = candidates[:n]
            ledger.reserve(budgets["details"], n, f"tile={tile['id']};state={tile['state_code']};after_pro_or_grounding_exhausted")
            detail_results = parallel_ids(v8.details_one, key, detail_ids, args.workers)
            for r in detail_results:
                if r.get("ok") and r.get("domain") and not v8.blocked_domain(r.get("domain")):
                    resolved.append(r)
                else:
                    v8.record_unresolved(query, args.batch_id, tile["state_code"], tile["id"], r)

        new_here = 0
        for r in resolved:
            if v8.batch_state(query, args.batch_id)["remaining_domains"] <= 0:
                break
            pid = str(r["place_id"])
            d = v8.business_domain(r.get("domain"))
            if pid in existing_ids or not d or d in existing_domains:
                continue
            if v8.persist_resolved(query, campaign, args.batch_id, tile["state_code"], tile["id"], r):
                existing_ids.add(pid)
                existing_domains.add(d)
                new_here += 1
                item = {"place_id": pid, "website_domain": d, "state": tile["state_code"], "tile": tile["id"], "resolution_method": r.get("method")}
                run_accepted.append(item)
                print(json.dumps({"accepted": item, "batch_collected": v8.batch_state(query, args.batch_id)["collected_domains"]}), flush=True)

        query("UPDATE aggregate_tiles_v8 SET status='leaf_complete',net_new_domains=?,updated_at=CURRENT_TIMESTAMP WHERE id=?", [new_here, tile["id"]])
        v8.write_checkpoint(out_dir, query, args.batch_id, budgets, run_accepted, last_tile)
        print(json.dumps({
            "tile": last_tile,
            "count": count,
            "ids": len(ids),
            "fresh_ids": len(fresh),
            "new_domains": new_here,
            "batch": v8.batch_state(query, args.batch_id),
            "budgets": {k: b.remaining for k, b in budgets.items()},
        }), flush=True)

        if budgets["details_pro"].remaining <= 0 and budgets["grounding"].remaining <= 0 and budgets["details"].remaining <= 0 and v8.batch_state(query, args.batch_id)["remaining_domains"] > 0:
            stop_reason = "domain_resolution_free_guards_exhausted"
            break

    final = v8.batch_state(query, args.batch_id)
    if final["remaining_domains"] <= 0:
        query("UPDATE discovery_batches_v8 SET status='completed',completed_at=COALESCE(completed_at,CURRENT_TIMESTAMP),updated_at=CURRENT_TIMESTAMP WHERE id=?", [args.batch_id])
    else:
        query("UPDATE discovery_batches_v8 SET status='partial',updated_at=CURRENT_TIMESTAMP WHERE id=?", [args.batch_id])
    v8.write_checkpoint(out_dir, query, args.batch_id, budgets, run_accepted, last_tile, stop_reason)
    summary = {
        "batch": v8.batch_state(query, args.batch_id),
        "run_accepted": len(run_accepted),
        "stop_reason": stop_reason,
        "budgets": {k: {"used": b.used, "cap": b.cap, "remaining": b.remaining} for k, b in budgets.items()},
        "tile_status": v8.tile_stats(query, args.batch_id),
        "completed_at": v8.now_iso(),
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2), flush=True)
    if stop_reason not in {"target_reached", None} and final["remaining_domains"] > 0:
        raise SystemExit(f"V8 partial stop: {stop_reason}; remaining={final['remaining_domains']}")


if __name__ == "__main__":
    main()
