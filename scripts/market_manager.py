#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone

from d1_helpers import ROOT, apply_schema, make_query_client, result_rows

VALID_STATUSES = {"queued", "partial", "covered_once", "exhausted", "cooling"}


def load_campaign(campaign_id: str) -> dict:
    path = ROOT / "campaigns" / f"{campaign_id}.json"
    if not path.exists():
        raise SystemExit(f"Campaign config not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def load_plan(campaign: dict) -> dict:
    relative = campaign.get("market_plan")
    if not relative:
        raise SystemExit(f"Campaign {campaign['id']} has no market_plan")
    path = ROOT / relative
    if not path.exists():
        raise SystemExit(f"Market plan not found: {path}")
    plan = json.loads(path.read_text(encoding="utf-8"))
    if plan.get("campaign_id") != campaign.get("id"):
        raise SystemExit("Market plan campaign_id mismatch")
    return plan


def expand_markets(plan: dict) -> list[dict]:
    if plan.get("markets"):
        return list(plan.get("markets") or [])
    expanded = []
    for group in plan.get("groups") or []:
        for label in group.get("markets") or []:
            city, state = [part.strip() for part in label.rsplit(",", 1)]
            import re
            slug = re.sub(r"[^a-z0-9]+", "-", city.lower()).strip("-")
            expanded.append({
                "key": f"{state.lower()}-{slug}",
                "label": label,
                "state": state,
                "tier": int(group.get("tier") or 1),
                "priority": int(group.get("priority") or 100),
                "phase": group.get("phase") or "",
                "seed_status": group.get("seed_status") or "queued",
            })
    return expanded


def ensure_campaign(query, campaign: dict) -> None:
    query(
        """
        INSERT INTO campaigns (id,name,vertical,description,config_json,active,updated_at)
        VALUES (?,?,?,?,?,1,CURRENT_TIMESTAMP)
        ON CONFLICT(id) DO UPDATE SET
          name=excluded.name,
          vertical=excluded.vertical,
          description=excluded.description,
          config_json=excluded.config_json,
          active=1,
          updated_at=CURRENT_TIMESTAMP
        """,
        [
            campaign["id"], campaign.get("name") or campaign["id"], campaign.get("vertical") or "unknown",
            campaign.get("description") or "", json.dumps(campaign, ensure_ascii=False, separators=(",", ":")),
        ],
    )


def sync_plan(query, campaign: dict, plan: dict) -> dict:
    ensure_campaign(query, campaign)
    inserted = 0
    for market in expand_markets(plan):
        status = market.get("seed_status") or "queued"
        if status not in VALID_STATUSES:
            raise SystemExit(f"Invalid seed_status {status} for {market.get('label')}")
        before = result_rows(query(
            "SELECT status FROM market_coverage WHERE campaign_id=? AND market_key=?",
            [campaign["id"], market["key"]],
        ))
        query(
            """
            INSERT INTO market_coverage (
              campaign_id,market_key,market_label,state_code,tier,priority,phase,status,updated_at
            ) VALUES (?,?,?,?,?,?,?,?,CURRENT_TIMESTAMP)
            ON CONFLICT(campaign_id,market_key) DO UPDATE SET
              market_label=excluded.market_label,
              state_code=excluded.state_code,
              tier=excluded.tier,
              priority=excluded.priority,
              phase=excluded.phase,
              updated_at=CURRENT_TIMESTAMP
            """,
            [
                campaign["id"], market["key"], market["label"], market.get("state"),
                int(market.get("tier") or 1), int(market.get("priority") or 100),
                market.get("phase") or "", status,
            ],
        )
        if not before:
            inserted += 1
    return {"plan_markets": len(expand_markets(plan)), "new_market_rows": inserted}


def mark_historical_seed(query, campaign: dict, plan: dict) -> dict:
    historical = [m for m in expand_markets(plan) if m.get("seed_status") == "covered_once"]
    changed = 0
    for market in historical:
        rows = result_rows(query(
            "SELECT search_count,status FROM market_coverage WHERE campaign_id=? AND market_key=?",
            [campaign["id"], market["key"]],
        ))
        if not rows:
            continue
        if int(rows[0].get("search_count") or 0) > 0:
            continue
        query(
            """
            UPDATE market_coverage
            SET status='covered_once', search_count=1,
                first_searched_at=COALESCE(first_searched_at, '2026-09-02T00:00:00+00:00'),
                last_searched_at=COALESCE(last_searched_at, '2026-09-02T00:00:00+00:00'),
                last_run_id=COALESCE(last_run_id, ?),
                notes=CASE WHEN notes='' THEN 'Seeded from first validated 1,000-domain run' ELSE notes END,
                updated_at=CURRENT_TIMESTAMP
            WHERE campaign_id=? AND market_key=?
            """,
            [
                (plan.get("historical_seed") or {}).get("source_working_set_run_id") or "historical-seed",
                campaign["id"], market["key"],
            ],
        )
        changed += 1
    return {"historical_markets_seeded": changed}


def next_markets(query, campaign: dict, plan: dict, limit: int) -> list[dict]:
    policy = plan.get("selection_policy") or {}
    revisit_days = int(policy.get("revisit_after_days") or 90)
    cutoff = (datetime.now(timezone.utc) - timedelta(days=revisit_days)).isoformat()

    rows = result_rows(query(
        """
        SELECT campaign_id,market_key,market_label,state_code,tier,priority,phase,status,
               search_count,raw_places,net_new_place_ids,grounding_calls,quality_passes,
               net_new_domains,last_yield_per_search,first_searched_at,last_searched_at,last_run_id,notes
        FROM market_coverage
        WHERE campaign_id=?
          AND (
            status IN ('queued','partial')
            OR (status='covered_once' AND (last_searched_at IS NULL OR last_searched_at < ?))
          )
        ORDER BY
          CASE status WHEN 'queued' THEN 0 WHEN 'partial' THEN 1 ELSE 2 END,
          priority ASC,
          tier ASC,
          COALESCE(last_searched_at,'') ASC,
          market_label ASC
        LIMIT ?
        """,
        [campaign["id"], cutoff, limit],
    ))
    return rows


def status_report(query, campaign: dict, plan: dict, next_count: int) -> dict:
    summary_rows = result_rows(query(
        """
        SELECT status, COUNT(*) AS markets,
               SUM(search_count) AS searches,
               SUM(net_new_domains) AS net_new_domains
        FROM market_coverage
        WHERE campaign_id=?
        GROUP BY status
        ORDER BY status
        """,
        [campaign["id"]],
    ))
    state_rows = result_rows(query(
        """
        SELECT state_code,
               COUNT(*) AS markets,
               SUM(CASE WHEN status='queued' THEN 1 ELSE 0 END) AS queued,
               SUM(CASE WHEN status='covered_once' THEN 1 ELSE 0 END) AS covered_once,
               SUM(CASE WHEN status='partial' THEN 1 ELSE 0 END) AS partial,
               SUM(CASE WHEN status='exhausted' THEN 1 ELSE 0 END) AS exhausted,
               SUM(net_new_domains) AS net_new_domains
        FROM market_coverage
        WHERE campaign_id=?
        GROUP BY state_code
        ORDER BY queued DESC, state_code ASC
        """,
        [campaign["id"]],
    ))
    existing = result_rows(query(
        "SELECT COUNT(*) AS leads FROM campaign_leads WHERE campaign_id=?",
        [campaign["id"]],
    ))
    return {
        "campaign": campaign["id"],
        "campaign_leads_in_d1": int((existing[0] if existing else {}).get("leads") or 0),
        "market_status": summary_rows,
        "states": state_rows,
        "next_markets": next_markets(query, campaign, plan, next_count),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Manage market coverage / next-market queue in D1")
    parser.add_argument("command", choices=["sync", "status", "next"])
    parser.add_argument("--campaign", default="lawyers-us")
    parser.add_argument("--next", type=int, default=20)
    parser.add_argument("--seed-historical", action="store_true")
    args = parser.parse_args()

    campaign = load_campaign(args.campaign)
    plan = load_plan(campaign)
    query = make_query_client()
    apply_schema(query)

    sync_result = sync_plan(query, campaign, plan)
    seed_result = mark_historical_seed(query, campaign, plan) if args.seed_historical else {}

    if args.command == "sync":
        print(json.dumps({**sync_result, **seed_result}, indent=2))
    elif args.command == "next":
        print(json.dumps(next_markets(query, campaign, plan, args.next), indent=2))
    else:
        print(json.dumps({**sync_result, **seed_result, **status_report(query, campaign, plan, args.next)}, indent=2))


if __name__ == "__main__":
    main()
