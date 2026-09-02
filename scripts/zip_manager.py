#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone

import pgeocode

from d1_helpers import ROOT, apply_schema, make_query_client, result_rows

VALID_STATUSES = {"queued", "in_progress", "partial", "covered", "saturated", "failed", "cooling"}


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
        raise SystemExit(f"ZIP market plan not found: {path}")
    plan = json.loads(path.read_text(encoding="utf-8"))
    if plan.get("campaign_id") != campaign.get("id"):
        raise SystemExit("ZIP market plan campaign_id mismatch")
    return plan


def state_rules(plan: dict) -> dict[str, dict]:
    rules: dict[str, dict] = {}
    for phase in plan.get("phases") or []:
        for state in phase.get("states") or []:
            code = str(state.get("state") or "").upper()
            if not code:
                continue
            rules[code] = {
                "phase": phase.get("phase") or "",
                "state_priority": int(phase.get("priority") or 100),
                "preferred_cities": [str(x).strip().lower() for x in state.get("preferred_cities") or [] if str(x).strip()],
            }
    return rules


def normalize_zip(value) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if "." in text:
        text = text.split(".", 1)[0]
    text = "".join(ch for ch in text if ch.isdigit())
    if not text:
        return None
    return text.zfill(5)[:5]


def load_zip_universe(plan: dict) -> list[dict]:
    rules = state_rules(plan)
    nomi = pgeocode.Nominatim("us")
    frame = nomi._data
    rows: list[dict] = []

    for record in frame.to_dict("records"):
        state = str(record.get("state_code") or "").upper().strip()
        rule = rules.get(state)
        if not rule:
            continue
        zip_code = normalize_zip(record.get("postal_code"))
        if not zip_code:
            continue
        latitude = record.get("latitude")
        longitude = record.get("longitude")
        try:
            latitude = float(latitude)
            longitude = float(longitude)
        except (TypeError, ValueError):
            continue
        if latitude != latitude or longitude != longitude:
            continue

        city = str(record.get("place_name") or "").strip()
        city_lower = city.lower()
        preferred = rule["preferred_cities"]
        try:
            city_priority = preferred.index(city_lower)
        except ValueError:
            city_priority = 1000

        rows.append({
            "zip_code": zip_code,
            "city": city,
            "state_code": state,
            "latitude": latitude,
            "longitude": longitude,
            "phase": rule["phase"],
            "state_priority": rule["state_priority"],
            "city_priority": city_priority,
        })

    best: dict[str, dict] = {}
    for row in rows:
        current = best.get(row["zip_code"])
        if current is None or (row["state_priority"], row["city_priority"]) < (current["state_priority"], current["city_priority"]):
            best[row["zip_code"]] = row
    return sorted(best.values(), key=lambda r: (r["state_priority"], r["city_priority"], r["state_code"], r["city"], r["zip_code"]))


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
        [campaign["id"], campaign.get("name") or campaign["id"], campaign.get("vertical") or "unknown", campaign.get("description") or "", json.dumps(campaign, ensure_ascii=False, separators=(",", ":"))],
    )


def sync_zip_plan(query, campaign: dict, plan: dict) -> dict:
    ensure_campaign(query, campaign)
    universe = load_zip_universe(plan)
    inserted = 0
    for index, row in enumerate(universe, 1):
        existing = result_rows(query("SELECT zip_code FROM zip_coverage WHERE campaign_id=? AND zip_code=?", [campaign["id"], row["zip_code"]]))
        query(
            """
            INSERT INTO zip_coverage (
              campaign_id,zip_code,city,state_code,latitude,longitude,phase,
              state_priority,city_priority,status,updated_at
            ) VALUES (?,?,?,?,?,?,?,?,?,'queued',CURRENT_TIMESTAMP)
            ON CONFLICT(campaign_id,zip_code) DO UPDATE SET
              city=excluded.city,
              state_code=excluded.state_code,
              latitude=excluded.latitude,
              longitude=excluded.longitude,
              phase=excluded.phase,
              state_priority=excluded.state_priority,
              city_priority=excluded.city_priority,
              updated_at=CURRENT_TIMESTAMP
            """,
            [campaign["id"], row["zip_code"], row["city"], row["state_code"], row["latitude"], row["longitude"], row["phase"], row["state_priority"], row["city_priority"]],
        )
        if not existing:
            inserted += 1
        if index % 1000 == 0:
            print(f"ZIP plan synced {index}/{len(universe)}")
    return {"zip_universe": len(universe), "new_zip_rows": inserted}


def recover_stale_in_progress(query, campaign_id: str, stale_hours: int = 6) -> int:
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=stale_hours)).isoformat()
    rows = result_rows(query("SELECT zip_code FROM zip_coverage WHERE campaign_id=? AND status='in_progress' AND (last_searched_at IS NULL OR last_searched_at < ?)", [campaign_id, cutoff]))
    if rows:
        query(
            """
            UPDATE zip_coverage
            SET status='failed', notes=CASE WHEN notes='' THEN 'Recovered stale in_progress ZIP' ELSE notes END, updated_at=CURRENT_TIMESTAMP
            WHERE campaign_id=? AND status='in_progress' AND (last_searched_at IS NULL OR last_searched_at < ?)
            """,
            [campaign_id, cutoff],
        )
    return len(rows)


def next_zips(query, campaign: dict, plan: dict, limit: int) -> list[dict]:
    policy = plan.get("selection_policy") or {}
    retry_days = int(policy.get("retry_failed_after_days") or 7)
    revisit_days = int(policy.get("revisit_covered_after_days") or 180)
    now = datetime.now(timezone.utc)
    retry_cutoff = (now - timedelta(days=retry_days)).isoformat()
    revisit_cutoff = (now - timedelta(days=revisit_days)).isoformat()

    return result_rows(query(
        """
        SELECT campaign_id,zip_code,city,state_code,latitude,longitude,phase,
               state_priority,city_priority,status,search_count,page_count,
               raw_places,exact_zip_places,quality_passes,net_new_domains,
               duplicate_place_ids,duplicate_domains,last_searched_at,last_run_id,notes
        FROM zip_coverage
        WHERE campaign_id=?
          AND (
            status='queued'
            OR status='partial'
            OR (status='failed' AND (last_searched_at IS NULL OR last_searched_at < ?))
            OR (status IN ('covered','saturated') AND last_searched_at < ?)
          )
        ORDER BY
          CASE status WHEN 'queued' THEN 0 WHEN 'partial' THEN 1 WHEN 'failed' THEN 2 ELSE 3 END,
          state_priority ASC,
          city_priority ASC,
          state_code ASC,
          zip_code ASC
        LIMIT ?
        """,
        [campaign["id"], retry_cutoff, revisit_cutoff, int(limit)],
    ))


def status_report(query, campaign: dict, plan: dict, next_count: int) -> dict:
    by_status = result_rows(query(
        """
        SELECT status, COUNT(*) AS zips, SUM(search_count) AS searches, SUM(page_count) AS pages,
               SUM(raw_places) AS raw_places, SUM(exact_zip_places) AS exact_zip_places,
               SUM(net_new_domains) AS net_new_domains
        FROM zip_coverage WHERE campaign_id=? GROUP BY status ORDER BY status
        """,
        [campaign["id"]],
    ))
    by_state = result_rows(query(
        """
        SELECT state_code, COUNT(*) AS total_zips,
               SUM(CASE WHEN status='queued' THEN 1 ELSE 0 END) AS queued,
               SUM(CASE WHEN status='partial' THEN 1 ELSE 0 END) AS partial,
               SUM(CASE WHEN status='covered' THEN 1 ELSE 0 END) AS covered,
               SUM(CASE WHEN status='saturated' THEN 1 ELSE 0 END) AS saturated,
               SUM(CASE WHEN status='failed' THEN 1 ELSE 0 END) AS failed,
               SUM(net_new_domains) AS net_new_domains
        FROM zip_coverage WHERE campaign_id=? GROUP BY state_code ORDER BY MIN(state_priority), state_code
        """,
        [campaign["id"]],
    ))
    leads = result_rows(query("SELECT COUNT(*) AS n FROM leads"))
    suppressed = result_rows(query("SELECT COUNT(*) AS n FROM outreach_suppression WHERE suppressed=1"))
    return {
        "campaign": campaign["id"],
        "canonical_businesses_in_d1": int((leads[0] if leads else {}).get("n") or 0),
        "globally_suppressed_businesses": int((suppressed[0] if suppressed else {}).get("n") or 0),
        "zip_status": by_status,
        "states": by_state,
        "next_zips": next_zips(query, campaign, plan, next_count),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Manage ZIP-level lawyer search coverage in D1")
    parser.add_argument("command", choices=["sync", "status", "next"])
    parser.add_argument("--campaign", default="lawyers-us")
    parser.add_argument("--next", type=int, default=25)
    args = parser.parse_args()

    campaign = load_campaign(args.campaign)
    plan = load_plan(campaign)
    query = make_query_client()
    apply_schema(query)
    recovered = recover_stale_in_progress(query, campaign["id"])
    sync_result = sync_zip_plan(query, campaign, plan)

    if args.command == "sync":
        print(json.dumps({**sync_result, "stale_in_progress_recovered": recovered}, indent=2))
    elif args.command == "next":
        print(json.dumps(next_zips(query, campaign, plan, args.next), indent=2))
    else:
        print(json.dumps({**sync_result, "stale_in_progress_recovered": recovered, **status_report(query, campaign, plan, args.next)}, indent=2))


if __name__ == "__main__":
    main()
