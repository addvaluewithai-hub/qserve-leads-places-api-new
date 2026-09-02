# Market Coverage Management — Lawyers US

Status: **production operating model**  
Last updated: **2026-09-02**

This document answers one operational question:

> After one 1,000-lead build, where should Agent 1 search next, and how do we prevent duplicate leads or random market selection?

The answer is a managed market queue backed by a static plan plus dynamic D1 coverage state.

## Source of truth

Static desired market universe:

```text
market_plans/lawyers-us.json
```

Dynamic actual state:

```text
D1.market_coverage
D1.market_run_history
```

Campaign:

```text
campaigns/lawyers-us.json
```

Do not manually maintain a vague note such as "Texas done". Coverage is tracked per market/metro and per pass.

## Important historical correction

The first validated 1,000-domain working set used **92 Text Search requests across 92 markets** and stopped at **New Haven, CT**.

It did **not** consume the remaining primary queue. In particular, the first build stopped before the primary Texas markets in the original plan.

Therefore Texas is not considered exhausted.

## Status lifecycle

Each market has one dynamic status:

```text
queued
partial
covered_once
exhausted
cooling
```

Meaning:

- `queued` — never searched by the managed production queue yet.
- `partial` — a pass produced good net-new yield; keep the market eligible for a later pass after queued markets are preferred.
- `covered_once` — searched once; do not immediately repeat it, but it may be revisited after the cooldown.
- `exhausted` — current pass produced very low net-new yield; deprioritize it.
- `cooling` — manually/operationally paused until later.

One search pass never means a city/state is permanently complete.

## Selection policy

Default priority is:

```text
1. queued primary markets
2. queued secondary-expansion markets
3. partial markets
4. covered_once markets only after revisit cooldown
5. never auto-select exhausted/cooling
```

Current default revisit cooldown:

```text
90 days
```

Current target per build:

```text
1,000 NET-NEW unique website domains
```

The builder does not stop at 1,000 raw Google results.

## Current next high-level sequence

The plan currently contains 250 managed markets:

```text
92 historical covered_once
158 queued
```

The first queued primary markets are:

```text
Providence, RI
Boston, MA
Worcester, MA
Portland, ME
Manchester, NH
Burlington, VT
Newark, NJ
Trenton, NJ
Virginia Beach, VA
Savannah, GA
Atlanta, GA
Augusta, GA
Fort Worth, TX
Austin, TX
San Antonio, TX
Houston, TX
El Paso, TX
```

After the remaining primary markets, the queue expands into secondary metros/cities across the US, including additional Texas markets.

This order is data/config, not hard-coded business logic. Reprioritize by editing `market_plans/lawyers-us.json` and syncing the plan to D1.

## Cross-run dedupe

Before any Google call can count toward the new target, Agent 1 loads the existing campaign state from D1.

Mandatory exclusion keys:

```text
Google Place ID
normalized official website domain
```

The next-run builder also checks the global `lead_domains` registry so a known domain cannot silently become a second canonical lead.

A new branch/location of an already-known firm does not count as a new working lead.

## D1 tables

### `lead_domains`

Canonical normalized domain registry:

```text
lead_id
website_domain
verified
source
updated_at
```

### `market_coverage`

One aggregate row per campaign + market:

```text
campaign_id
market_key
market_label
state_code
tier
priority
phase
status
search_count
raw_places
net_new_place_ids
grounding_calls
quality_passes
net_new_domains
last_yield_per_search
first_searched_at
last_searched_at
last_run_id
notes
```

### `market_run_history`

Append-only per-market run measurements so yield changes can be audited later.

## Bootstrap the existing first 1,000

Before running `next 1,000`, the validated first working set must exist in D1. Otherwise the builder cannot prove that a candidate is net-new.

Use:

```bash
python scripts/bootstrap_lawyers_us_campaign.py \
  --campaign lawyers-us \
  --input-dir <directory-containing-lawyers_1000.csv-summary.json-search_log.json>
```

The bootstrap:

1. creates/updates the `lawyers-us` campaign,
2. stores the first working-set businesses,
3. writes normalized domains,
4. creates campaign membership as `Ready for Validation`, `qualified=0`,
5. seeds the first 92 searched markets as `covered_once`.

It makes **zero Google calls**.

## See the current market queue

```bash
python scripts/market_manager.py status --campaign lawyers-us --next 25
```

Sync config changes into D1:

```bash
python scripts/market_manager.py sync --campaign lawyers-us
```

Show only the next markets:

```bash
python scripts/market_manager.py next --campaign lawyers-us --next 25
```

These commands require the Cloudflare D1 environment variables.

## Build the next 1,000

After bootstrap:

```bash
export GOOGLE_API_KEY=...
export CLOUDFLARE_ACCOUNT_ID=...
export CLOUDFLARE_API_TOKEN=...
export D1_DATABASE_ID=...

python scripts/build_next_1000_lawyers.py \
  --campaign lawyers-us \
  --target 1000
```

The builder:

1. loads existing D1 Place IDs/domains,
2. selects the next markets from `market_coverage`,
3. performs minimal Text Search Pro discovery,
4. excludes old Place IDs before Grounding,
5. resolves website/rating/review count using Maps Grounding Lite,
6. applies the 4.7 / 20+ quality gate,
7. excludes existing/duplicate domains,
8. records market yield after every market,
9. continues until exactly 1,000 net-new domains are collected,
10. writes the new working set into D1 as `Ready for Validation`, `qualified=0`.

If the available market plan cannot produce the requested target, the script preserves every accepted net-new lead in D1 and reports the remaining deficit. Expand/reprioritize the market plan, then rerun with the remaining target. Cross-run dedupe prevents the saved partial set from being counted twice.

## Why this structure

This separates three concerns cleanly:

```text
WHERE should we search?       → market plan
WHAT have we already covered? → D1 market coverage/history
WHO have we already collected?→ D1 Place IDs + domain registry
```

That means Agent 1 can be given a simple instruction:

> Get the next 1,000 lawyers.

The agent should not need a human to manually choose cities, remember previous batches, or inspect spreadsheets for duplicate domains.
