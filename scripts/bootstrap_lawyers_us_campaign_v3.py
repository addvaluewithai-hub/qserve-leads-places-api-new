#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path

import zip_manager
zip_manager.ZIP_UPSERT_BATCH = 10

from d1_helpers import apply_schema, canonical_domain, make_query_client, result_rows
from zip_manager import load_campaign, load_plan, sync_zip_plan

D1_MAX_BOUND_PARAMS = 100


def read_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def multi_insert(query, prefix: str, rows: list[tuple], cols: int, suffix: str = "") -> None:
    if not rows:
        return
    chunk_size = max(1, D1_MAX_BOUND_PARAMS // cols)
    placeholder = "(" + ",".join("?" for _ in range(cols)) + ")"
    for start in range(0, len(rows), chunk_size):
        chunk = rows[start:start + chunk_size]
        params = [value for row in chunk for value in row]
        query(prefix + ",".join(placeholder for _ in chunk) + ("\n" + suffix if suffix else ""), params)


def main() -> None:
    parser = argparse.ArgumentParser(description="Batch-bootstrap the validated first 1,000 lawyer domains into D1")
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
    zip_sync = sync_zip_plan(query, campaign, plan)

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

    domain_map: dict[str, str] = {}
    for existing in result_rows(query("SELECT lead_id,website_domain FROM lead_domains")):
        domain = canonical_domain(existing.get("website_domain"))
        if domain and existing.get("lead_id"):
            domain_map[domain] = str(existing["lead_id"])

    lead_rows: list[tuple] = []
    domain_rows: list[tuple] = []
    membership_rows: list[tuple] = []
    reused = 0
    source_valid = 0

    for row in rows:
        place_id = row.get("place_id")
        website = row.get("website")
        domain = canonical_domain(website or row.get("website_domain"))
        if not place_id or not domain or not website:
            continue
        source_valid += 1
        canonical_id = domain_map.get(domain)
        if canonical_id:
            reused += 1
        else:
            canonical_id = str(place_id)
            domain_map[domain] = canonical_id
            title = (row.get("website_title") or domain).strip()
            lead_rows.append((
                canonical_id, title, "OPERATIONAL", website, campaign.get("name") or campaign["id"],
                "lawyer", campaign.get("vertical") or "legal", row.get("source_market"),
                "Ready for Validation",
                "Historical first-1,000 seed. Website/title persisted from independent open-web verification; exact historical Google/Grounding rating-review values are not imported into the V2/V3 production model.",
                run_id, run_id,
            ))
            domain_rows.append((canonical_id, domain, 1, "historical_open_web_seed"))

        membership_rows.append((
            campaign["id"], canonical_id, 0, 0, "historical_working_set_ready_for_validation",
            row.get("source_market"), "lawyer", "historical-first-1000",
            "Ready for Validation", run_id,
        ))

    multi_insert(
        query,
        """INSERT INTO leads (
          id,name,business_status,website,source_label,source_query,source_type,source_area,
          status,notes,first_source_batch,latest_source_batch
        ) VALUES """,
        lead_rows, 12,
        """ON CONFLICT(id) DO UPDATE SET
          name=excluded.name,website=excluded.website,source_label=excluded.source_label,
          source_query=excluded.source_query,source_type=excluded.source_type,source_area=excluded.source_area,
          status=excluded.status,notes=excluded.notes,latest_source_batch=excluded.latest_source_batch,
          last_seen_at=CURRENT_TIMESTAMP""",
    )

    # Write canonical domains after canonical business rows.
    multi_insert(
        query,
        "INSERT INTO lead_domains (lead_id,website_domain,verified,source) VALUES ",
        domain_rows, 4,
        """ON CONFLICT(lead_id) DO UPDATE SET website_domain=excluded.website_domain,
          verified=excluded.verified,source=excluded.source,updated_at=CURRENT_TIMESTAMP""",
    )

    multi_insert(
        query,
        """INSERT INTO campaign_leads (
          campaign_id,lead_id,qualified,quality_score,qualification_reason,
          source_area,source_query,source_term,status,last_run_id
        ) VALUES """,
        membership_rows, 10,
        """ON CONFLICT(campaign_id,lead_id) DO UPDATE SET qualified=0,
          qualification_reason=excluded.qualification_reason,source_area=excluded.source_area,
          source_query=excluded.source_query,source_term=excluded.source_term,status=excluded.status,
          last_seen_at=CURRENT_TIMESTAMP,last_run_id=excluded.last_run_id""",
    )

    print(json.dumps({
        "campaign": campaign["id"],
        "bootstrap_run_id": run_id,
        "source_rows": len(rows),
        "valid_rows": source_valid,
        "new_canonical_leads_written": len(lead_rows),
        "campaign_memberships_written": len(membership_rows),
        "existing_domains_reused": reused,
        "zip_sync": zip_sync,
        "google_calls": 0,
        "d1_max_bound_params_respected": True,
    }, indent=2))


if __name__ == "__main__":
    main()
