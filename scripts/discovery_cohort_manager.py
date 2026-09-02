#!/usr/bin/env python3
from __future__ import annotations

import uuid
from dataclasses import dataclass

from d1_helpers import result_rows


@dataclass
class CohortState:
    cohort_id: str
    campaign_id: str
    sequence_no: int
    target_domains: int
    collected_domains: int
    remaining_domains: int
    status: str


def ensure_cohort_schema(query) -> None:
    query(
        """
        CREATE TABLE IF NOT EXISTS discovery_cohorts (
          id TEXT PRIMARY KEY,
          campaign_id TEXT NOT NULL,
          sequence_no INTEGER NOT NULL,
          target_domains INTEGER NOT NULL DEFAULT 1000,
          status TEXT NOT NULL DEFAULT 'active',
          started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
          completed_at TEXT,
          notes TEXT NOT NULL DEFAULT '',
          updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
          UNIQUE(campaign_id, sequence_no)
        )
        """
    )
    query(
        """
        CREATE TABLE IF NOT EXISTS discovery_cohort_leads (
          cohort_id TEXT NOT NULL,
          lead_id TEXT NOT NULL,
          website_domain TEXT NOT NULL,
          source_zip TEXT,
          added_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
          PRIMARY KEY (cohort_id, lead_id),
          UNIQUE(cohort_id, website_domain)
        )
        """
    )
    query("CREATE INDEX IF NOT EXISTS idx_discovery_cohorts_active ON discovery_cohorts(campaign_id,status,sequence_no)")
    query("CREATE INDEX IF NOT EXISTS idx_discovery_cohort_leads_cohort ON discovery_cohort_leads(cohort_id,added_at)")


def _cohort_count(query, cohort_id: str) -> int:
    rows = result_rows(query("SELECT COUNT(*) AS n FROM discovery_cohort_leads WHERE cohort_id=?", [cohort_id]))
    return int((rows[0] if rows else {}).get("n") or 0)


def adopt_unassigned_completed_discoveries(query, campaign_id: str, cohort_id: str) -> int:
    """Adopt crawler-completed campaign discoveries not yet assigned to any cohort.

    This is what makes cancel/retry resumable. We only trust lead_domains, the
    pipeline completion marker, so half-written campaign rows are not counted.
    """
    before = _cohort_count(query, cohort_id)
    query(
        """
        INSERT OR IGNORE INTO discovery_cohort_leads (cohort_id,lead_id,website_domain,source_zip)
        SELECT ?, cl.lead_id, ld.website_domain, cl.source_area
        FROM campaign_leads cl
        JOIN lead_domains ld ON ld.lead_id=cl.lead_id
        WHERE cl.campaign_id=?
          AND cl.qualification_reason='working_set_ready_for_validation'
          AND NOT EXISTS (
            SELECT 1 FROM discovery_cohort_leads dcl WHERE dcl.lead_id=cl.lead_id
          )
        """,
        [cohort_id, campaign_id],
    )
    return max(0, _cohort_count(query, cohort_id) - before)


def get_or_create_active_cohort(query, campaign_id: str, target_domains: int = 1000) -> CohortState:
    ensure_cohort_schema(query)
    rows = result_rows(query(
        """
        SELECT id,campaign_id,sequence_no,target_domains,status
        FROM discovery_cohorts
        WHERE campaign_id=? AND status IN ('active','partial')
        ORDER BY sequence_no DESC LIMIT 1
        """,
        [campaign_id],
    ))

    if rows:
        row = rows[0]
        cohort_id = str(row["id"])
        sequence_no = int(row["sequence_no"])
        cohort_target = int(row.get("target_domains") or target_domains)
    else:
        max_rows = result_rows(query("SELECT COALESCE(MAX(sequence_no),0) AS n FROM discovery_cohorts WHERE campaign_id=?", [campaign_id]))
        sequence_no = int((max_rows[0] if max_rows else {}).get("n") or 0) + 1
        cohort_id = f"{campaign_id}:cohort:{sequence_no}:{uuid.uuid4().hex[:8]}"
        cohort_target = int(target_domains)
        query(
            """
            INSERT INTO discovery_cohorts (id,campaign_id,sequence_no,target_domains,status,notes)
            VALUES (?,?,?,?, 'active', ?)
            """,
            [cohort_id, campaign_id, sequence_no, cohort_target, "Resumable net-new discovery cohort."],
        )

    adopt_unassigned_completed_discoveries(query, campaign_id, cohort_id)
    collected = _cohort_count(query, cohort_id)
    remaining = max(0, cohort_target - collected)
    status = "completed" if remaining == 0 else ("partial" if collected else "active")
    query(
        """
        UPDATE discovery_cohorts
        SET status=?, completed_at=CASE WHEN ?='completed' THEN COALESCE(completed_at,CURRENT_TIMESTAMP) ELSE NULL END,
            updated_at=CURRENT_TIMESTAMP
        WHERE id=?
        """,
        [status, status, cohort_id],
    )
    return CohortState(cohort_id, campaign_id, sequence_no, cohort_target, collected, remaining, status)


def add_cohort_leads(query, cohort_id: str, rows: list[tuple[str,str,str | None]]) -> int:
    if not rows:
        return 0
    before = _cohort_count(query, cohort_id)
    # One INSERT SELECT/VALUES per small chunk keeps bound parameters below D1's 100 limit.
    per_row = 4
    chunk_size = 20
    for start in range(0, len(rows), chunk_size):
        chunk = rows[start:start + chunk_size]
        placeholders = ",".join(["(?,?,?,?)"] * len(chunk))
        params = []
        for lead_id, domain, source_zip in chunk:
            params.extend([cohort_id, lead_id, domain, source_zip])
        if len(params) > 100:
            raise RuntimeError("D1 cohort batch exceeded 100 bound parameters")
        query(
            f"INSERT OR IGNORE INTO discovery_cohort_leads (cohort_id,lead_id,website_domain,source_zip) VALUES {placeholders}",
            params,
        )
    return max(0, _cohort_count(query, cohort_id) - before)


def refresh_cohort(query, cohort_id: str) -> CohortState:
    rows = result_rows(query(
        "SELECT id,campaign_id,sequence_no,target_domains,status FROM discovery_cohorts WHERE id=? LIMIT 1",
        [cohort_id],
    ))
    if not rows:
        raise RuntimeError(f"Discovery cohort not found: {cohort_id}")
    row = rows[0]
    collected = _cohort_count(query, cohort_id)
    target = int(row.get("target_domains") or 1000)
    remaining = max(0, target - collected)
    status = "completed" if remaining == 0 else ("partial" if collected else "active")
    query(
        """
        UPDATE discovery_cohorts
        SET status=?, completed_at=CASE WHEN ?='completed' THEN COALESCE(completed_at,CURRENT_TIMESTAMP) ELSE NULL END,
            updated_at=CURRENT_TIMESTAMP
        WHERE id=?
        """,
        [status, status, cohort_id],
    )
    return CohortState(
        str(row["id"]), str(row["campaign_id"]), int(row["sequence_no"]),
        target, collected, remaining, status,
    )
