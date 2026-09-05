#!/usr/bin/env python3
from __future__ import annotations

"""Promote successfully crawled V8 leads from Crawl Evidence to Validation.

This importer is intentionally write-first and does not pre-read D1 rows. The input
artifact already carries the V8 Place ID + official domain identity, and Crawl4AI
must successfully land on that domain (or a subdomain of it) before promotion.
"""

import argparse
import json
from pathlib import Path
from urllib.parse import urlparse

from d1_helpers import make_query_client


def host(value: str | None) -> str:
    if not value:
        return ""
    raw = value.strip()
    if not raw:
        return ""
    if "://" not in raw:
        raw = "https://" + raw
    h = (urlparse(raw).hostname or "").lower().strip(".")
    return h[4:] if h.startswith("www.") else h


def matches_expected_domain(final_url: str | None, expected_domain: str | None) -> bool:
    expected = host(expected_domain)
    actual = host(final_url)
    if not expected or not actual:
        return False
    return actual == expected or actual.endswith("." + expected)


def main() -> None:
    ap = argparse.ArgumentParser(description="Import Crawl4AI homepage evidence into D1 and promote leads")
    ap.add_argument("--campaign", default="lawyers-us")
    ap.add_argument("--input", required=True, help="homepage_links.json from Crawl4AI artifact")
    ap.add_argument("--report", default=None)
    args = ap.parse_args()

    payload = json.loads(Path(args.input).read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise SystemExit("Expected homepage_links.json to contain a JSON list")

    query = make_query_client()
    promoted = 0
    crawl_failed = 0
    domain_mismatch = 0
    links_written = 0
    errors: list[dict] = []

    for item in payload:
        place_id = str(item.get("place_id") or "").strip()
        expected_domain = str(item.get("website_domain") or "").strip().lower().strip(".")
        crawl_status = str(item.get("crawl_status") or "")
        final_url = str(item.get("final_url") or item.get("homepage") or "").strip()
        crawled_at = str(item.get("fetched_at") or "").strip()

        if crawl_status != "completed":
            crawl_failed += 1
            continue
        if not place_id or not expected_domain or not matches_expected_domain(final_url, expected_domain):
            domain_mismatch += 1
            errors.append({
                "place_id": place_id,
                "expected_domain": expected_domain,
                "final_url": final_url,
                "reason": "final_domain_mismatch_or_missing_identity",
            })
            continue

        try:
            query(
                "DELETE FROM homepage_link_evidence WHERE campaign_id=? AND lead_id=?",
                [args.campaign, place_id],
            )
            for link in item.get("links") or []:
                url = str(link.get("url") or "").strip()
                if not url:
                    continue
                query(
                    """INSERT OR REPLACE INTO homepage_link_evidence
                       (campaign_id,lead_id,homepage,final_url,url,anchor_text,crawled_at)
                       VALUES (?,?,?,?,?,?,?)""",
                    [
                        args.campaign,
                        place_id,
                        str(item.get("homepage") or final_url),
                        final_url,
                        url,
                        str(link.get("anchor_text") or "")[:140],
                        crawled_at,
                    ],
                )
                links_written += 1

            query(
                """UPDATE lead_domains
                   SET verified=1,source='crawl4ai_homepage_confirmed',updated_at=CURRENT_TIMESTAMP
                   WHERE lead_id=? AND website_domain=?""",
                [place_id, expected_domain],
            )
            query(
                """UPDATE leads
                   SET website=?,status='Ready for Validation',last_seen_at=CURRENT_TIMESTAMP
                   WHERE id=?""",
                [final_url, place_id],
            )
            query(
                """UPDATE campaign_leads
                   SET status='Ready for Validation',
                       qualification_reason='crawl4ai_homepage_evidence_ready',
                       last_seen_at=CURRENT_TIMESTAMP
                   WHERE campaign_id=? AND lead_id=?""",
                [args.campaign, place_id],
            )
            promoted += 1
        except Exception as exc:
            errors.append({
                "place_id": place_id,
                "expected_domain": expected_domain,
                "final_url": final_url,
                "reason": f"{type(exc).__name__}: {exc}",
            })

    report = {
        "campaign": args.campaign,
        "input_items": len(payload),
        "promoted_ready_for_validation": promoted,
        "crawl_not_completed": crawl_failed,
        "domain_mismatch": domain_mismatch,
        "homepage_links_written": links_written,
        "errors": errors[:200],
    }
    text = json.dumps(report, ensure_ascii=False, indent=2)
    print(text)
    if args.report:
        path = Path(args.report)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
