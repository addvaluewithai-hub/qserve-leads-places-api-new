# Agent 1 Runbook — Discovery, Market Management, Campaign Build, Homepage Collection

Status: **production operating procedure**  
Last updated: **2026-09-02**

## Mission

Agent 1 creates the next working set of leads for a campaign and prepares them for Agent 2.

For the lawyer workflow, success means:

```text
1,000 NET-NEW unique law-firm website domains
```

—not 1,000 raw Google results, not 1,000 Google locations, and not 1,000 rows that include firms already collected in older runs.

Agent 1 owns:

1. campaign setup,
2. market/territory selection,
3. low-cost Google discovery,
4. Maps Grounding Lite enrichment,
5. identity and quality filtering,
6. cross-run Place-ID/domain dedupe,
7. campaign + D1 insertion,
8. homepage-only Crawl4AI collection,
9. handoff to Agent 2.

Agent 1 does **not** decide whether a service gap is real and does **not** search for owner emails.

---

## Read these files first

Read in this order:

1. `README.md`
2. `docs/FINAL_LEAD_ENGINE_ARCHITECTURE.md`
3. `docs/MARKET_COVERAGE_MANAGEMENT.md`
4. this file
5. `campaigns/lawyers-us.json`
6. `market_plans/lawyers-us.json`

For the current scalable lawyer production path, the main scripts are:

```text
scripts/bootstrap_lawyers_us_campaign.py
scripts/market_manager.py
scripts/build_next_1000_lawyers.py
scripts/crawl_working_set_homepages_parallel.py
```

`scripts/build_1000_lawyers.py` remains useful as the validated historical reference for the first 1,000 build, but `build_next_1000_lawyers.py` is the cross-run-aware production builder.

---

## Credentials

Google discovery / Grounding:

```text
GOOGLE_API_KEY
```

D1 state, cross-run dedupe, campaign membership, and market coverage:

```text
CLOUDFLARE_ACCOUNT_ID
CLOUDFLARE_API_TOKEN
D1_DATABASE_ID
```

Live Google/Crawl workflows must remain **manual-dispatch only**. A code push must not trigger live discovery.

---

# 1. Campaign and market-management model

Current campaign:

```text
campaigns/lawyers-us.json
```

Static market universe / ordering:

```text
market_plans/lawyers-us.json
```

Dynamic market coverage:

```text
D1.market_coverage
D1.market_run_history
```

Canonical domain registry:

```text
D1.lead_domains
```

Never manage geography with vague notes such as:

```text
Texas done
Florida done
```

Coverage is per market/pass and has explicit states:

```text
queued
partial
covered_once
exhausted
cooling
```

One pass never permanently exhausts a state.

---

# 2. Bootstrap rule — mandatory before "next 1,000"

The validated first working set already exists as an artifact. Before requesting another 1,000, it must be represented in D1 so the next builder can prove what is net-new.

Bootstrap once:

```bash
python scripts/bootstrap_lawyers_us_campaign.py \
  --campaign lawyers-us \
  --input-dir <first-1000-artifact-directory>
```

The directory must contain:

```text
lawyers_1000.csv
summary.json
search_log.json
```

Bootstrap performs **zero Google calls**.

It stores:

- first working-set leads,
- normalized domains,
- campaign memberships,
- `Ready for Validation` status,
- first 92 market passes in coverage state.

The production next-1000 builder intentionally refuses to proceed if D1 has no campaign leads while the plan says a historical 1,000 exists.

---

# 3. Market selection

Never choose cities ad hoc if a managed plan exists.

Inspect current state:

```bash
python scripts/market_manager.py status --campaign lawyers-us --next 25
```

Show only next markets:

```bash
python scripts/market_manager.py next --campaign lawyers-us --next 25
```

Sync a changed plan:

```bash
python scripts/market_manager.py sync --campaign lawyers-us
```

Default order:

```text
queued primary
→ queued secondary expansion
→ partial
→ covered_once after cooldown
```

`exhausted` and `cooling` are not auto-selected.

Read `docs/MARKET_COVERAGE_MANAGEMENT.md` for the current next-market sequence and rules.

---

# 4. Cross-run exclusion set

Before Google discovery, load from D1:

```text
existing campaign Place IDs
existing normalized website domains
```

The production builder also checks the global domain registry.

A result does not count as new if:

```text
Place ID already exists
OR
website domain already exists
```

Domain normalization:

1. lowercase hostname,
2. remove leading `www.`,
3. ignore scheme/path/query/fragment.

Multiple Google offices sharing one firm domain count as one business opportunity.

---

# 5. Low-cost Google discovery

For each selected market:

```text
textQuery = "lawyer in <market>"
includedType = lawyer
strictTypeFiltering = true
minRating = 4.7
pageSize = 20
```

Minimal Text Search Pro fields only:

```text
places.id
places.displayName
places.formattedAddress
places.businessStatus
```

Do not request in discovery:

```text
websiteUri
rating
userRatingCount
phone
openingHours
reviews[]
```

Immediately discard:

- missing Place ID,
- non-operational business,
- existing Place ID,
- Place ID already seen in the current run.

---

# 6. Maps Grounding Lite enrichment

Raw Place-ID-only Grounding was tested and did not resolve the businesses reliably.

Use:

```text
<business name>, <formatted address> official website rating review count
```

Require:

```text
Grounding returned Place ID == discovery Place ID
```

Extract:

```text
official website
rating
review count
Google Maps source
```

Do not trust a mismatched identity automatically.

---

# 7. Quality gate

Current lawyers-us gate:

```text
business status = OPERATIONAL
rating >= 4.7
review count >= 20
Grounding Place ID match = true
official website domain resolved
```

Review text is not needed.

Place Details Enterprise is not part of the normal path.

---

# 8. Website/domain verification

Make a basic independent request to the resolved site and preserve:

```text
website
website_domain
website_http_status
website_final_url
website_title
website_verified_open_web
```

A bot-blocked site is not automatically fake. It can continue to Crawl4AI/manual validation if identity/domain evidence is strong.

Never invent a substitute URL.

Before adding the domain to the working-set count, exclude:

```text
existing D1 domains
current-run selected domains
```

---

# 9. Build the next net-new target

Normal production command:

```bash
python scripts/build_next_1000_lawyers.py \
  --campaign lawyers-us \
  --target 1000
```

The builder automatically:

1. reads D1 exclusions,
2. reads the market queue,
3. searches market-by-market,
4. updates market yield after every search,
5. excludes old Place IDs before Grounding,
6. excludes old/duplicate domains after Grounding,
7. continues until the requested number of net-new domains is reached,
8. writes accepted leads to D1 with `qualified=0` and `Ready for Validation`.

Historical benchmark for the first 1,000:

```text
92 Text Search Pro requests
1,252 Maps Grounding Lite calls
0 Place Details Enterprise calls
```

Do not treat those counts as fixed quotas.

### If the current plan cannot reach the target

Accepted leads are still saved to D1 so work is not lost.

The script reports the remaining deficit. Expand/reprioritize the market plan and rerun with the remaining target.

Cross-run dedupe ensures the saved partial set is not counted again.

---

# 10. Market-yield bookkeeping

After every market pass, preserve:

```text
raw places
net-new Place IDs
grounding calls
quality passes
net-new domains
yield per search
run ID
search timestamp
status after pass
```

This updates:

```text
market_coverage
market_run_history
```

Status policy is data-driven:

- strong net-new yield → `partial`,
- normal one-pass completion → `covered_once`,
- very low yield → `exhausted`.

The exact thresholds live in `market_plans/lawyers-us.json`.

---

# 11. D1 state after discovery

A discovery-quality business is **not Qualified**.

Initial campaign membership:

```text
qualified = 0
status = "Ready for Validation"
qualification_reason = "working_set_ready_for_validation"
```

Canonical business goes in:

```text
leads
lead_domains
```

Campaign-specific membership goes in:

```text
campaign_leads
```

Run/territory state goes in:

```text
campaign_runs
market_coverage
market_run_history
```

---

# 12. Crawl4AI homepage collection

After working-set creation, Crawl4AI remains a **dumb collector**.

For each site:

1. load homepage only,
2. render normal header/nav/footer,
3. collect visible same-domain links,
4. save URL + anchor text,
5. retry once if needed,
6. stop.

Never:

- deep crawl,
- recursively follow links,
- classify pages,
- decide gaps,
- search emails.

Use the validated parallel collector:

```text
scripts/crawl_working_set_homepages_parallel.py
```

Default:

```text
4 workers
```

Use batches so failed sites can be retried independently.

---

# 13. Handoff to Agent 2

Agent 1 is complete when each accepted lead has:

```text
Place ID
name
address/source market
rating
review count
official website
normalized domain
Google Maps source
campaign membership
homepage links OR crawl-review flag
status = Ready for Validation
```

Agent 2 then performs:

```text
homepage-link inspection
→ mandatory site double-check
→ real gap validation
→ owner identification
→ direct public owner email
→ final qualification
```

---

## Agent 1 must NEVER

- mark discovery leads Qualified,
- choose random markets while ignoring the market plan,
- count existing Place IDs/domains toward the target,
- count multiple offices of one domain as multiple opportunities,
- assume a missing homepage link proves a gap,
- deep crawl with Crawl4AI,
- request review text for this workflow,
- use Place Details Enterprise by default,
- run live discovery on normal code push.

---

## Final checklist

```text
[ ] lawyers-us campaign exists
[ ] market plan synced
[ ] historical working set bootstrapped once
[ ] existing Place IDs/domains loaded from D1
[ ] next markets selected from managed queue
[ ] target means NET-NEW domains
[ ] minimal Text Search Pro fields used
[ ] Grounding identity match required
[ ] rating >= 4.7
[ ] review count >= 20
[ ] official website resolved
[ ] old + current domains deduped
[ ] accepted leads saved to D1
[ ] qualified remains 0
[ ] market yield/history updated
[ ] homepage-only Crawl4AI completed or review flag preserved
[ ] Agent 2 handoff ready
```
