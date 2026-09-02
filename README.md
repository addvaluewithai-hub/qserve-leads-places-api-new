# Multi-Campaign Lead Engine + CRM

A reusable lead-discovery, website-validation, enrichment, and outreach CRM built around Google Places API (New), Maps Grounding Lite, Crawl4AI, GitHub Actions, Cloudflare Pages, and Cloudflare D1.

The repository supports multiple verticals and campaigns. The most mature production workflow is the **large-scale lawyer service-gap pipeline**, which has been validated on a 1,000-domain working set.

---

## Start here

For the current lawyer production workflow, read these in order:

1. `docs/FINAL_LEAD_ENGINE_ARCHITECTURE.md` — architecture/source-of-truth decision.
2. `docs/AGENT_1_DISCOVERY_CAMPAIGN_RUNBOOK.md` — how an agent creates the next 1,000 net-new working leads, adds them to a campaign, and collects homepage links.
3. `docs/AGENT_2_VALIDATE_ENRICH_QUALIFY_RUNBOOK.md` — how an agent validates the real service gap, then finds the owner/direct public email and performs final qualification.

Supporting benchmark/history docs include:

- `docs/BENCHMARK_10_REQUESTS_2026-09-02.md`
- `docs/BUILD_1000_LAWYERS_2026-09-02.md`
- `docs/HOMEPAGE_BATCH_0_100_REVIEW_2026-09-02.md`
- `docs/FIRST_4_OUTREACH_READY_LEADS_2026-09-02.md`

---

# Current production architecture — lawyers

```text
Agent 1

Google Places Text Search Pro
(minimal identity fields only)
        ↓
Place ID + business name + address + business status
        ↓
Maps Grounding Lite
(name + address → official website + rating + review count)
        ↓
Place-ID identity match
+ quality gate
+ existing-lead exclusion
+ domain dedupe
        ↓
1,000 NET-NEW unique law-firm domains
        ↓
Campaign / D1 membership
status = Ready for Validation
qualified = 0
        ↓
Crawl4AI homepage only
        ↓
all visible same-domain homepage/header/footer/nav links
        ↓
Agent 2

Inspect Crawl4AI links
        ↓
MANDATORY website double-check
        ↓
real service offered + no dedicated exact-service page
        ↓
Confirmed Gap
        ↓
identify owner / decision maker
        ↓
find DIRECT PUBLIC email for that exact person
        ↓
Qualified
```

A business is **not Qualified during discovery**. Google quality creates a working set; qualification happens only after service-gap and contact evidence are complete.

---

# Two-agent operating model

## Agent 1 — Discovery, Campaign Build, Homepage Collection

Runbook:

```text
docs/AGENT_1_DISCOVERY_CAMPAIGN_RUNBOOK.md
```

Agent 1 owns:

- campaign setup,
- exclusion of existing Place IDs/domains,
- generic lawyer discovery,
- Maps Grounding Lite enrichment,
- rating/review-count quality gate,
- official website resolution,
- cross-run Place-ID/domain dedupe,
- collecting exactly the requested number of **net-new domains**,
- normalizing/inserting campaign records,
- homepage-only Crawl4AI collection,
- handoff to Agent 2.

Agent 1 does **not**:

- classify service gaps,
- search for owner emails,
- mark discovery candidates Qualified.

## Agent 2 — Gap Validation, Contact Enrichment, Final Qualification

Runbook:

```text
docs/AGENT_2_VALIDATE_ENRICH_QUALIFY_RUNBOOK.md
```

Agent 2 works lead-by-lead:

```text
Crawl links
→ website double-check
→ confirm real gap
→ only then find owner
→ only then find direct public owner email
→ Qualified
```

If there is no confirmed gap, Agent 2 stops before email research.

---

# Lawyer qualification rule

The final rule is deliberately strict:

```text
Real service offered
+
No dedicated exact-service internal page after double-check
+
Owner / decision maker identified
+
Direct public email for that exact person
=
QUALIFIED
```

## Exact-service page rule

A general page such as:

```text
/services
/practice-areas
/what-we-do
```

is allowed and does not automatically disqualify a service gap.

A service gap is disqualified only when that **exact service** has its own dedicated page/URL.

Examples:

```text
target Family Law + /family-law            → Disqualified for Family Law

target Probate + /estate-planning only     → Probate may still be a gap

target Adoption + /family-law only         → Adoption may still be a gap
```

Dedicated pages for other services do not disqualify the entire firm. A single law firm can have several service opportunities with different outcomes.

## Missing homepage link is not enough

Crawl4AI evidence is only the first check.

If no obvious dedicated service URL is present in homepage links, Agent 2 must independently inspect/search the official website before confirming the gap.

If the firm does not genuinely offer the service:

```text
Not Relevant
```

not Qualified.

Ambiguity becomes:

```text
Needs Review
```

not a guessed positive decision.

---

# Direct-email rule

Final qualification requires a **direct public email for the selected owner/decision maker**.

Acceptable contacts normally include:

- founder,
- owner,
- founding attorney,
- managing partner when clearly the business decision maker,
- solo attorney/owner.

Generic addresses are not accepted, including:

```text
info@
contact@
hello@
office@
support@
reception@
intake@
admin@
team@
marketing@
appointments@
```

A receptionist, intake coordinator, assistant, paralegal, or unrelated employee email is not a substitute for the owner email.

Emails must be publicly evidenced. **Never guess or pattern-generate an email.**

If a gap is confirmed but no direct owner email is found:

```text
Gap Confirmed - Direct Email Missing
qualified = 0
```

---

# Low-cost Google discovery design

The scaled lawyer workflow intentionally avoids Place Details Enterprise and review text in the normal path.

## Text Search

Use generic lawyer discovery, for example:

```text
textQuery = "lawyer in Phoenix, AZ"
includedType = lawyer
strictTypeFiltering = true
minRating = 4.7
pageSize = 20
```

Minimal response field mask:

```text
places.id
places.displayName
places.formattedAddress
places.businessStatus
```

Do not request `websiteUri`, `rating`, `userRatingCount`, phone, opening hours, or `reviews[]` during the discovery request.

## Grounding Lite

For each unique candidate, query using:

```text
<business name>, <address> official website rating review count
```

Require the Grounding result's Place ID to match the discovery Place ID before trusting the identity automatically.

A direct `Place ID only → Grounding search_places` lookup was tested on known law firms and returned empty results. Therefore the production path intentionally preserves the business name + address for Grounding.

## Validated 1,000-lawyer run

The first full working-set build collected:

```text
1,000 unique law-firm website domains
rating floor: 4.7
minimum reviews: 20
Text Search Pro requests: 92
Maps Grounding Lite calls: 1,252
Place Details Enterprise calls: 0
review-text requests: 0
```

Pricing and free caps can change. Verify current Google Maps Platform pricing before making cost claims for a new run.

---

# Getting ANOTHER 1,000 leads

Do not simply rerun the first-1,000 script and call its output new.

Before discovery, load the authoritative existing sets:

```text
existing_place_ids
existing_website_domains
```

A candidate only counts toward the new target when it is not already present by Place ID or normalized domain.

The stop condition is:

```text
1,000 NET-NEW unique accepted domains
```

not 1,000 raw Places results.

Full procedure:

```text
docs/AGENT_1_DISCOVERY_CAMPAIGN_RUNBOOK.md
```

---

# Crawl4AI — homepage links only

Crawl4AI is intentionally a **dumb collector**.

It should:

1. load one homepage,
2. render normal header/nav/footer,
3. collect all visible same-domain links,
4. save URL + anchor text,
5. retry once if needed,
6. stop.

It must not:

- deep crawl,
- recursively follow collected links,
- classify service pages,
- make Qualified/Disqualified decisions,
- search for emails.

Primary outputs:

```text
homepage_links.csv
homepage_links.json
homepage_fetch_summary.csv/json
homepage_links_summary.json
```

Validated large-set crawler:

```text
scripts/crawl_working_set_homepages_parallel.py
```

Validated worker count:

```text
4
```

Use batches so failures can be retried independently.

---

# Running the lawyer working-set builder

Validated script:

```bash
export GOOGLE_API_KEY=...
python scripts/build_1000_lawyers.py
```

GitHub Actions workflow:

```text
Actions → Build 1000 lawyer working set
```

The workflow is **manual-dispatch only**.

Important: `scripts/build_1000_lawyers.py` is the validated first-working-set reference implementation. For subsequent 1,000 sets, an agent must apply the existing Place-ID/domain exclusion procedure documented in Agent 1 before counting candidates toward the target.

---

# Running homepage collection

The working-set crawl consumes the saved working-set artifact; it does not repeat Google discovery.

Relevant workflow/script:

```text
.github/workflows/crawl-lawyers-working-set.yml
scripts/crawl_working_set_homepages_parallel.py
```

Use a batch start/limit and four workers after validation.

Example logical batch:

```text
start = 0
limit = 100
workers = 4
```

No Google Text Search or Grounding requests are required merely to recrawl a saved working set.

---

# Multi-campaign support

Existing campaign configs include:

- `campaigns/lawyers-tx.json`
- `campaigns/dentists-tx.json`
- `campaigns/cafes-eg.json`

The repository also still contains the reusable/older campaign runner:

```text
scripts/run_campaign.py
scripts/run_campaign_tracked.py
scripts/sync_campaign_to_d1.py
```

These remain useful for generic campaign work, dentists/cafes, and earlier flows, but the **large-scale lawyer production architecture is the two-agent workflow documented above**. Do not assume the older lawyer service-specific query configuration represents the current scaled-lawyer strategy.

---

# Campaign and D1 model

The core D1 model currently separates canonical businesses from campaign membership:

```text
leads
campaigns
campaign_runs
campaign_leads
lead_signals
```

This is important because one canonical business can participate in multiple campaigns without mixing campaign-specific state.

## Initial state after Agent 1

A newly discovered working lead should conceptually enter a campaign as:

```text
qualified = 0
status = Ready for Validation
qualification_reason = pending_gap_validation
```

## Final state after Agent 2

Only when gap + owner + direct public owner email are all evidenced:

```text
qualified = 1
status = Qualified
qualification_reason = confirmed_service_gap + verified_owner + direct_public_owner_email
```

## Working-set field normalization

The scaled builder uses names such as:

```text
place_id
review_count
source_market
```

while older campaign/D1 scripts may expect:

```text
id
user_rating_count
source_area
```

Do not blindly feed the raw 1,000-working-set CSV into an older sync path. Normalize the fields first. The exact mapping is documented in Agent 1.

---

# Status lifecycle

Recommended campaign lifecycle:

```text
Ready for Validation
        ↓
Needs Review / Not Relevant / Disqualified
        OR
Gap Confirmed
        ↓
Gap Confirmed - Owner Missing
Gap Confirmed - Direct Email Missing
        OR
Qualified
```

`Gap Confirmed` is evidence of a sales opportunity, but it is **not yet outreach-ready** under the current rule.

---

# GitHub Actions safety

Live Google, Grounding, Crawl, and D1 actions should be manual-dispatch workflows unless a deliberate scheduled/production automation is later designed.

Normal code pushes should validate/build code without silently consuming Google API calls.

Required secrets across the full system can include:

```text
GOOGLE_API_KEY
CLOUDFLARE_ACCOUNT_ID
CLOUDFLARE_API_TOKEN
D1_DATABASE_ID
```

---

# Repository architecture summary

```text
campaigns/
  campaign configurations

docs/
  FINAL_LEAD_ENGINE_ARCHITECTURE.md
  AGENT_1_DISCOVERY_CAMPAIGN_RUNBOOK.md
  AGENT_2_VALIDATE_ENRICH_QUALIFY_RUNBOOK.md
  benchmark/build/review reports

scripts/
  build_1000_lawyers.py
  benchmark_lawyer_discovery.py
  crawl_working_set_homepages.py
  crawl_working_set_homepages_parallel.py
  crawl_campaign_websites.py
  run_campaign.py
  run_campaign_tracked.py
  sync_campaign_to_d1.py

.github/workflows/
  manual discovery/build/crawl workflows

schema.sql
  Cloudflare D1 schema
```

---

# Next hardening priorities

The architecture is validated; the next improvements are mainly data-model/orchestration hardening:

1. Add first-class D1 tables/columns for service-gap evidence, contacts, contact evidence, and validation events.
2. Make the 1,000-builder natively exclusion-aware by reading existing Place IDs/domains before counting the next working set.
3. Add a first-class normalizer/sync path specifically for the scaled working-set fields instead of relying on older campaign field names.
4. Persist homepage-link evidence into D1 when useful instead of relying only on artifacts.
5. Create a durable validation queue so multiple Agent 2 workers can claim leads without duplicate work.
6. Add outreach suppression/dedupe rules across campaigns.
7. Add revalidation logic for stale websites, owners, and emails.

Until those improvements are implemented, the two agent runbooks are the operational source of truth for producing and qualifying lawyer leads.
