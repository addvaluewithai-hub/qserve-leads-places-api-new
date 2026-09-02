#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from d1_helpers import apply_schema, canonical_domain, make_query_client, result_rows
from market_manager import expand_markets, load_campaign, load_plan, sync_plan


def read_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def main() -> None:
    parser = argparse.ArgumentParser(description="Bootstrap the validated first 1,000 lawyer domains into lawyers-us D1 campaign")
    parser.add_argument("--campaign", default="lawyers-us")
    parser.add_argument("--input-dir", required=True, help="Directory containing lawyers_1000.csv, summary.json and search_log.json")
    args = parser.parse_args()

    input_dir = Path(args.input_dir)
    leads_path = input_dir / "lawyers_1000.csv"
    summary_path = input_dir / "summary.json"
    search_log_path = input_dir / "search_log.json"
    for path in (leads_path, summary_path, search_log_path):
        if not path.exists():
            raise SystemExit(f"Missing bootstrap file: {path}")

    rows = read_csv(leads_path)
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    search_log = json.loads(search_log_path.read_text(encoding="utf-8"))
    campaign = load_campaign(args.campaign)
    plan = load_plan(campaign)

    query = make_query_client()
    apply_schema(query)
    sync_plan(query, campaign, plan)

    run_id = f"bootstrap-{(plan.get('historical_seed') or {}).get('source_working_set_run_id') or 'first1000'}"
    now = datetime.now(timezone.utc).isoformat()
    query(
        """
        INSERT INTO campaign_runs (id,campaign_id,started_at,completed_at,discovered_count,qualified_count,summary_json,status)
        VALUES (?,?,?,?,?,?,?,?)
        ON CONFLICT(id) DO UPDATE SET
          completed_at=excluded.completed_at,
          discovered_count=excluded.discovered_count,
          summary_json=excluded.summary_json,
          status=excluded.status
        """,
        [run_id, campaign["id"], now, now, len(rows), 0, json.dumps(summary, separators=(",", ":")), "completed"],
    )

    source_counts = Counter(r.get("source_market") for r in rows if r.get("source_market"))
    inserted_memberships = 0
    reused_canonical_domains = 0

    for index, row in enumerate(rows, 1):
        place_id = row.get("place_id")
        domain = canonical_domain(row.get("website") or row.get("website_domain"))
        if not place_id or not domain:
            continue

        existing_domain_rows = result_rows(query(
            "SELECT lead_id FROM lead_domains WHERE website_domain=? LIMIT 1", [domain]
        ))
        canonical_id = str(existing_domain_rows[0]["lead_id"]) if existing_domain_rows else place_id
        if canonical_id != place_id:
            reused_canonical_domains += 1
        else:
            query(
                """
                INSERT INTO leads (
                  id,name,rating,user_rating_count,business_status,website,google_maps_url,address,
                  source_label,source_query,source_type,source_area,status,first_source_batch,latest_source_batch
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(id) DO UPDATE SET
                  name=excluded.name,
                  rating=excluded.rating,
                  user_rating_count=excluded.user_rating_count,
                  business_status=excluded.business_status,
                  website=excluded.website,
                  google_maps_url=excluded.google_maps_url,
                  address=excluded.address,
                  source_label=excluded.source_label,
                  source_query=excluded.source_query,
                  source_type=excluded.source_type,
                  source_area=excluded.source_area,
                  status=excluded.status,
                  latest_source_batch=excluded.latest_source_batch,
                  last_seen_at=CURRENT_TIMESTAMP
                """,
                [
                    place_id, row.get("name") or "Unnamed business", float(row.get("rating") or 0),
                    int(float(row.get("review_count") or 0)), "OPERATIONAL", row.get("website"),
                    row.get("google_maps_source"), row.get("address"), campaign.get("name"), "lawyer",
                    campaign.get("vertical"), row.get("source_market"), "Ready for Validation", run_id, run_id,
                ],
            )
            query(
                """
                INSERT INTO lead_domains (lead_id,website_domain,verified,source,updated_at)
                VALUES (?,?,?,?,CURRENT_TIMESTAMP)
                ON CONFLICT(lead_id) DO UPDATE SET
                  website_domain=excluded.website_domain,
                  verified=excluded.verified,
                  source=excluded.source,
                  updated_at=CURRENT_TIMESTAMP
                """,
                [
                    place_id, domain,
                    1 if str(row.get("website_verified_open_web") or "").lower() in {"true", "1", "yes"} else 0,
                    "bootstrap_maps_grounding_lite",
                ],
            )

        query(
            """
            INSERT INTO campaign_leads (
              campaign_id,lead_id,qualified,quality_score,qualification_reason,source_area,source_query,source_term,
              status,first_seen_at,last_seen_at,last_run_id
            ) VALUES (?,?,?,?,?,?,?,?,?,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP,?)
            ON CONFLICT(campaign_id,lead_id) DO UPDATE SET
              qualified=0,
              qualification_reason=excluded.qualification_reason,
              source_area=excluded.source_area,
              source_query=excluded.source_query,
              status=excluded.status,
              last_seen_at=CURRENT_TIMESTAMP,
              last_run_id=excluded.last_run_id
            """,
            [
                campaign["id"], canonical_id, 0, 0, "working_set_ready_for_validation",
                row.get("source_market"), "lawyer", "historical-first-1000", "Ready for Validation", run_id,
            ],
        )
        inserted_memberships += 1
        if index % 100 == 0:
            print(f"Bootstrapped {index}/{len(rows)} rows")

    plan_by_label = {m["label"]: m for m in expand_markets(plan)}
    search_by_market = {x.get("market"): x for x in search_log if x.get("market")}
    for market_label in summary.get("markets_used") or []:
        market = plan_by_label.get(market_label)
        if not market:
            continue
        meta = search_by_market.get(market_label) or {}
        domains_from_market = int(source_counts.get(market_label) or 0)
        query(
            """
            UPDATE market_coverage
            SET status='covered_once',
                search_count=CASE WHEN search_count < 1 THEN 1 ELSE search_count END,
                raw_places=CASE WHEN raw_places < ? THEN ? ELSE raw_places END,
                net_new_domains=CASE WHEN net_new_domains < ? THEN ? ELSE net_new_domains END,
                last_yield_per_search=?,
                first_searched_at=COALESCE(first_searched_at, ?),
                last_searched_at=COALESCE(last_searched_at, ?),
                last_run_id=?,
                notes=CASE WHEN notes='' THEN 'Bootstrapped from first validated 1,000-domain build' ELSE notes END,
                updated_at=CURRENT_TIMESTAMP
            WHERE campaign_id=? AND market_key=?
            """,
            [
                int(meta.get("result_count") or 0), int(meta.get("result_count") or 0),
                domains_from_market, domains_from_market, float(domains_from_market),
                now, now, run_id, campaign["id"], market["key"],
            ],
        )

    print(json.dumps({
        "campaign": campaign["id"],
        "bootstrap_run_id": run_id,
        "source_rows": len(rows),
        "campaign_memberships_written": inserted_memberships,
        "existing_domains_reused_as_canonical_leads": reused_canonical_domains,
        "markets_seeded": len(summary.get("markets_used") or []),
    }, indent=2))


if __name__ == "__main__":
    main()
