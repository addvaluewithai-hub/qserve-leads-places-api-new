#!/usr/bin/env python3
from __future__ import annotations

import json
from datetime import datetime, timezone

from d1_helpers import apply_schema, make_query_client, result_rows

CAMPAIGN_ID = "lawyers-us"
SKU = "places_text_search_enterprise"


def scalar(query, sql: str, params=None, key: str = "n") -> int:
    rows = result_rows(query(sql, params or []))
    return int((rows[0] if rows else {}).get(key) or 0)


def main() -> None:
    query = make_query_client()
    apply_schema(query)
    month = datetime.now(timezone.utc).strftime("%Y-%m")

    states = result_rows(query(
        """
        SELECT state_code,
               COUNT(*) AS materialized_zips,
               SUM(CASE WHEN status='queued' THEN 1 ELSE 0 END) AS queued,
               SUM(CASE WHEN status='in_progress' THEN 1 ELSE 0 END) AS in_progress,
               SUM(CASE WHEN status='partial' THEN 1 ELSE 0 END) AS partial,
               SUM(CASE WHEN status='covered' THEN 1 ELSE 0 END) AS covered,
               SUM(CASE WHEN status='saturated' THEN 1 ELSE 0 END) AS saturated,
               SUM(CASE WHEN status='failed' THEN 1 ELSE 0 END) AS failed,
               COALESCE(SUM(search_count),0) AS searches,
               COALESCE(SUM(page_count),0) AS pages,
               COALESCE(SUM(raw_places),0) AS raw_places,
               COALESCE(SUM(exact_zip_places),0) AS exact_zip_places,
               COALESCE(SUM(quality_passes),0) AS quality_passes,
               COALESCE(SUM(net_new_domains),0) AS net_new_domains
        FROM zip_coverage
        WHERE campaign_id=?
        GROUP BY state_code
        ORDER BY net_new_domains DESC, state_code
        """,
        [CAMPAIGN_ID],
    ))

    recent_zips = result_rows(query(
        """
        SELECT zip_code,city,state_code,status,search_count,page_count,raw_places,
               exact_zip_places,quality_passes,net_new_domains,last_searched_at,last_run_id
        FROM zip_coverage
        WHERE campaign_id=? AND last_searched_at IS NOT NULL
        ORDER BY last_searched_at DESC
        LIMIT 25
        """,
        [CAMPAIGN_ID],
    ))

    recent_runs = result_rows(query(
        """
        SELECT id,status,started_at,completed_at,discovered_count,qualified_count
        FROM campaign_runs WHERE campaign_id=?
        ORDER BY started_at DESC LIMIT 10
        """,
        [CAMPAIGN_ID],
    ))

    report = {
        "campaign": CAMPAIGN_ID,
        "canonical_leads": scalar(query, "SELECT COUNT(*) AS n FROM leads"),
        "canonical_domains": scalar(query, "SELECT COUNT(*) AS n FROM lead_domains"),
        "campaign_memberships": scalar(query, "SELECT COUNT(*) AS n FROM campaign_leads WHERE campaign_id=?", [CAMPAIGN_ID]),
        "ready_for_validation": scalar(query, "SELECT COUNT(*) AS n FROM campaign_leads WHERE campaign_id=? AND status='Ready for Validation'", [CAMPAIGN_ID]),
        "globally_suppressed": scalar(query, "SELECT COUNT(*) AS n FROM outreach_suppression WHERE suppressed=1"),
        "enterprise_requests_repo_ledger_this_month": scalar(
            query,
            "SELECT COALESCE(SUM(request_count),0) AS n FROM api_usage_ledger WHERE campaign_id=? AND sku=? AND usage_month=?",
            [CAMPAIGN_ID, SKU, month],
        ),
        "states": states,
        "recent_zips": recent_zips,
        "recent_campaign_runs": recent_runs,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
