# ZIP Coverage Management — Lawyers US

Status: **production operating model**

Last updated: **2026-09-02**

This document answers:

> Where do we search next, how do we know what has been covered, and how do we avoid repeatedly seeing the same firms?

## Sources of truth

Static high-level territory plan:

```text
market_plans/lawyers-us-zips.json
```

Dynamic coverage state:

```text
D1.zip_coverage
D1.zip_run_history
```

Global business identity:

```text
D1.leads
D1.lead_domains
```

Global contacted-business block:

```text
D1.outreach_suppression
```

## Coverage hierarchy

```text
State
  ↓
Preferred cities
  ↓
ZIP codes
```

The ZIP code is the actual search/coverage unit.

Do not use vague state notes such as `Texas done`. State summaries are calculated from ZIP rows.

## ZIP universe

ZIP rows are generated from the US postal-code dataset bundled through `pgeocode`/GeoNames.

Each row records ZIP/city/state/centroid, plan priority, status, page/search counts, exact-ZIP results, quality passes, net-new domains and duplicate counts.

The centroid is used only to create a reasonable `locationRestriction` rectangle.

A Google result only counts for a ZIP when the returned address components explicitly contain:

```text
postal_code == target ZIP
```

## Priority plan

Current first phase:

```text
TX
FL
GA
NC
TN
AZ
NV
CO
```

Texas is first. Within Texas, preferred cities such as Houston, Dallas, Austin, San Antonio, Fort Worth and El Paso receive higher ZIP priority than the rest of the state.

After the first phase, large markets and national expansion follow.

The order is configuration, not hard-coded discovery logic.

## Status lifecycle

```text
queued
in_progress
partial
covered
saturated
failed
cooling
```

- `queued` — never processed by V2.
- `in_progress` — currently owned by a run.
- `partial` — stopped because target/budget was reached before ZIP completion.
- `covered` — completed under pagination policy.
- `saturated` — reached configured page limit while more results appeared available.
- `failed` — retryable API/crawl processing failure.
- `cooling` — manually paused.

`zip_manager.py` recovers stale `in_progress` rows after a crash.

## Pagination policy

Page 1 always runs.

Default page 2/3 trigger:

```text
page 1 raw count >= 20
AND
page 1 exact-ZIP count >= 5
AND
nextPageToken exists
```

Maximum:

```text
3 pages per ZIP
```

All pages are requested during the same ZIP processing pass.

This replaces the old failure mode where revisiting a metro repeatedly returned the same first 20 results.

## Global dedupe

A candidate cannot count as a net-new business if:

```text
Place ID already exists
OR
registrable domain already exists
OR
domain is globally suppressed after outreach
OR
same Place ID/domain was already accepted in current run
```

This is global across the CRM, not campaign-local.

A multi-office firm is one sales opportunity when offices resolve to the same registrable domain.

## Historical first 1,000

The original first 1,000 came from the earlier metro/Grounding experiment.

Bootstrap them before V2 discovery:

```bash
python scripts/bootstrap_lawyers_us_campaign.py \
  --campaign lawyers-us \
  --input-dir <historical-artifact>
```

The V2 bootstrap does not pretend old metro searches are ZIP coverage. V2 ZIP rows start from their real managed state, while global Place-ID/domain dedupe prevents historical firms from counting again.

## Commands

Sync/generate ZIP universe:

```bash
python scripts/zip_manager.py sync --campaign lawyers-us
```

Coverage report:

```bash
python scripts/zip_manager.py status --campaign lawyers-us --next 50
```

Next ZIPs:

```bash
python scripts/zip_manager.py next --campaign lawyers-us --next 50
```

Build next 1,000:

```bash
python scripts/build_next_1000_lawyers_zip.py \
  --campaign lawyers-us \
  --target 1000 \
  --max-zips 5000 \
  --max-search-requests 900
```

## Request-budget management

Successful Text Search Enterprise page calls are written to:

```text
api_usage_ledger
```

Current internal monthly ceiling:

```text
900 requests
```

This leaves headroom under the currently documented 1,000-request Text Search Enterprise free cap.

The D1 ledger only measures calls from this repository. Google Cloud Billing remains authoritative.

## Outreach management

Discovery dedupe and outreach suppression are separate concepts.

Canonical dedupe:

```text
already known business
→ do not count again as net-new
```

Outreach suppression:

```text
actually contacted
→ do not contact again through another campaign
```

After outreach:

```bash
python scripts/mark_business_contacted.py \
  --lead-id <PLACE_ID> \
  --campaign lawyers-us \
  --email <DIRECT_OWNER_EMAIL> \
  --status Contacted
```

Re-engagement uses the existing canonical business and an explicit future state; it is not rediscovered as a new business.
