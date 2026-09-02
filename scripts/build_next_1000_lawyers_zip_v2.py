#!/usr/bin/env python3
from __future__ import annotations

"""
Production wrapper for build_next_1000_lawyers_zip.py.

It keeps the validated ZIP-search/crawl loop but hardens two production concerns:
1) business-domain identity / directory-social rejection;
2) batched D1 persistence per ZIP, with lead_domains written last as the
   completion marker so interrupted ZIPs can be retried safely.
"""

from datetime import datetime, timezone
from urllib.parse import urlparse

import tldextract

import build_next_1000_lawyers_zip as core
from d1_helpers import result_rows

TLD_EXTRACT = tldextract.TLDExtract(suffix_list_urls=None)

BLOCKED_BUSINESS_DOMAINS = {
    "google.com", "googleusercontent.com", "facebook.com", "instagram.com",
    "linkedin.com", "twitter.com", "x.com", "youtube.com", "tiktok.com",
    "yelp.com", "avvo.com", "justia.com", "findlaw.com", "lawyers.com",
    "martindale.com", "martindale-hubbell.com", "superlawyers.com", "lawinfo.com",
    "yellowpages.com", "mapquest.com", "bbb.org", "chamberofcommerce.com",
    "alignable.com", "linktr.ee", "bio.site", "beacons.ai", "business.site",
}

HOST_IDENTITY_BASES = {
    "wixsite.com", "wordpress.com", "weebly.com", "godaddysites.com",
    "square.site", "webflow.io", "mystrikingly.com", "site123.me",
}

_pending_by_zip: dict[str, list[dict]] = {}
_original_finish_zip = core.finish_zip
_original_quality_candidates = core.quality_candidates
_original_crawl_candidates = core.crawl_candidates


def _host(value: str | None) -> str | None:
    if not value:
        return None
    try:
        normalized = value if "://" in value else f"https://{value}"
        host = (urlparse(normalized).hostname or "").lower().strip(".")
        return host[4:] if host.startswith("www.") else (host or None)
    except Exception:
        return None


def business_domain(value: str | None) -> str | None:
    host = _host(value)
    if not host:
        return None
    parts = TLD_EXTRACT(host)
    base = f"{parts.domain}.{parts.suffix}".lower() if parts.domain and parts.suffix else host
    if base in HOST_IDENTITY_BASES and host != base:
        return host
    return base


def is_blocked_business_site(value: str | None) -> bool:
    domain = business_domain(value)
    if not domain:
        return True
    if domain in BLOCKED_BUSINESS_DOMAINS:
        return True
    return any(domain.endswith("." + blocked) for blocked in BLOCKED_BUSINESS_DOMAINS)


def global_seen(query) -> tuple[set[str], set[str], set[str]]:
    """Only lead_domains marks a completed canonical discovery row for this pipeline."""
    ids = {
        str(r["lead_id"])
        for r in result_rows(query("SELECT lead_id FROM lead_domains"))
        if r.get("lead_id")
    }
    domains: set[str] = set()
    for row in result_rows(query("SELECT website_domain FROM lead_domains")):
        domain = business_domain(row.get("website_domain"))
        if domain:
            domains.add(domain)

    suppressed: set[str] = set()
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
        domain = business_domain(row.get("website_domain"))
        if domain:
            suppressed.add(domain)
            domains.add(domain)
    return ids, domains, suppressed


def quality_candidates(payload: dict, campaign: dict, target_zip: str):
    rows, counts = _original_quality_candidates(payload, campaign, target_zip)
    filtered = [
        row for row in rows
        if row.get("seed_business_domain")
        and not is_blocked_business_site(row.get("website_seed"))
    ]
    return filtered, counts


def crawl_candidates(candidates: list[dict], zip_row: dict, workers: int) -> list[dict]:
    rows = _original_crawl_candidates(candidates, zip_row, workers)
    for row in rows:
        row["final_business_domain"] = business_domain(row.get("final_url"))
        if row.get("crawl_status") == "completed" and is_blocked_business_site(row.get("final_url")):
            row["crawl_status"] = "rejected_non_business_domain"
            row["error"] = "Crawler landed on directory/social/shared non-business host"
    return rows


def _multi_insert(query, prefix: str, rows: list[tuple], columns_per_row: int, suffix: str = "", chunk_size: int = 50):
    if not rows:
        return
    placeholder = "(" + ",".join("?" for _ in range(columns_per_row)) + ")"
    for start in range(0, len(rows), chunk_size):
        chunk = rows[start:start + chunk_size]
        sql = prefix + ",".join(placeholder for _ in chunk)
        if suffix:
            sql += "\n" + suffix
        params = [value for row in chunk for value in row]
        query(sql, params)


def buffer_open_web_lead(query, *, campaign: dict, run_id: str, zip_row: dict, crawled: dict) -> dict:
    place_id = str(crawled["place_id"])
    final_url = str(crawled["final_url"])
    domain = business_domain(final_url)
    title = (crawled.get("homepage_title") or domain or "Law firm").strip()
    now = datetime.now(timezone.utc).isoformat()
    item = {
        "place_id": place_id,
        "website": final_url,
        "website_domain": domain,
        "website_title": title,
        "source_zip": str(zip_row["zip_code"]),
        "source_city": zip_row.get("city"),
        "source_state": zip_row.get("state_code"),
        "homepage_status_code": crawled.get("homepage_status_code"),
        "internal_links_found": len(crawled.get("links") or []),
        "campaign_status": "Ready for Validation",
        "qualified": False,
        "_campaign_id": campaign["id"],
        "_campaign_name": campaign.get("name") or campaign["id"],
        "_vertical": campaign.get("vertical") or "legal",
        "_run_id": run_id,
        "_crawled_at": now,
        "_links": list(crawled.get("links") or []),
    }
    _pending_by_zip.setdefault(str(zip_row["zip_code"]), []).append(item)
    return {key: value for key, value in item.items() if not key.startswith("_")}


def _flush_zip(query, zip_code: str) -> None:
    rows = _pending_by_zip.get(zip_code) or []
    if not rows:
        return

    lead_rows = []
    membership_rows = []
    screening_rows = []
    link_rows = []
    domain_rows = []

    for row in rows:
        batch = f"{row['_campaign_id']}:{row['_run_id']}"
        notes = (
            "Passed transient Google Places screening (rating >= 4.0 and reviews >= 20). "
            "Google non-ID screening fields and websiteUri were not persisted. "
            "Website/domain/title/links were re-observed from the public site by Crawl4AI."
        )
        lead_rows.append((
            row["place_id"], row["website_title"], "OPERATIONAL", row["website"],
            row["_campaign_name"], "lawyer", row["_vertical"], row["source_zip"],
            "Ready for Validation", notes, batch, batch,
        ))
        membership_rows.append((
            row["_campaign_id"], row["place_id"], 0, 0,
            "working_set_ready_for_validation", row["source_zip"], "lawyer",
            f"zip:{row['source_zip']}", "Ready for Validation", row["_run_id"],
        ))
        screening_rows.append((
            row["_campaign_id"], row["place_id"],
            "google_places_text_search_enterprise_transient", row["source_zip"],
            1, row["_crawled_at"],
            "Google non-ID fields used transiently for screening/crawler seeding; only Place ID persisted from Google response.",
        ))
        for link in row["_links"]:
            if not link.get("url"):
                continue
            link_rows.append((
                row["_campaign_id"], row["place_id"], row["website"], row["website"],
                link.get("url"), link.get("anchor_text") or "", row["_crawled_at"],
            ))
        domain_rows.append((row["place_id"], row["website_domain"], 1, "crawl4ai_open_web"))

    _multi_insert(
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
          name=excluded.name,
          business_status=excluded.business_status,
          website=excluded.website,
          source_label=excluded.source_label,
          source_query=excluded.source_query,
          source_type=excluded.source_type,
          source_area=excluded.source_area,
          status=excluded.status,
          notes=excluded.notes,
          latest_source_batch=excluded.latest_source_batch,
          last_seen_at=CURRENT_TIMESTAMP
        """,
        chunk_size=25,
    )

    _multi_insert(
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
        chunk_size=25,
    )

    _multi_insert(
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
        chunk_size=25,
    )

    _multi_insert(
        query,
        """
        INSERT INTO homepage_link_evidence (
          campaign_id,lead_id,homepage,final_url,url,anchor_text,crawled_at
        ) VALUES
        """,
        link_rows, 7,
        """
        ON CONFLICT(campaign_id,lead_id,url) DO UPDATE SET
          homepage=excluded.homepage,
          final_url=excluded.final_url,
          anchor_text=excluded.anchor_text,
          crawled_at=excluded.crawled_at
        """,
        chunk_size=75,
    )

    # Completion marker LAST. global_seen() only trusts rows that made it here.
    _multi_insert(
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
        chunk_size=25,
    )

    _pending_by_zip.pop(zip_code, None)


def finish_zip(query, *, campaign_id: str, run_id: str, zip_row: dict, status: str, metrics: dict, note: str = "") -> None:
    zip_code = str(zip_row["zip_code"])
    _flush_zip(query, zip_code)
    _original_finish_zip(
        query,
        campaign_id=campaign_id,
        run_id=run_id,
        zip_row=zip_row,
        status=status,
        metrics=metrics,
        note=note,
    )


core.business_domain = business_domain
core.global_seen = global_seen
core.quality_candidates = quality_candidates
core.crawl_candidates = crawl_candidates
core.persist_open_web_lead = buffer_open_web_lead
core.finish_zip = finish_zip


if __name__ == "__main__":
    core.main()
