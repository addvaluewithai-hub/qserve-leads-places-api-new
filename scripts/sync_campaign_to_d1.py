#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_FILE = ROOT / "schema.sql"


def env_required(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise SystemExit(f"{name} is required")
    return value


def make_query_client():
    account_id = env_required("CLOUDFLARE_ACCOUNT_ID")
    token = env_required("CLOUDFLARE_API_TOKEN")
    database_id = env_required("D1_DATABASE_ID")
    api_url = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/d1/database/{database_id}/query"

    def query(sql: str, params=None):
        body = {"sql": sql}
        if params is not None:
            body["params"] = params
        request = urllib.request.Request(
            api_url,
            data=json.dumps(body).encode("utf-8"),
            method="POST",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=60) as response:
            payload = json.loads(response.read().decode("utf-8"))
        if not payload.get("success"):
            raise RuntimeError(payload)
        results = payload.get("result") or []
        for result in results:
            if result.get("success") is False:
                raise RuntimeError(result)
        return results

    return query


def load_json(path: Path):
    if not path.exists():
        raise SystemExit(f"Missing campaign output: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def apply_schema(query) -> None:
    schema = SCHEMA_FILE.read_text(encoding="utf-8")
    for statement in [part.strip() for part in schema.split(";") if part.strip()]:
        query(statement)


def main() -> None:
    parser = argparse.ArgumentParser(description="Sync one campaign run into Cloudflare D1")
    parser.add_argument("--campaign", required=True)
    parser.add_argument("--out-dir", default=None)
    args = parser.parse_args()

    out_dir = Path(args.out_dir) if args.out_dir else ROOT / "out" / args.campaign
    campaign = load_json(out_dir / "campaign.json")
    rows = load_json(out_dir / "all_candidates.json")
    summary = load_json(out_dir / "summary.json")
    if campaign.get("id") != args.campaign:
        raise SystemExit("Campaign output does not match --campaign")

    query = make_query_client()
    apply_schema(query)

    config_json = json.dumps(campaign, ensure_ascii=False, separators=(",", ":"))
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
        [campaign["id"], campaign.get("name"), campaign.get("vertical"), campaign.get("description"), config_json],
    )

    run_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    query(
        """
        INSERT INTO campaign_runs (id,campaign_id,started_at,completed_at,discovered_count,qualified_count,summary_json,status)
        VALUES (?,?,?,?,?,?,?,?)
        """,
        [run_id, campaign["id"], now, now, summary.get("discovered", 0), summary.get("qualified", 0), json.dumps(summary), "completed"],
    )

    lead_sql = """
    INSERT INTO leads (
      id,name,price_level,rating,user_rating_count,business_status,phone,website,
      google_maps_url,address,latitude,longitude,primary_type,types,opening_hours,
      source_label,source_query,source_type,source_area,first_source_batch,latest_source_batch
    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    ON CONFLICT(id) DO UPDATE SET
      name=excluded.name,
      price_level=excluded.price_level,
      rating=excluded.rating,
      user_rating_count=excluded.user_rating_count,
      business_status=excluded.business_status,
      phone=excluded.phone,
      website=excluded.website,
      google_maps_url=excluded.google_maps_url,
      address=excluded.address,
      latitude=excluded.latitude,
      longitude=excluded.longitude,
      primary_type=excluded.primary_type,
      types=excluded.types,
      opening_hours=excluded.opening_hours,
      source_query=excluded.source_query,
      source_area=excluded.source_area,
      latest_source_batch=excluded.latest_source_batch,
      last_seen_at=CURRENT_TIMESTAMP
    """

    membership_sql = """
    INSERT INTO campaign_leads (
      campaign_id,lead_id,qualified,quality_score,qualification_reason,source_area,source_query,source_term,
      first_seen_at,last_seen_at,last_run_id
    ) VALUES (?,?,?,?,?,?,?,?,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP,?)
    ON CONFLICT(campaign_id,lead_id) DO UPDATE SET
      qualified=excluded.qualified,
      quality_score=excluded.quality_score,
      qualification_reason=excluded.qualification_reason,
      source_area=excluded.source_area,
      source_query=excluded.source_query,
      source_term=excluded.source_term,
      last_seen_at=CURRENT_TIMESTAMP,
      last_run_id=excluded.last_run_id
    """

    signal_sql = """
    INSERT INTO lead_signals (
      campaign_id,lead_id,latest_sampled_review_at,latest_sampled_review_age_days,sampled_review_count,
      recent_sampled_reviews,sampled_review_avg,review_signal_checked_at,review_signal_note,
      website_present,phone_present,updated_at
    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,CURRENT_TIMESTAMP)
    ON CONFLICT(campaign_id,lead_id) DO UPDATE SET
      latest_sampled_review_at=excluded.latest_sampled_review_at,
      latest_sampled_review_age_days=excluded.latest_sampled_review_age_days,
      sampled_review_count=excluded.sampled_review_count,
      recent_sampled_reviews=excluded.recent_sampled_reviews,
      sampled_review_avg=excluded.sampled_review_avg,
      review_signal_checked_at=excluded.review_signal_checked_at,
      review_signal_note=excluded.review_signal_note,
      website_present=excluded.website_present,
      phone_present=excluded.phone_present,
      updated_at=CURRENT_TIMESTAMP
    """

    for index, row in enumerate(rows, 1):
        if not row.get("id"):
            continue
        batch = f"{campaign['id']}:{run_id}"
        query(lead_sql, [
            row["id"], row.get("name") or "Unnamed business", row.get("price_level") or "PRICE_LEVEL_UNSPECIFIED",
            row.get("rating"), row.get("user_rating_count") or 0, row.get("business_status"), row.get("phone"),
            row.get("website"), row.get("google_maps_url"), row.get("address"), row.get("latitude"), row.get("longitude"),
            row.get("primary_type"), row.get("types"), row.get("opening_hours"), campaign.get("name"), row.get("source_query"),
            campaign.get("vertical"), row.get("source_area"), batch, batch,
        ])
        query(membership_sql, [
            campaign["id"], row["id"], 1 if row.get("qualified") else 0, row.get("quality_score") or 0,
            row.get("qualification_reason") or "", row.get("source_area"), row.get("source_query"), row.get("source_term"), run_id,
        ])
        query(signal_sql, [
            campaign["id"], row["id"], row.get("latest_sampled_review_at"), row.get("latest_sampled_review_age_days"),
            row.get("sampled_review_count") or 0, row.get("recent_sampled_reviews") or 0, row.get("sampled_review_avg"),
            row.get("review_signal_checked_at"), row.get("review_signal_note"), 1 if row.get("website") else 0,
            1 if row.get("phone") else 0,
        ])
        if index % 25 == 0:
            print(f"Synced {index}/{len(rows)} campaign candidates")

    print(json.dumps({
        "campaign": campaign["id"],
        "run_id": run_id,
        "candidates_synced": len(rows),
        "qualified": summary.get("qualified", 0),
    }, indent=2))


if __name__ == "__main__":
    main()
