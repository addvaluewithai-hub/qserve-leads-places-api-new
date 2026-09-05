#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import math
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import tldextract

import zip_manager
from d1_helpers import ROOT, apply_schema, make_query_client, result_rows
from places_v7_router import (
    ENTERPRISE_FIELD_MASK,
    PRO_FIELD_MASK,
    PlacesV7Router,
    UsageLedger,
    blocked,
)

# D1 accepts at most 100 bound parameters per statement in this project.
zip_manager.ZIP_UPSERT_BATCH = 10
D1_MAX_BOUND_PARAMS = 100
TLD_EXTRACT = tldextract.TLDExtract(suffix_list_urls=None)
HOST_IDENTITY_BASES = {
    "wixsite.com", "wordpress.com", "weebly.com", "godaddysites.com",
    "square.site", "webflow.io", "mystrikingly.com", "site123.me",
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def host(value: str | None) -> str | None:
    if not value:
        return None
    try:
        v = value if "://" in value else f"https://{value}"
        h = (urlparse(v).hostname or "").lower().strip(".")
        return h[4:] if h.startswith("www.") else (h or None)
    except Exception:
        return None


def business_domain(value: str | None) -> str | None:
    h = host(value)
    if not h:
        return None
    parts = TLD_EXTRACT(h)
    base = f"{parts.domain}.{parts.suffix}".lower() if parts.domain and parts.suffix else h
    if base in HOST_IDENTITY_BASES and h != base:
        return h
    return base


def rectangle(latitude: float, longitude: float, half_span_km: float) -> dict:
    lat_delta = half_span_km / 111.0
    cos_lat = max(0.2, math.cos(math.radians(latitude)))
    lon_delta = half_span_km / (111.0 * cos_lat)
    return {
        "rectangle": {
            "low": {
                "latitude": max(-90.0, latitude - lat_delta),
                "longitude": max(-180.0, longitude - lon_delta),
            },
            "high": {
                "latitude": min(90.0, latitude + lat_delta),
                "longitude": min(180.0, longitude + lon_delta),
            },
        }
    }


def state_rank(plan: dict) -> dict[str, tuple[int, int, int]]:
    ranks: dict[str, tuple[int, int, int]] = {}
    for phase_index, phase in enumerate(plan.get("phases") or []):
        phase_priority = int(phase.get("priority") or 100)
        for state_index, state in enumerate(phase.get("states") or []):
            code = str(state.get("state") or "").upper().strip()
            if code:
                ranks[code] = (phase_priority, phase_index, state_index)
    return ranks


def ordered_next_zips(query, campaign: dict, plan: dict, limit: int) -> list[dict]:
    rows = zip_manager.next_zips(query, campaign, plan, max(int(limit), 5000))
    ranks = state_rank(plan)
    fallback = (999999, 999999, 999999)
    rows.sort(key=lambda row: (
        0 if row.get("status") == "queued" else 1 if row.get("status") == "partial" else 2,
        ranks.get(str(row.get("state_code") or "").upper(), fallback),
        int(row.get("city_priority") if row.get("city_priority") is not None else 1000),
        str(row.get("zip_code") or ""),
    ))
    return rows[: int(limit)]


def global_seen(query) -> tuple[set[str], set[str]]:
    ids: set[str] = set()
    domains: set[str] = set()
    for row in result_rows(query("SELECT lead_id,website_domain FROM lead_domains")):
        if row.get("lead_id"):
            ids.add(str(row["lead_id"]))
        d = business_domain(row.get("website_domain"))
        if d:
            domains.add(d)
    for row in result_rows(query(
        """
        SELECT lead_id,website_domain
        FROM outreach_suppression
        WHERE suppressed=1
          AND (reengage_after IS NULL OR reengage_after > CURRENT_TIMESTAMP)
        """
    )):
        if row.get("lead_id"):
            ids.add(str(row["lead_id"]))
        d = business_domain(row.get("website_domain"))
        if d:
            domains.add(d)
    return ids, domains


def multi_insert(query, prefix: str, rows: list[tuple], columns: int, suffix: str = "") -> None:
    if not rows:
        return
    chunk_size = max(1, D1_MAX_BOUND_PARAMS // max(1, columns))
    placeholder = "(" + ",".join("?" for _ in range(columns)) + ")"
    for start in range(0, len(rows), chunk_size):
        chunk = rows[start:start + chunk_size]
        sql = prefix + ",".join(placeholder for _ in chunk)
        if suffix:
            sql += "\n" + suffix
        params = [value for row in chunk for value in row]
        query(sql, params)


def persist_zip_rows(query, campaign: dict, run_id: str, zip_row: dict, rows: list[dict]) -> None:
    if not rows:
        return
    batch = f"{campaign['id']}:{run_id}"
    lead_rows: list[tuple] = []
    membership_rows: list[tuple] = []
    screening_rows: list[tuple] = []
    domain_rows: list[tuple] = []
    screened_at = now_iso()

    for row in rows:
        pid = row["place_id"]
        domain = row["website_domain"]
        normalized_site = f"https://{domain}/"
        method = row["resolution_method"]
        if method == "maps_grounding_lite":
            provider = "places_text_search_pro_min_rating4_plus_maps_grounding_lite"
        else:
            provider = "places_text_search_enterprise_fallback_min_rating4"
        notes = (
            "V7 discovery: lawyer type + Google minRating>=4.0 + OPERATIONAL. "
            "No minimum review-count gate. Domain resolved with Grounding Lite or Enterprise fallback. "
            "Crawl4AI is intentionally deferred to the separate evidence stage."
        )
        lead_rows.append((
            pid, domain, "OPERATIONAL", normalized_site,
            campaign.get("name") or campaign["id"], "lawyer", campaign.get("vertical") or "legal",
            str(zip_row["zip_code"]), "Ready for Crawl Evidence", notes, batch, batch,
        ))
        membership_rows.append((
            campaign["id"], pid, 0, 0, "working_set_ready_for_crawl_evidence",
            str(zip_row["zip_code"]), "lawyer", f"zip:{zip_row['zip_code']}",
            "Ready for Crawl Evidence", run_id,
        ))
        screening_rows.append((
            campaign["id"], pid, provider, str(zip_row["zip_code"]), 1, screened_at,
            f"V7 minRating>=4.0; no review-count gate; resolution_method={method}; Crawl4AI pending.",
        ))
        # verified=0 until Crawl4AI confirms the public site/final domain.
        domain_rows.append((pid, domain, 0, method + "_seed"))

    multi_insert(
        query,
        """
        INSERT INTO leads (
          id,name,business_status,website,source_label,source_query,source_type,source_area,
          status,notes,first_source_batch,latest_source_batch
        ) VALUES
        """,
        lead_rows, 12,
        """
        ON CONFLICT(id) DO UPDATE SET
          website=excluded.website,
          business_status=excluded.business_status,
          source_label=excluded.source_label,
          source_query=excluded.source_query,
          source_type=excluded.source_type,
          source_area=excluded.source_area,
          status=excluded.status,
          notes=excluded.notes,
          latest_source_batch=excluded.latest_source_batch,
          last_seen_at=CURRENT_TIMESTAMP
        """,
    )
    multi_insert(
        query,
        """
        INSERT INTO campaign_leads (
          campaign_id,lead_id,qualified,quality_score,qualification_reason,
          source_area,source_query,source_term,status,last_run_id
        ) VALUES
        """,
        membership_rows, 10,
        """
        ON CONFLICT(campaign_id,lead_id) DO UPDATE SET
          qualified=0,
          qualification_reason=excluded.qualification_reason,
          source_area=excluded.source_area,
          source_query=excluded.source_query,
          source_term=excluded.source_term,
          status=excluded.status,
          last_seen_at=CURRENT_TIMESTAMP,
          last_run_id=excluded.last_run_id
        """,
    )
    multi_insert(
        query,
        """
        INSERT INTO lead_discovery_screening (
          campaign_id,lead_id,provider,source_zip,quality_gate_passed,screened_at,notes
        ) VALUES
        """,
        screening_rows, 7,
        """
        ON CONFLICT(campaign_id,lead_id) DO UPDATE SET
          provider=excluded.provider,
          source_zip=excluded.source_zip,
          quality_gate_passed=excluded.quality_gate_passed,
          screened_at=excluded.screened_at,
          notes=excluded.notes
        """,
    )
    # Completion/dedupe marker LAST. Unique website_domain protects global domain identity.
    multi_insert(
        query,
        """
        INSERT INTO lead_domains (lead_id,website_domain,verified,source) VALUES
        """,
        domain_rows, 4,
        """
        ON CONFLICT(lead_id) DO UPDATE SET
          website_domain=excluded.website_domain,
          verified=excluded.verified,
          source=excluded.source,
          updated_at=CURRENT_TIMESTAMP
        """,
    )


def mark_zip_in_progress(query, campaign_id: str, zip_code: str, run_id: str) -> None:
    query(
        "UPDATE zip_coverage SET status='in_progress',last_run_id=?,last_searched_at=?,updated_at=CURRENT_TIMESTAMP WHERE campaign_id=? AND zip_code=?",
        [run_id, now_iso(), campaign_id, zip_code],
    )


def finish_zip(query, campaign_id: str, run_id: str, zip_row: dict, status: str, metrics: dict, note: str) -> None:
    now = now_iso()
    query(
        """
        UPDATE zip_coverage
        SET status=?,search_count=search_count+1,page_count=page_count+?,raw_places=raw_places+?,
            quality_passes=quality_passes+?,net_new_domains=net_new_domains+?,
            duplicate_place_ids=duplicate_place_ids+?,duplicate_domains=duplicate_domains+?,
            last_searched_at=?,last_run_id=?,notes=?,updated_at=CURRENT_TIMESTAMP
        WHERE campaign_id=? AND zip_code=?
        """,
        [
            status, int(metrics["page_count"]), int(metrics["raw_places"]), int(metrics["quality_passes"]),
            int(metrics["net_new_domains"]), int(metrics["duplicate_place_ids"]), int(metrics["duplicate_domains"]),
            now, run_id, note[:1200], campaign_id, str(zip_row["zip_code"]),
        ],
    )
    query(
        """
        INSERT INTO zip_run_history (
          id,campaign_id,run_id,zip_code,city,state_code,searched_at,status_after,
          page_count,raw_places,exact_zip_places,quality_passes,net_new_domains,
          duplicate_place_ids,duplicate_domains,note
        ) VALUES (?,?,?,?,?,?,CURRENT_TIMESTAMP,?,?,?,?,?,?,?,?,?)
        """,
        [
            str(uuid.uuid4()), campaign_id, run_id, str(zip_row["zip_code"]), zip_row.get("city"),
            zip_row.get("state_code"), status, int(metrics["page_count"]), int(metrics["raw_places"]), 0,
            int(metrics["quality_passes"]), int(metrics["net_new_domains"]), int(metrics["duplicate_place_ids"]),
            int(metrics["duplicate_domains"]), note[:1200],
        ],
    )


def enterprise_rows(payload: dict) -> list[dict]:
    rows: list[dict] = []
    for place in payload.get("places") or []:
        if place.get("businessStatus") != "OPERATIONAL" or not place.get("id"):
            continue
        d = business_domain(place.get("websiteUri"))
        if not d or blocked(d):
            continue
        rows.append({
            "place_id": str(place["id"]),
            "website_domain": d,
            "resolution_method": "text_search_enterprise_fallback",
        })
    return rows


def write_outputs(out_dir: Path, accepted: list[dict], summary: dict, zip_log: list[dict]) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    with (out_dir / "accepted.jsonl").open("w", encoding="utf-8") as f:
        for row in accepted:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    if accepted:
        with (out_dir / "accepted.csv").open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(accepted[0].keys()))
            w.writeheader(); w.writerows(accepted)
    with (out_dir / "zip-log.jsonl").open("w", encoding="utf-8") as f:
        for row in zip_log:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="V7 zero-paid US lawyer discovery batch")
    parser.add_argument("--campaign", default="lawyers-us")
    parser.add_argument("--target", type=int, default=2000)
    parser.add_argument("--max-zips", type=int, default=5000)
    parser.add_argument("--batch-label", default="v7-batch")
    parser.add_argument("--out-dir", default="out/lawyers-us-v7-batch")
    args = parser.parse_args()

    key = os.getenv("GOOGLE_API_KEY")
    if not key:
        raise SystemExit("GOOGLE_API_KEY is required")

    campaign = zip_manager.load_campaign(args.campaign)
    plan = zip_manager.load_plan(campaign)
    google = campaign.get("google") or {}
    query = make_query_client()
    apply_schema(query)
    recovered = zip_manager.recover_stale_in_progress(query, campaign["id"])
    sync = zip_manager.sync_zip_plan(query, campaign, plan)

    existing_ids, existing_domains = global_seen(query)
    target = int(args.target)
    run_id = str(uuid.uuid4())
    started = now_iso()
    query(
        "INSERT INTO campaign_runs (id,campaign_id,started_at,discovered_count,qualified_count,summary_json,status) VALUES (?,?,?,?,?,?,?)",
        [run_id, campaign["id"], started, 0, 0, "{}", "running"],
    )

    ledger = UsageLedger(query=query, campaign_id=campaign["id"], run_id=run_id)
    router = PlacesV7Router(
        key,
        ledger=ledger,
        pro_cap=int(google.get("monthly_text_search_pro_request_budget") or 4800),
        grounding_cap=int(google.get("monthly_grounding_lite_request_budget") or 9500),
        enterprise_cap=int(google.get("monthly_enterprise_request_budget") or 900),
    )
    budget_before = router.budget_snapshot()

    zip_rows = ordered_next_zips(query, campaign, plan, int(args.max_zips))
    accepted: list[dict] = []
    zip_log: list[dict] = []
    run_seen_ids: set[str] = set()
    run_seen_domains: set[str] = set()
    max_pages = int(google.get("max_pages_per_zip") or 3)
    page_size = int(google.get("page_size") or 20)
    raw_floor = int(google.get("paginate_if_first_page_raw_count_at_least") or 20)
    half_span = float(google.get("zip_location_restriction_half_span_km") or 10.0)
    stop_reason = "target_reached"

    if not zip_rows:
        stop_reason = "zip_queue_exhausted"

    for zip_index, zip_row in enumerate(zip_rows, 1):
        if len(accepted) >= target:
            break
        if not router.pro.can_spend() and not router.enterprise.can_spend():
            stop_reason = "search_free_tier_guards_exhausted"; break
        if not router.ground.can_spend() and not router.enterprise.can_spend():
            stop_reason = "resolution_free_tier_guards_exhausted"; break

        zip_code = str(zip_row["zip_code"])
        mark_zip_in_progress(query, campaign["id"], zip_code, run_id)
        metrics = {
            "page_count": 0, "raw_places": 0, "quality_passes": 0,
            "net_new_domains": 0, "duplicate_place_ids": 0, "duplicate_domains": 0,
            "grounding_resolved": 0, "enterprise_resolved": 0,
        }
        page_token = None
        zip_error = None
        target_hit = False
        next_token_remaining = False

        for page_number in range(1, max_pages + 1):
            if len(accepted) >= target:
                target_hit = True; break

            body = router.search_body(
                text_query=str(google.get("query_template") or "lawyer in {zip_code}").format(zip_code=zip_code),
                included_type=str(google.get("included_type") or "lawyer"),
                min_rating=float(google.get("min_rating_search_filter") or 4.0),
                page_size=page_size,
                page_token=page_token,
                location_restriction=rectangle(float(zip_row["latitude"]), float(zip_row["longitude"]), half_span),
            )
            context = f"batch={args.batch_label};zip={zip_code};page={page_number}"

            try:
                if router.ground.can_spend():
                    payload = router._post_places(body, PRO_FIELD_MASK, router.pro, context + ";mode=pro")
                    pro_places = [
                        p for p in (payload.get("places") or [])
                        if p.get("id") and p.get("businessStatus") == "OPERATIONAL"
                    ]
                    metrics["page_count"] += 1
                    metrics["raw_places"] += len(payload.get("places") or [])
                    metrics["quality_passes"] += len(pro_places)

                    # CRITICAL: Place-ID dedupe happens BEFORE any Grounding call.
                    fresh_places = []
                    for place in pro_places:
                        pid = str(place["id"])
                        if pid in existing_ids or pid in run_seen_ids:
                            metrics["duplicate_place_ids"] += 1
                            continue
                        run_seen_ids.add(pid)
                        fresh_places.append(place)

                    resolved: list[dict] = []
                    unresolved: set[str] = set()
                    for place in fresh_places:
                        if len(accepted) + len(resolved) >= target:
                            target_hit = True
                            break
                        grounded = router._ground_one(place)
                        if grounded.get("ok"):
                            d = business_domain(grounded.get("url"))
                            if d and not blocked(d):
                                resolved.append({
                                    "place_id": str(place["id"]),
                                    "website_domain": d,
                                    "resolution_method": "maps_grounding_lite",
                                })
                                continue
                        unresolved.add(str(place["id"]))

                    # One Enterprise page fallback can resolve every failed/unresolved fresh Place ID.
                    if unresolved and router.enterprise.can_spend():
                        ep = router._post_places(body, ENTERPRISE_FIELD_MASK, router.enterprise, context + ";mode=enterprise_page_fallback")
                        by_id = {r["place_id"]: r for r in enterprise_rows(ep)}
                        for pid in sorted(unresolved):
                            if pid in by_id:
                                resolved.append(by_id[pid])
                        unresolved = {pid for pid in unresolved if pid not in by_id}

                    page_payload = payload
                else:
                    if not router.enterprise.can_spend():
                        stop_reason = "resolution_free_tier_guards_exhausted"
                        break
                    page_payload = router._post_places(body, ENTERPRISE_FIELD_MASK, router.enterprise, context + ";mode=enterprise_direct")
                    rows = enterprise_rows(page_payload)
                    metrics["page_count"] += 1
                    metrics["raw_places"] += len(page_payload.get("places") or [])
                    metrics["quality_passes"] += sum(1 for p in (page_payload.get("places") or []) if p.get("id") and p.get("businessStatus") == "OPERATIONAL")
                    resolved = []
                    for row in rows:
                        pid = row["place_id"]
                        if pid in existing_ids or pid in run_seen_ids:
                            metrics["duplicate_place_ids"] += 1
                            continue
                        run_seen_ids.add(pid)
                        resolved.append(row)

                save_rows: list[dict] = []
                for row in resolved:
                    if len(accepted) + len(save_rows) >= target:
                        target_hit = True; break
                    pid = row["place_id"]
                    d = business_domain(row["website_domain"])
                    if not d or blocked(d):
                        continue
                    if d in existing_domains or d in run_seen_domains:
                        metrics["duplicate_domains"] += 1
                        continue
                    run_seen_domains.add(d)
                    save_rows.append({
                        "place_id": pid,
                        "website_domain": d,
                        "source_zip": zip_code,
                        "source_city": zip_row.get("city"),
                        "source_state": zip_row.get("state_code"),
                        "resolution_method": row["resolution_method"],
                        "status": "Ready for Crawl Evidence",
                    })

                # Persist after each page. A cancelled run resumes safely via global Place-ID/domain dedupe.
                persist_zip_rows(query, campaign, run_id, zip_row, save_rows)
                for row in save_rows:
                    accepted.append(row)
                    existing_ids.add(row["place_id"])
                    existing_domains.add(row["website_domain"])
                    metrics["net_new_domains"] += 1
                    if row["resolution_method"] == "maps_grounding_lite":
                        metrics["grounding_resolved"] += 1
                    else:
                        metrics["enterprise_resolved"] += 1

                next_token = page_payload.get("nextPageToken")
                next_token_remaining = bool(next_token)
                if target_hit or not next_token:
                    break
                if page_number == 1 and len(page_payload.get("places") or []) < raw_floor:
                    next_token_remaining = False
                    break
                page_token = next_token

            except Exception as exc:
                zip_error = f"{type(exc).__name__}: {exc}"
                break

        if zip_error:
            zip_status = "failed"; note = f"V7 batch error: {zip_error}"
        elif target_hit or len(accepted) >= target:
            zip_status = "partial"; note = "V7 batch stopped inside ZIP because batch target was reached."
        elif stop_reason.endswith("guards_exhausted"):
            zip_status = "partial"; note = f"V7 zero-paid stop: {stop_reason}."
        elif next_token_remaining and metrics["page_count"] >= max_pages:
            zip_status = "saturated"; note = f"V7 reached max_pages_per_zip={max_pages}."
        else:
            zip_status = "covered"; note = "V7 ZIP pass completed; minRating>=4.0, no review-count gate."

        finish_zip(query, campaign["id"], run_id, zip_row, zip_status, metrics, note)
        zip_log.append({
            "zip_code": zip_code, "city": zip_row.get("city"), "state": zip_row.get("state_code"),
            "status": zip_status, **metrics, "accepted_total_after_zip": len(accepted), "note": note,
        })
        print(
            f"[{zip_index}/{len(zip_rows)}] {zip_code} {zip_row.get('city')}, {zip_row.get('state_code')} "
            f"pages={metrics['page_count']} raw={metrics['raw_places']} fresh_new={metrics['net_new_domains']} "
            f"dup_pid={metrics['duplicate_place_ids']} dup_domain={metrics['duplicate_domains']} "
            f"ground={metrics['grounding_resolved']} ent={metrics['enterprise_resolved']} total={len(accepted)}/{target}",
            flush=True,
        )

        if len(accepted) >= target:
            stop_reason = "target_reached"; break
        if stop_reason.endswith("guards_exhausted"):
            break

    completed = len(accepted) >= target
    if not completed and stop_reason == "target_reached":
        stop_reason = "zip_queue_exhausted"
    completed_at = now_iso()
    summary = {
        "campaign": campaign["id"],
        "batch_label": args.batch_label,
        "run_id": run_id,
        "target_net_new_domains": target,
        "net_new_domains_collected": len(accepted),
        "status": "completed" if completed else f"partial_{stop_reason}",
        "stop_reason": stop_reason,
        "minimum_rating": float(google.get("min_rating_search_filter") or 4.0),
        "minimum_review_count_gate_enabled": False,
        "place_id_dedupe_before_grounding": True,
        "open_web_resolver_used": False,
        "crawl4ai_run_inside_discovery": False,
        "status_after_discovery": "Ready for Crawl Evidence",
        "zip_rows_processed": len(zip_log),
        "stale_in_progress_recovered": recovered,
        "zip_plan_sync": sync,
        "budget_before": budget_before,
        "budget_after": router.budget_snapshot(),
        "started_at": started,
        "completed_at": completed_at,
        "zero_paid_mode": True,
        "note": "Internal SKU guards are intentionally below published free caps. D1 ledger is repo-local; buffers remain in place for untracked benchmark/project usage.",
    }
    out_dir = ROOT / args.out_dir
    write_outputs(out_dir, accepted, summary, zip_log)
    query(
        "UPDATE campaign_runs SET completed_at=?,discovered_count=?,qualified_count=0,summary_json=?,status=? WHERE id=?",
        [completed_at, len(accepted), json.dumps(summary, separators=(",", ":")), summary["status"], run_id],
    )
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == "__main__":
    main()
