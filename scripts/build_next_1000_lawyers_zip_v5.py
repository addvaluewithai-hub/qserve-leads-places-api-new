#!/usr/bin/env python3
from __future__ import annotations

"""ZIP V5: explicit market order + resumable 1,000-domain discovery cohorts.

A GitHub run is execution machinery; a discovery cohort is the business unit.
If a run is cancelled or hits the request ceiling, the next invocation adopts
all crawler-completed unassigned discoveries and requests only the remaining
number required to finish the active cohort.
"""

import argparse
import json
import sys

import build_next_1000_lawyers_zip_v4 as v4
from d1_helpers import apply_schema, make_query_client
from discovery_cohort_manager import (
    add_cohort_leads,
    get_or_create_active_cohort,
    refresh_cohort,
)

hardened = v4.v3.hardened
_original_flush_zip = hardened._flush_zip
_ACTIVE_COHORT_ID: str | None = None


def _flush_zip_with_cohort(query, zip_code: str) -> None:
    pending = list(hardened._pending_by_zip.get(str(zip_code)) or [])
    _original_flush_zip(query, str(zip_code))
    if not pending or not _ACTIVE_COHORT_ID:
        return
    completed_rows = []
    for row in pending:
        lead_id = row.get("place_id")
        domain = row.get("website_domain")
        if lead_id and domain:
            completed_rows.append((str(lead_id), str(domain), row.get("source_zip")))
    add_cohort_leads(query, _ACTIVE_COHORT_ID, completed_rows)


def _replace_target_arg(remaining: int) -> None:
    args = list(sys.argv)
    if "--target" in args:
        idx = args.index("--target")
        if idx + 1 >= len(args):
            raise SystemExit("--target requires a value")
        args[idx + 1] = str(remaining)
    else:
        args.extend(["--target", str(remaining)])
    sys.argv[:] = args


def main() -> None:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--campaign", default="lawyers-us")
    parser.add_argument("--target", type=int, default=1000)
    known, _ = parser.parse_known_args()

    query = make_query_client()
    apply_schema(query)
    cohort = get_or_create_active_cohort(query, known.campaign, int(known.target))

    print(json.dumps({
        "discovery_cohort": cohort.cohort_id,
        "sequence_no": cohort.sequence_no,
        "cohort_target_domains": cohort.target_domains,
        "already_collected_domains": cohort.collected_domains,
        "remaining_domains_for_this_invocation": cohort.remaining_domains,
        "cohort_status": cohort.status,
    }, indent=2))

    if cohort.remaining_domains <= 0:
        print("Active discovery cohort is already complete; no Google requests are required.")
        return

    global _ACTIVE_COHORT_ID
    _ACTIVE_COHORT_ID = cohort.cohort_id
    hardened._flush_zip = _flush_zip_with_cohort
    _replace_target_arg(cohort.remaining_domains)

    exit_error: BaseException | None = None
    try:
        v4.v3.hardened.core.main()
    except BaseException as exc:
        exit_error = exc
    finally:
        final_state = refresh_cohort(query, cohort.cohort_id)
        print(json.dumps({
            "discovery_cohort": final_state.cohort_id,
            "sequence_no": final_state.sequence_no,
            "cohort_target_domains": final_state.target_domains,
            "cohort_collected_domains": final_state.collected_domains,
            "cohort_remaining_domains": final_state.remaining_domains,
            "cohort_status": final_state.status,
        }, indent=2))

    if exit_error is not None:
        raise exit_error


if __name__ == "__main__":
    main()
