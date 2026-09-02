#!/usr/bin/env python3
from __future__ import annotations

import argparse
from datetime import datetime, timezone

from d1_helpers import apply_schema, canonical_domain, make_query_client, result_rows

ALLOWED_STATUSES = {"Contacted", "Replied", "Interested", "Not Interested", "Do Not Contact", "Bounced", "Re-engage Later"}


def resolve_lead(query, lead_id: str | None, domain: str | None) -> tuple[str, str]:
    if lead_id:
        rows = result_rows(query("SELECT l.id,ld.website_domain FROM leads l LEFT JOIN lead_domains ld ON ld.lead_id=l.id WHERE l.id=? LIMIT 1", [lead_id]))
        if not rows or not rows[0].get("website_domain"):
            raise SystemExit("Lead ID not found or has no canonical domain")
        return str(rows[0]["id"]), str(rows[0]["website_domain"]).lower()
    normalized = canonical_domain(domain)
    if not normalized:
        raise SystemExit("Valid --domain or --lead-id is required")
    rows = result_rows(query("SELECT lead_id,website_domain FROM lead_domains WHERE website_domain=? LIMIT 1", [normalized]))
    if not rows:
        raise SystemExit(f"Domain not found in canonical lead registry: {normalized}")
    return str(rows[0]["lead_id"]), str(rows[0]["website_domain"]).lower()


def main() -> None:
    parser = argparse.ArgumentParser(description="Globally suppress a business after outreach/contact")
    parser.add_argument("--lead-id", default=None)
    parser.add_argument("--domain", default=None)
    parser.add_argument("--campaign", default=None)
    parser.add_argument("--email", default=None)
    parser.add_argument("--status", default="Contacted", choices=sorted(ALLOWED_STATUSES))
    parser.add_argument("--reason", default="contacted_once_global_block")
    parser.add_argument("--reengage-after", default=None)
    parser.add_argument("--unsuppress", action="store_true")
    args = parser.parse_args()
    if not args.lead_id and not args.domain:
        raise SystemExit("Provide --lead-id or --domain")

    query = make_query_client(); apply_schema(query)
    lead_id, domain = resolve_lead(query, args.lead_id, args.domain)
    now = datetime.now(timezone.utc).isoformat()
    suppressed = 0 if args.unsuppress else 1
    query(
        """
        INSERT INTO outreach_suppression (
          lead_id,website_domain,suppressed,contact_status,first_contacted_at,last_contacted_at,
          campaign_id,contact_email,suppression_reason,reengage_after,updated_at
        ) VALUES (?,?,?,?,?,?,?,?,?,?,CURRENT_TIMESTAMP)
        ON CONFLICT(lead_id) DO UPDATE SET
          website_domain=excluded.website_domain, suppressed=excluded.suppressed,
          contact_status=excluded.contact_status,
          first_contacted_at=COALESCE(outreach_suppression.first_contacted_at, excluded.first_contacted_at),
          last_contacted_at=excluded.last_contacted_at, campaign_id=excluded.campaign_id,
          contact_email=excluded.contact_email, suppression_reason=excluded.suppression_reason,
          reengage_after=excluded.reengage_after, updated_at=CURRENT_TIMESTAMP
        """,
        [lead_id, domain, suppressed, args.status, now if not args.unsuppress else None, now if not args.unsuppress else None, args.campaign, args.email, args.reason, args.reengage_after],
    )
    print({"lead_id": lead_id, "website_domain": domain, "suppressed": bool(suppressed), "status": args.status, "reengage_after": args.reengage_after})


if __name__ == "__main__":
    main()
