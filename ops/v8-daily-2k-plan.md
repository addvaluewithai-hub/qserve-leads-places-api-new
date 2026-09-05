# V8 Daily 2K Discovery Plan

Status captured 2026-09-05.

## Batch 1 checkpoint
- Batch ID: `lawyers-us:v8-batch-01-of-09`
- Target: 2,000 total domains for Batch 1 (including adopted V7 discoveries).
- Result from the completed artifact: **2,000 / 2,000 collected; remaining 0; status completed**.
- V8 added 1,133 domains during its production run; the rest were adopted from the earlier V7 Batch-1 work.
- Stop reason: `target_reached`.
- Tracked Google usage at completion: Aggregate 512, Place Details Pro 2,079, Grounding Lite 3,170, Place Details Enterprise 0.

## Do not run another batch on 2026-09-05
No Batch 2 trigger should be created today. Ignore validator workflows and do not touch `main`.

## D1 incident
A later same-Batch-1 status/resume attempt failed before discovery because Cloudflare D1 returned error 7500: the account exceeded the **free-tier daily row-read limit**. Cloudflare's error says to wait until midnight UTC for the daily reset.

Root cause was row-read amplification in the V8 hot loop: repeated `batch_state()` / `COUNT(*)` calls as the batch grew, plus `write_checkpoint()` recomputing batch state and aggregate tile stats frequently.

## D1 row-read fix LANDED 2026-09-05
The production-safe low-read launcher is now:

`scripts/build_lawyers_v8_aggregate_probridge_lean.py`

It keeps the authoritative batch count in memory during a discovery process, increments it only after a durable `persist_resolved()` success, replaces hot-loop checkpoints with file-only checkpoints, and performs one final D1 reconciliation instead of repeatedly counting the growing batch and aggregating all tiles.

`.github/workflows/places-v8-aggregate-batch1.yml` now compiles and uses the lean runner. The lean runner compiled successfully in the Batch-1 Crawl4AI workflow before the crawl began.

Correctness-preserving indexed identity checks remain in place; the removed reads are the repeated full/count/aggregate scans that caused the large amplification.

## Crawl4AI handoff for Batch 1
A dedicated workflow now prepares the completed Batch-1 V8 domains for validators:

`.github/workflows/crawl-v8-batch1-evidence.yml`

It downloads the completed V8 Batch-1 discovery artifact, converts `accepted-this-run.jsonl` into the Crawl4AI working-set format, then runs homepage-only Crawl4AI over all V8-accepted domains. It does not run Google discovery and does not start Batch 2.

Successful crawl evidence is handed to D1 by:

`.github/workflows/import-v8-batch1-crawl-evidence.yml`

using:

`scripts/import_crawl4ai_evidence_to_d1.py`

The importer only promotes a lead when Crawl4AI completed successfully and the final host matches the expected official domain (or its subdomain). It persists homepage-link evidence, marks the domain Crawl4AI-confirmed, and changes both lead/campaign status to `Ready for Validation`. Failed crawls or domain mismatches are not promoted.

Because D1's daily row-read quota is already exhausted on 2026-09-05, the D1 handoff is intentionally deferred until after the midnight-UTC reset rather than repeatedly hitting the blocked quota.

## Daily execution rule starting 2026-09-06
1. Confirm no discovery workflow is already active. Ignore validators.
2. Confirm D1 daily quota is available; if unavailable, start nothing and report the block.
3. Confirm Google zero-paid guards are safe. If remaining free quota cannot be safely established or a guard is exhausted, start nothing.
4. Future V8 discovery must use `scripts/build_lawyers_v8_aggregate_probridge_lean.py` (or an equivalent low-read implementation); do not run the old hot-loop runner directly.
5. If the current numbered 2K batch is partial, resume that exact batch only.
6. If it is complete and campaign expansion is below +18,000 net-new domains, start the next numbered batch for +2,000 net-new domains using global Place-ID/domain dedupe.
7. Preserve the breadth-first / nationwide shallow-sweep strategy instead of exhausting one state before moving on.
8. Never auto-chain a second 2K batch on the same day.
9. Stop permanently after the +18,000 campaign expansion goal is reached.

Architecture remains:
`Places Aggregate COUNT -> recursive split -> Place IDs -> global Place-ID dedupe -> Place Details Pro context -> Maps Grounding Lite official domain -> global domain dedupe -> Ready for Crawl Evidence -> Crawl4AI homepage evidence -> Ready for Validation`.
