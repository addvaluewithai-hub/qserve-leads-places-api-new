#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import os
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

from benchmark_lawyer_discovery import SEARCH_URL, api_post, ground_one
from build_1000_lawyers import canonical_domain, verify_website
from d1_helpers import ROOT, apply_schema, make_query_client, result_rows
from market_manager import load_campaign, load_plan, next_markets, sync_plan

GROUNDING_SUBMIT_DELAY_SECONDS = 0.25


def campaign_search(key: str, campaign: dict, market: dict) -> tuple[dict, list[dict]]:
    google = campaign.get("google") or {}
    fields = google.get("field_mask") or [
        "places.id", "places.displayName", "places.formattedAddress", "places.businessStatus"
    ]
    body = {
        "textQuery": str(google.get("query_template") or "lawyer in {market}").format(market=market["market_label"]),
        "includedType": google.get("included_type") or "lawyer",
        "strictTypeFiltering": bool(google.get("strict_type_filtering", True)),
        "minRating": float(google.get("min_rating_search_filter") or 4.7),
        "pageSize": int(google.get("page_size") or 20),
        "regionCode": google.get("region_code") or "US",
        "languageCode": google.get("language_code") or "en",
    }
    response = api_post(SEARCH_URL, key=key, body=body, field_mask=",".join(fields), timeout=60)
    meta = {
        "market_key": market["market_key"],
        "market": market["market_label"],
        "http_status": response.status_code,
        "result_count": 0,
        "error": None,
    }
    if response.status_code != 200:
        meta["error"] = response.text[:1200]
        return meta, []
    payload = response.json()
    rows = []
    for place in payload.get("places") or []:
        place_id = place.get("id")
        if not place_id:
            continue
        display = place.get("displayName") or {}
        rows.append({
            "place_id": place_id,
            "name": display.get("text") or "Unnamed business",
            "address": place.get("formattedAddress") or "",
            "business_status": place.get("businessStatus"),
            "source_market": market["market_label"],
            "market_key": market["market_key"],
        })
    meta["result_count"] = len(rows)
    return meta, rows


def ground_verify(key: str, row: dict, campaign: dict) -> dict:
    grounded = ground_one(key, row)
    quality = campaign.get("quality") or {}
    qualifies = (
        grounded.get("grounding_identity_match")
        and grounded.get("website_domain")
        and grounded.get("business_status") in (quality.get("allowed_business_statuses") or ["OPERATIONAL"])
        and float(grounded.get("rating") or 0) >= float(quality.get("min_rating") or 0)
        and int(grounded.get("review_count") or 0) >= int(quality.get("min_reviews") or 0)
    )
    grounded["passed_quality_gate"] = bool(qualifies)
    if qualifies:
        grounded.update(verify_website(grounded.get("website")))
        final_url = grounded.get("website_final_url") or grounded.get("website")
        grounded["website"] = final_url
        grounded["website_domain"] = canonical_domain(final_url)
    return grounded


def existing_campaign_state(query, campaign_id: str) -> tuple[set[str], set[str]]:
    rows = result_rows(query(
        """
        SELECT l.id, COALESCE(ld.website_domain, '') AS website_domain
        FROM campaign_leads cl
        JOIN leads l ON l.id=cl.lead_id
        LEFT JOIN lead_domains ld ON ld.lead_id=l.id
        WHERE cl.campaign_id=?
        """,
        [campaign_id],
    ))
    ids = {str(r["id"]) for r in rows if r.get("id")}
    domains = {str(r["website_domain"]).lower() for r in rows if r.get("website_domain")}
    return ids, domains


def global_domains(query) -> set[str]:
    return {
        str(r["website_domain"]).lower()
        for r in result_rows(query("SELECT website_domain FROM lead_domains"))
        if r.get("website_domain")
    }


def update_market_metrics(query, campaign_id: str, run_id: str, market: dict, metrics: dict, plan: dict) -> None:
    policy = plan.get("selection_policy") or {}
    partial_floor = int(policy.get("minimum_net_new_domains_for_partial") or 5)
    exhausted_floor = int(policy.get("exhausted_yield_threshold") or 2)
    new_domains = int(metrics.get("net_new_domains") or 0)
    if new_domains <= exhausted_floor:
        status = "exhausted"
    elif new_domains >= partial_floor:
        status = "partial"
    else:
        status = "covered_once"

    now = datetime.now(timezone.utc).isoformat()
    query(
        """
        UPDATE market_coverage
        SET status=?, search_count=search_count+1, raw_places=raw_places+?,
            net_new_place_ids=net_new_place_ids+?, grounding_calls=grounding_calls+?,
            quality_passes=quality_passes+?, net_new_domains=net_new_domains+?,
            last_yield_per_search=?, first_searched_at=COALESCE(first_searched_at, ?),
            last_searched_at=?, last_run_id=?, updated_at=CURRENT_TIMESTAMP
        WHERE campaign_id=? AND market_key=?
        """,
        [
            status, metrics.get("raw_places", 0), metrics.get("net_new_place_ids", 0),
            metrics.get("grounding_calls", 0), metrics.get("quality_passes", 0), new_domains,
            float(new_domains), now, now, run_id, campaign_id, market["market_key"],
        ],
    )
    query(
        """
        INSERT INTO market_run_history (
          id,campaign_id,run_id,market_key,market_label,searched_at,raw_places,net_new_place_ids,
          grounding_calls,quality_passes,net_new_domains,status_after,note
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        [
            str(uuid.uuid4()), campaign_id, run_id, market["market_key"], market["market_label"], now,
            metrics.get("raw_places", 0), metrics.get("net_new_place_ids", 0), metrics.get("grounding_calls", 0),
            metrics.get("quality_passes", 0), new_domains, status, metrics.get("note") or "",
        ],
    )


def safe_row(row: dict) -> dict:
    return {
        "place_id": row.get("place_id"), "name": row.get("name"), "address": row.get("address"),
        "source_market": row.get("source_market"), "market_key": row.get("market_key"),
        "website": row.get("website"), "website_domain": canonical_domain(row.get("website")),
        "website_title": row.get("website_title"), "website_http_status": row.get("website_http_status"),
        "google_maps_source": row.get("google_maps_source"), "rating": row.get("rating"),
        "review_count": row.get("review_count"), "grounding_identity_match": bool(row.get("grounding_identity_match")),
        "website_verified_open_web": bool(row.get("website_verified_open_web")),
        "campaign_status": "Ready for Validation", "qualified": False,
    }


def write_outputs(out_dir: Path, selected: list[dict], summary: dict, market_log: list[dict]) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "leads.json").write_text(json.dumps(selected, ensure_ascii=False, indent=2), encoding="utf-8")
    (out_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    (out_dir / "market_log.json").write_text(json.dumps(market_log, ensure_ascii=False, indent=2), encoding="utf-8")
    fields = [
        "place_id","name","address","source_market","market_key","website","website_domain",
        "website_title","website_http_status","google_maps_source","rating","review_count",
        "grounding_identity_match","website_verified_open_web","campaign_status","qualified",
    ]
    with (out_dir / "leads.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader(); writer.writerows(selected)


def insert_selected_into_d1(query, campaign: dict, run_id: str, selected: list[dict]) -> None:
    batch = f"{campaign['id']}:{run_id}"
    for index, row in enumerate(selected, 1):
        query(
            """
            INSERT INTO leads (
              id,name,rating,user_rating_count,business_status,website,google_maps_url,address,
              source_label,source_query,source_type,source_area,status,first_source_batch,latest_source_batch
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET
              name=excluded.name, rating=excluded.rating, user_rating_count=excluded.user_rating_count,
              business_status=excluded.business_status, website=excluded.website,
              google_maps_url=excluded.google_maps_url, address=excluded.address,
              source_label=excluded.source_label, source_query=excluded.source_query,
              source_type=excluded.source_type, source_area=excluded.source_area,
              status=excluded.status, latest_source_batch=excluded.latest_source_batch,
              last_seen_at=CURRENT_TIMESTAMP
            """,
            [
                row["place_id"], row.get("name") or "Unnamed business", row.get("rating"),
                int(row.get("review_count") or 0), "OPERATIONAL", row.get("website"),
                row.get("google_maps_source"), row.get("address"), campaign.get("name"), "lawyer",
                campaign.get("vertical"), row.get("source_market"), "Ready for Validation", batch, batch,
            ],
        )
        query(
            """
            INSERT INTO lead_domains (lead_id,website_domain,verified,source,updated_at)
            VALUES (?,?,?,?,CURRENT_TIMESTAMP)
            ON CONFLICT(lead_id) DO UPDATE SET
              website_domain=excluded.website_domain, verified=excluded.verified,
              source=excluded.source, updated_at=CURRENT_TIMESTAMP
            """,
            [row["place_id"], row["website_domain"], 1 if row.get("website_verified_open_web") else 0, "maps_grounding_lite+open_web"],
        )
        query(
            """
            INSERT INTO campaign_leads (
              campaign_id,lead_id,qualified,quality_score,qualification_reason,source_area,source_query,source_term,
              status,first_seen_at,last_seen_at,last_run_id
            ) VALUES (?,?,?,?,?,?,?,?,?,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP,?)
            ON CONFLICT(campaign_id,lead_id) DO UPDATE SET
              qualified=0, qualification_reason=excluded.qualification_reason,
              source_area=excluded.source_area, source_query=excluded.source_query,
              source_term=excluded.source_term, status=excluded.status,
              last_seen_at=CURRENT_TIMESTAMP, last_run_id=excluded.last_run_id
            """,
            [
                campaign["id"], row["place_id"], 0, 0, "working_set_ready_for_validation",
                row.get("source_market"), "lawyer", row.get("market_key"), "Ready for Validation", run_id,
            ],
        )
        if index % 100 == 0:
            print(f"D1 synced {index}/{len(selected)} net-new leads")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the next net-new lawyer working set using D1 dedupe + managed market queue")
    parser.add_argument("--campaign", default="lawyers-us")
    parser.add_argument("--target", type=int, default=None)
    parser.add_argument("--max-markets", type=int, default=250)
    parser.add_argument("--out-dir", default=None)
    args = parser.parse_args()

    key = os.getenv("GOOGLE_API_KEY")
    if not key:
        raise SystemExit("GOOGLE_API_KEY is required")

    campaign = load_campaign(args.campaign)
    plan = load_plan(campaign)
    target = int(args.target or (campaign.get("working_set") or {}).get("target_net_new_domains_per_run") or 1000)
    out_dir = Path(args.out_dir) if args.out_dir else ROOT / "out" / f"{args.campaign}-next-{target}"

    query = make_query_client()
    apply_schema(query)
    sync_plan(query, campaign, plan)

    existing_ids, campaign_domains = existing_campaign_state(query, campaign["id"])
    historical_expected = int((plan.get("historical_seed") or {}).get("first_working_set_domains") or 0)
    if not existing_ids and historical_expected:
        raise SystemExit(
            f"Campaign {campaign['id']} has no D1 leads, but market plan records {historical_expected} historical leads. "
            "Run scripts/bootstrap_lawyers_us_campaign.py first so next-run dedupe is trustworthy."
        )

    existing_domains = set(campaign_domains) | global_domains(query)
    markets = next_markets(query, campaign, plan, args.max_markets)
    if not markets:
        raise SystemExit("No eligible markets remain in the market plan. Expand market_plans/lawyers-us.json or wait for revisit cooldown.")

    run_id = str(uuid.uuid4())
    started = datetime.now(timezone.utc).isoformat()
    query(
        "INSERT INTO campaign_runs (id,campaign_id,started_at,discovered_count,qualified_count,summary_json,status) VALUES (?,?,?,?,?,?,?)",
        [run_id, campaign["id"], started, 0, 0, "{}", "running"],
    )

    selected_by_domain: dict[str, dict] = {}
    batch_seen_place_ids: set[str] = set()
    market_log: list[dict] = []
    grounding_workers = int((campaign.get("grounding") or {}).get("workers") or 4)

    for market_index, market in enumerate(markets, 1):
        if len(selected_by_domain) >= target:
            break
        meta, rows = campaign_search(key, campaign, market)
        raw_count = len(rows)
        fresh = []
        for row in rows:
            pid = row.get("place_id")
            if not pid or pid in existing_ids or pid in batch_seen_place_ids:
                continue
            batch_seen_place_ids.add(pid)
            if row.get("business_status") != "OPERATIONAL":
                continue
            fresh.append(row)

        grounded_rows = []
        if fresh:
            with ThreadPoolExecutor(max_workers=grounding_workers) as pool:
                futures = []
                for row in fresh:
                    futures.append(pool.submit(ground_verify, key, row, campaign))
                    time.sleep(GROUNDING_SUBMIT_DELAY_SECONDS)
                for future in as_completed(futures):
                    grounded_rows.append(future.result())

        quality_rows = [r for r in grounded_rows if r.get("passed_quality_gate") and r.get("website_domain")]
        new_from_market = 0
        duplicate_domains = 0
        for grounded in quality_rows:
            domain = canonical_domain(grounded.get("website"))
            if not domain:
                continue
            if domain in existing_domains or domain in selected_by_domain:
                duplicate_domains += 1
                continue
            selected_by_domain[domain] = safe_row(grounded)
            new_from_market += 1
            if len(selected_by_domain) >= target:
                break

        metrics = {
            "raw_places": raw_count, "net_new_place_ids": len(fresh), "grounding_calls": len(grounded_rows),
            "quality_passes": len(quality_rows), "net_new_domains": new_from_market,
            "note": f"duplicate_or_existing_domains={duplicate_domains}; http_status={meta['http_status']}",
        }
        update_market_metrics(query, campaign["id"], run_id, market, metrics, plan)
        market_log.append({**meta, **metrics, "working_domains_after_market": len(selected_by_domain)})
        print(
            f"[{market_index}/{len(markets)}] {market['market_label']}: raw={raw_count} fresh_ids={len(fresh)} "
            f"quality={len(quality_rows)} new_domains={new_from_market} total={len(selected_by_domain)}/{target}"
        )

    selected = list(selected_by_domain.values())[:target]
    completed = len(selected) >= target
    summary = {
        "campaign": campaign["id"], "run_id": run_id, "target_net_new_domains": target,
        "net_new_domains_collected": len(selected), "existing_campaign_place_ids_before_run": len(existing_ids),
        "existing_domains_before_run": len(existing_domains), "markets_considered": len(market_log),
        "text_search_requests": len(market_log),
        "grounding_calls": sum(int(x.get("grounding_calls") or 0) for x in market_log),
        "status": "completed" if completed else "partial_market_plan_exhausted",
        "started_at": started, "completed_at": datetime.now(timezone.utc).isoformat(),
    }
    write_outputs(out_dir, selected, summary, market_log)

    if selected:
        insert_selected_into_d1(query, campaign, run_id, selected)

    query(
        """
        UPDATE campaign_runs
        SET completed_at=?, discovered_count=?, qualified_count=0, summary_json=?, status=?
        WHERE id=?
        """,
        [summary["completed_at"], len(selected), json.dumps(summary, separators=(",", ":")), summary["status"], run_id],
    )
    print(json.dumps(summary, indent=2))

    if not completed:
        remaining = target - len(selected)
        raise SystemExit(
            f"Only {len(selected)}/{target} net-new domains collected in this run. The {len(selected)} accepted leads WERE saved to D1. "
            f"Expand/reprioritize the market plan, then rerun with --target {remaining} to finish the original goal. "
            "Cross-run dedupe will prevent re-counting the saved leads."
        )


if __name__ == "__main__":
    main()
