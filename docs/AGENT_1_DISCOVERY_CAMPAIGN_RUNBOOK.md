# Agent 1 Runbook — Discovery, Campaign Build, and Homepage Collection

Status: **production operating procedure**

Last updated: **2026-09-02**

## Mission

Agent 1 creates the next working set of leads for a campaign and prepares them for human/agent validation.

For the lawyer workflow, the unit of success is **1,000 net-new unique law-firm website domains**, not 1,000 raw Google results and not 1,000 Google locations.

Agent 1 owns:

1. campaign setup,
2. low-cost Google discovery,
3. Maps Grounding Lite enrichment,
4. identity and quality filtering,
5. cross-run dedupe,
6. campaign/D1 insertion,
7. homepage-only Crawl4AI collection,
8. handoff to Agent 2.

Agent 1 does **not** decide whether a service gap is real and does **not** search for owner emails.

---

## Read these files first

Before doing anything, read:

- `README.md`
- `docs/FINAL_LEAD_ENGINE_ARCHITECTURE.md`
- this file
- the relevant `campaigns/<campaign>.json` if one already exists

For lawyers, use `scripts/build_1000_lawyers.py` as the validated reference implementation for discovery economics and data extraction. Do not blindly reuse the older expensive Google field masks from `scripts/run_campaign.py` for a large lawyer build.

---

## Required credentials

For the current lawyer discovery path:

```text
GOOGLE_API_KEY
```

For D1 sync:

```text
CLOUDFLARE_ACCOUNT_ID
CLOUDFLARE_API_TOKEN
D1_DATABASE_ID
```

Live Google and Crawl workflows must remain **manual-dispatch only**. A normal code push must not silently make live Google requests.

---

## Campaign definition

A campaign is a logical sales/research project, not merely a Google query.

Example lawyer campaign intent:

```text
Find high-reputation active US law firms with real websites,
then inspect their website architecture for service-page gaps,
then find a direct public owner/decision-maker email only for confirmed gaps.
```

For generic lawyer discovery, do **not** pre-limit discovery to one service such as Family Law or Probate. The firm can offer many services; Agent 2 discovers the actual gaps later.

A new campaign should have a stable ID, for example:

```text
lawyers-us-gap-2026-09-a
```

Recommended logical config:

```json
{
  "id": "lawyers-us-gap-2026-09-a",
  "name": "US Lawyers — Service Gap Campaign",
  "vertical": "legal",
  "discovery": {
    "included_type": "lawyer",
    "strict_type_filtering": true,
    "minimum_rating": 4.7,
    "minimum_reviews": 20,
    "target_new_domains": 1000
  },
  "crawl": {
    "engine": "crawl4ai",
    "mode": "homepage_links_only",
    "same_domain_only": true,
    "follow_links": false,
    "classification": false
  },
  "qualification": {
    "gap_validation_required": true,
    "owner_required": true,
    "direct_owner_email_required": true
  }
}
```

The exact config schema may evolve, but the operating rules in this runbook are authoritative.

---

# Phase 1 — Load the exclusion set

This is mandatory when the user asks for **another 1,000**.

The existing `build_1000_lawyers.py` dedupes Place IDs and domains inside one run. A new agent must additionally exclude leads already collected in earlier runs/campaign membership.

Build two exclusion sets from D1 and/or previous authoritative artifacts:

```text
existing_place_ids
existing_website_domains
```

Canonical domain normalization:

1. lowercase hostname,
2. remove leading `www.`,
3. ignore path/query/fragment,
4. treat the normalized hostname as the domain key.

A lead does **not** count toward the new target if either:

```text
Place ID already exists
OR
normalized website domain already exists
```

If the same firm has ten Google locations but one website domain, it counts as **one business opportunity**.

### Stop condition

Do not stop at 1,000 raw candidates. Stop only when there are:

```text
1,000 net-new unique accepted domains
```

If dedupe removes 150 candidates, continue searching additional markets until the final net-new count is 1,000.

---

# Phase 2 — Google discovery

## Lawyer Text Search request

Use generic vertical discovery:

```text
textQuery = "lawyer in <market>"
includedType = "lawyer"
strictTypeFiltering = true
minRating = 4.7
pageSize = 20
```

Use only the minimal Text Search Pro response fields:

```text
places.id
places.displayName
places.formattedAddress
places.businessStatus
```

Do not request during discovery:

```text
websiteUri
rating
userRatingCount
phone
openingHours
reviews[]
```

Those fields are unnecessary at this stage and can move the request to a more expensive SKU.

Use a broad list of independent US markets. Prefer geographic diversity over repeatedly paging a single market because diversity reduces duplicate multi-location firms.

Immediately reject:

- missing Place ID,
- non-`OPERATIONAL` business,
- Place ID already in the exclusion set.

Deduplicate Place IDs before Grounding Lite.

---

# Phase 3 — Maps Grounding Lite enrichment

Grounding Lite `search_places` did **not** resolve known businesses when given only a raw Place ID. Live tests returned HTTP 200 with `{}`.

Therefore query Grounding using the human-readable identity from Text Search:

```text
<business name>, <formatted address> official website rating review count
```

For every response:

1. extract the returned Google Place ID/source,
2. require it to match the discovery Place ID,
3. extract official website URL from the grounded summary,
4. extract rating,
5. extract review count,
6. retain the Google Maps grounding source/attribution.

### Never accept a mismatched identity automatically

If Grounding returns a different Place ID:

```text
status = Needs Review
```

It must not count toward the 1,000 accepted domains.

---

# Phase 4 — Initial quality gate

For the current lawyer working set, require:

```text
businessStatus == OPERATIONAL
rating >= 4.7
review_count >= 20
grounding Place ID == discovery Place ID
official website resolved
```

No review text is required.

No Place Details Enterprise call is required in the normal path.

The rating filter in Text Search is a cheap prefilter; the actual value parsed from Grounding is the final quality check.

---

# Phase 5 — Website verification and domain dedupe

Normalize the resolved website domain.

Reject it from the new-count calculation if the domain is already present in:

```text
existing_website_domains
OR
current_run_selected_domains
```

Make a basic independent open-web request to the website.

Record:

```text
website
website_domain
website_http_status
website_final_url
website_title
website_verified_open_web
```

A bot-blocked response does not automatically mean the domain is fake. If Grounding identity is matched and domain continuity is preserved, keep it in a browser verification queue and let Crawl4AI test it later.

Never invent a replacement URL when verification fails.

---

# Phase 6 — Continue until 1,000 NET-NEW domains

The validated first 1,000-lawyer build used approximately:

```text
92 Text Search Pro requests
1,252 Maps Grounding Lite calls
0 Place Details Enterprise calls
```

That number is a benchmark, not a quota. A later build may need more or fewer requests depending on market overlap and the exclusion set.

Continue market-by-market until the accepted set contains exactly the requested number of **new unique domains**.

Keep an explicit run summary:

```text
campaign_id
discovery_run_id
target_new_domains
text_search_calls
grounding_calls
unique_place_ids_seen
excluded_existing_place_ids
excluded_existing_domains
grounding_identity_matches
quality_gate_passes
new_unique_domains_collected
markets_used
started_at
completed_at
```

---

# Phase 7 — Normalize the campaign data contract

The current `build_1000_lawyers.py` artifact uses fields such as:

```text
place_id
review_count
source_market
```

The older D1 sync path historically expects fields such as:

```text
id
user_rating_count
source_area
```

Do not pass the raw working-set CSV blindly into the older sync script.

Normalize the data first.

Recommended mapping:

| Working-set field | Canonical/D1 field |
|---|---|
| `place_id` | `leads.id` |
| `name` | `leads.name` |
| `rating` | `leads.rating` |
| `review_count` | `leads.user_rating_count` |
| `website` | `leads.website` |
| `google_maps_source` | `leads.google_maps_url` |
| `address` | `leads.address` |
| `source_market` | `leads.source_area` / campaign source area |
| constant `OPERATIONAL` | `leads.business_status` |
| constant `lawyer` | `leads.primary_type` |

Do not fabricate phone, opening-hours, review-sample, or direct-email values when they were not collected.

---

# Phase 8 — Create/update campaign membership in D1

Canonical business data belongs in `leads`.

Campaign-specific state belongs in `campaign_leads`.

For each new accepted working-set lead, initial campaign membership should conceptually be:

```text
qualified = 0
status = "Ready for Validation"
qualification_reason = "pending_gap_validation"
```

Do **not** mark a lead Qualified at discovery time.

The campaign record should be inserted/updated in `campaigns`, and a run record should be stored in `campaign_runs` with the discovery summary.

If D1 schema/scripts have not yet been upgraded to first-class gap/contact fields, preserve evidence in structured artifacts and campaign notes rather than stuffing fake values into unrelated columns.

---

# Phase 9 — Crawl4AI homepage collection

Once the 1,000 working domains are saved, run Crawl4AI.

Crawl4AI is a **dumb collector only**.

For each lead:

1. load the homepage once in a browser,
2. include rendered header/navigation/footer,
3. collect all visible same-domain links,
4. record destination URL + anchor text,
5. retry the homepage once if needed,
6. stop.

It must not:

- deep crawl,
- recursively follow links,
- classify service pages,
- decide whether a gap exists,
- search for emails.

Validated production scripts/workflows include:

```text
scripts/crawl_working_set_homepages_parallel.py
.github/workflows/crawl-lawyers-working-set.yml
```

Recommended worker count after validation:

```text
4 workers
```

For large sets, use batches (for example 100–300 leads per artifact) so failures can be retried independently.

Required outputs per batch:

```text
homepage_links.csv
homepage_links.json
homepage_fetch_summary.csv/json
homepage_links_summary.json
```

Any failed crawl or completed homepage with suspiciously zero useful links goes to Agent 2 as a mandatory double-check case. It is never automatically Qualified.

---

# Phase 10 — Handoff to Agent 2

Agent 1 is finished when every accepted campaign lead has:

```text
stable Place ID
business name
address/source market
rating
review count
official website
normalized domain
Google Maps grounding source
campaign membership
homepage crawl evidence OR a crawl-review flag
status = Ready for Validation
```

Agent 2 receives:

1. campaign ID,
2. working-set/canonical lead rows,
3. homepage link artifacts,
4. homepage fetch summary/failure queue.

Agent 2 then owns all service-gap validation, owner identification, direct-email enrichment, and final qualification.

---

## Agent 1 must NEVER do these things

- Do not classify a lead as Qualified just because Google quality is good.
- Do not assume a missing homepage link proves a gap.
- Do not deep crawl with Crawl4AI.
- Do not request review text for this workflow.
- Do not use Place Details Enterprise by default.
- Do not count duplicate offices/domains toward the 1,000 target.
- Do not overwrite a better existing canonical business record with lower-confidence data.
- Do not run live Google discovery automatically on code push.

---

## Agent 1 final checklist

Before handing off, confirm:

```text
[ ] Campaign ID exists
[ ] Existing Place IDs/domains loaded as exclusions
[ ] Target is NET-NEW unique domains
[ ] Generic lawyer discovery used
[ ] Minimal Text Search Pro fields used
[ ] Grounding identity matched
[ ] Rating >= 4.7
[ ] Review count >= 20
[ ] Official website resolved
[ ] Domain deduped across old + current runs
[ ] Exactly requested number of new domains collected
[ ] Campaign/D1 rows normalized
[ ] No lead marked Qualified yet
[ ] Homepage-only Crawl4AI executed in batches
[ ] Failures/zero-link sites preserved for review
[ ] Handoff artifacts ready for Agent 2
```
