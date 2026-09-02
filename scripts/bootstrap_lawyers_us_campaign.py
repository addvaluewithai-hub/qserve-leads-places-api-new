#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path

from d1_helpers import apply_schema, canonical_domain, make_query_client, result_rows
from zip_manager import load_campaign, load_plan, sync_zip_plan


def read_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def main() -> None:
    parser = argparse.ArgumentParser(description="Bootstrap the validated historical first 1,000 lawyer domains into D1")
    parser.add_argument("--campaign", default="lawyers-us")
    parser.add_argument("--input-dir", required=True)
    args = parser.parse_args()

    input_dir = Path(args.input_dir)
    leads_path = input_dir / "lawyers_1000.csv"
    summary_path = input_dir / "summary.json"
    for path in (leads_path, summary_path):
        if not path.exists():
            raise SystemExit(f"Missing bootstrap file: {path}")

    rows = read_csv(leads_path)
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    campaign = load_campaign(args.campaign)
    plan = load_plan(campaign)

    query = make_query_client()
    apply_schema(query)
    sync_zip_plan(query, campaign, plan)

    run_id = "bootstrap-33604156200"
    now = datetime.now(timezone.utc).isoformat()
    query(
        """
        INSERT INTO campaign_runs (id,campaign_id,started_at,completed_at,discovered_count,qualified_count,summary_json,status)
        VALUES (?,?,?,?,?,?,?,?)
        ON CONFLICT(id) DO UPDATE SET completed_at=excluded.completed_at,
          discovered_count=excluded.discovered_count,summary_json=excluded.summary_json,status=excluded.status
        """,
        [run_id, campaign["id"], now, now, len(rows), 0, json.dumps(summary, separators=(",", ":")), "completed"],
    )

    written = 0
    reused = 0
    for index, row in enumerate(rows, 1):
        place_id = row.get("place_id")
        website = row.get("website")
        domain = canonical_domain(website or row.get("website_domain"))
        if not place_id or not domain or not website:
            continue

        existing = result_rows(query("SELECT lead_id FROM lead_domains WHERE website_domain=? LIMIT 1", [domain]))
        canonical_id = str(existing[0]["lead_id"]) if existing else str(place_id)
        if existing:
            reused += 1
        else:
            title = (row.get("website_title") or domain).strip()
            query(
                """
                INSERT INTO leads (
                  id,name,business_status,website,source_label,source_query,source_type,source_area,
                  status,notes,first_source_batch,latest_source_batch
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(id) DO UPDATE SET name=excluded.name,website=excluded.website,
                  source_label=excluded.source_label,source_query=excluded.source_query,
                  source_type=excluded.source_type,source_area=excluded.source_area,status=excluded.status,
                  notes=excluded.notes,latest_source_batch=excluded.latest_source_batch,last_seen_at=CURRENT_TIMESTAMP
                """,
                [place_id, title, "OPERATIONAL", website, campaign.get("name"), "lawyer", campaign.get("vertical"), row.get("source_market"), "Ready for Validation", "Historical first-1,000 seed. Website/title persisted from the independent open-web verification artifact; exact Google/Grounding rating-review values are not imported into the V2 production data model.", run_id, run_id],
            )
            query(
                """
                INSERT INTO lead_domains (lead_id,website_domain,verified,source,updated_at)
                VALUES (?,?,1,'historical_open_web_seed',CURRENT_TIMESTAMP)
                ON CONFLICT(lead_id) DO UPDATE SET website_domain=excluded.website_domain,
                  verified=1,source=excluded.source,updated_at=CURRENT_TIMESTAMP
                """,
                [place_id, domain],
            )

        query(
            """
            INSERT INTO campaign_leads (
              campaign_id,lead_id,qualified,quality_score,qualification_reason,source_area,source_query,source_term,
              status,first_seen_at,last_seen_at,last_run_id
            ) VALUES (?,?,?,?,?,?,?,?,?,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP,?)
            ON CONFLICT(campaign_id,lead_id) DO UPDATE SET qualified=0,
              qualification_reason=excluded.qualification_reason,source_area=excluded.source_area,
              source_query=excluded.source_query,status=excluded.status,last_seen_at=CURRENT_TIMESTAMP,
              last_run_id=excluded.last_run_id
            """,
            [campaign["id"], canonical_id, 0, 0, "historical_working_set_ready_for_validation", row.get("source_market"), "lawyer", "historical-first-1000", "Ready for Validation", run_id],
        )
        written += 1
        if index % 100 == 0:
            print(f"Bootstrapped {index}/{len(rows)} rows")

    print(json.dumps({
        "campaign": campaign["id"],
        "bootstrap_run_id": run_id,
        "source_rows": len(rows),
        "campaign_memberships_written": written,
        "existing_domains_reused": reused,
        "zip_plan_synced": True,
        "google_calls": 0
    }, indent=2))


if __name__ == "__main__":
    main()
