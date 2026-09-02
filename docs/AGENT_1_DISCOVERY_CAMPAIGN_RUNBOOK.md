# Agent 1 Runbook — ZIP Discovery, Global Dedupe, Campaign Build, Homepage Collection

Status: **production operating procedure — V2**

Last updated: **2026-09-02**

## Mission

Agent 1 creates the next working set of businesses and prepares them for Agent 2.

For lawyers, success means:

```text
requested NET-NEW unique law-firm business domains
+
public website successfully opened
+
homepage links collected
+
D1 status = Ready for Validation
+
qualified = 0
```

Agent 1 does **not** validate service gaps, find owner emails, or mark a lead Qualified.

---

## Read these first

1. `README.md`
2. `docs/FINAL_LEAD_ENGINE_ARCHITECTURE.md`
3. `docs/MARKET_COVERAGE_MANAGEMENT.md`
4. `docs/GOOGLE_MAPS_USAGE_GUARDRAILS.md`
5. this runbook

Production files:

```text
campaigns/lawyers-us.json
market_plans/lawyers-us-zips.json
scripts/zip_manager.py
scripts/build_next_1000_lawyers_zip.py
scripts/bootstrap_lawyers_us_campaign.py
scripts/mark_business_contacted.py
```

Grounding-era and metro-based scripts are historical experiments, not the V2 production path.

---

# 0. Historical bootstrap must exist

Before asking for another 1,000, the historical first 1,000 businesses must exist in the canonical D1 registry.

Bootstrap once:

```bash
python scripts/bootstrap_lawyers_us_campaign.py \
  --campaign lawyers-us \
  --input-dir <historical-first-1000-artifact>
```

The bootstrap makes zero Google calls.

The next-1,000 builder refuses to run when the expected historical seed is missing because it could not truthfully call new results `net-new`.

---

# 1. ZIP coverage is the discovery unit

Do not choose random cities and do not treat one city query as market coverage.

The static high-level plan is:

```text
market_plans/lawyers-us-zips.json
```

The dynamic source of truth is:

```text
zip_coverage
zip_run_history
```

The hierarchy is:

```text
state priority
→ preferred cities
→ ZIP codes
```

Generate/sync the ZIP universe:

```bash
python scripts/zip_manager.py sync --campaign lawyers-us
```

See status/next ZIPs:

```bash
python scripts/zip_manager.py status --campaign lawyers-us --next 50
python scripts/zip_manager.py next --campaign lawyers-us --next 50
```

Do not manually label a state `done`. State coverage is the aggregate of its ZIP rows.

---

# 2. Load GLOBAL exclusion sets

The business rule is global, not campaign-local.

Before a result can count as a new business, Agent 1 excludes:

```text
all existing canonical Place IDs
all existing registrable business domains
all globally suppressed/contacted business domains
all Place IDs/domains already accepted in the current run
```

A firm with multiple Google listings/offices but one registrable domain counts once.

Example:

```text
houston.examplelaw.com
and
austin.examplelaw.com
```

both collapse to:

```text
examplelaw.com
```

An already-known business may still have an existing campaign lifecycle, but it never counts toward the requested `next 1,000`.

A business already contacted is globally blocked from new outreach unless an explicit re-engagement state exists.

---

# 3. Text Search Enterprise by ZIP

For each eligible ZIP:

```text
textQuery = "lawyer in <ZIP>"
includedType = lawyer
strictTypeFiltering = true
minRating = 4.0
pageSize = 20
locationRestriction = rectangle around ZIP centroid
```

The rectangle improves recall but is not trusted as exact ZIP membership.

Required response fields are configured in `campaigns/lawyers-us.json` and include:

```text
Place ID
addressComponents
businessStatus
rating
userRatingCount
websiteUri
nextPageToken
```

## Exact geography rule

A result can only be processed for a ZIP when Google returns:

```text
addressComponents postal_code == target ZIP
```

A neighboring ZIP is ignored for this pass.

---

# 4. Quality screen

Current minimum screen:

```text
businessStatus == OPERATIONAL
rating >= 4.0
userRatingCount >= 20
websiteUri present
```

The Google non-ID values are screening inputs in the V2 pipeline.

Do **not** intentionally persist the exact Google:

```text
websiteUri
rating
userRatingCount
formattedAddress
location
addressComponents
```

as canonical lead data in the V2 working-set artifact/D1 row.

The Google Place ID is the intended persistent Google identifier.

Read `docs/GOOGLE_MAPS_USAGE_GUARDRAILS.md` before a live production run.

---

# 5. Solve the 20-result limit with same-ZIP pagination

Do not revisit a ZIP later just to repeat page 1.

For each ZIP:

1. request page 1,
2. inspect `nextPageToken`,
3. if page 1 is dense enough, request page 2 in the same processing pass,
4. request page 3 when appropriate,
5. record every page request and finish the ZIP state.

Default dense-ZIP trigger:

```text
page-1 raw results >= 20
AND
page-1 exact-ZIP results >= 5
AND
nextPageToken exists
```

Maximum:

```text
3 pages per ZIP
```

ZIP state after processing is one of:

```text
partial
covered
saturated
failed
```

`partial` means the overall target or API budget stopped the run before the ZIP was fully completed.

---

# 6. Immediate Crawl4AI handoff

For every quality-screened, non-duplicate candidate, pass the transient website seed directly to Crawl4AI.

Crawl4AI does:

```text
open homepage
→ render normal page
→ observe final public URL/domain/title
→ collect visible same-domain links
→ stop
```

Crawl4AI must not:

- deep crawl,
- recursively follow collected links,
- classify services,
- decide gaps,
- search for emails.

A candidate does not become a working business merely because a website seed exists. The crawler must reach a usable public site and produce a valid business domain.

Social/directory/profile sites such as Facebook, Avvo, Justia, FindLaw, Yelp, LinkedIn, etc. must not count as the law firm's official working website.

---

# 7. Persist PUBLIC-WEB evidence

Once Crawl4AI confirms the public site, persist:

```text
Place ID
public final URL
registrable business domain
homepage title
source ZIP
crawl status
homepage links
```

Primary tables:

```text
leads
lead_domains
campaign_leads
lead_discovery_screening
homepage_link_evidence
```

Initial campaign state:

```text
qualified = 0
status = Ready for Validation
qualification_reason = working_set_ready_for_validation
```

Do not mark a Google-quality business Qualified.

---

# 8. Global outreach suppression

Discovery dedupe and outreach suppression are separate.

Discovery rule:

```text
known business
→ not net-new
```

Outreach rule:

```text
actually contacted once
→ global suppression
```

After outreach is actually sent, update the existing lead:

```bash
python scripts/mark_business_contacted.py \
  --lead-id <PLACE_ID> \
  --campaign lawyers-us \
  --email <DIRECT_OWNER_EMAIL> \
  --status Contacted
```

Do not create a new campaign copy to contact the same business again.

Explicit re-engagement is an update to the existing business lifecycle.

---

# 9. API usage budget

Current internal safety ceiling:

```text
900 Text Search Enterprise requests/month
```

Every successful page request made by this repository is written to:

```text
api_usage_ledger
```

The builder stops partially when its internal budget is exhausted.

Important: this ledger does not know about other Google API usage outside this repo. Google Cloud Billing is authoritative.

The production GitHub workflow is manual-dispatch only and requires:

```text
ack_google_maps_terms_review = true
```

---

# 10. Failure safety

Only one V2 lawyer discovery run should operate at a time.

The GitHub workflow uses a concurrency group.

If the process dies during a ZIP:

```text
status = in_progress
```

is later recovered to a retryable failure state by `zip_manager.py`.

New accepted businesses are persisted incrementally.

If the run ends at:

```text
620 / 1000
```

those 620 remain canonical. A later run excludes them and continues toward the remaining target.

---

# 11. Handoff to Agent 2

Agent 1 is finished for a lead when Agent 2 has:

```text
campaign ID
Place ID
public website
registrable domain
homepage title
source ZIP
homepage crawl status
homepage links with URL + anchor text
status = Ready for Validation
```

Permanent Google rating/review values are not required by Agent 2.

Agent 2 owns:

```text
service-gap validation
owner/decision-maker identification
direct public owner email
final qualification
```

---

## Agent 1 must NEVER

- qualify a lead,
- declare a gap,
- deep crawl,
- use Grounding Lite in the V2 normal path,
- count a neighboring ZIP result,
- count a duplicate Place ID/domain,
- count a known/contacted business as new,
- accept Facebook/Avvo/Justia/FindLaw/etc. as the firm's official website,
- intentionally persist exact Google websiteUri/rating/review-count values into the V2 lead row,
- exceed the configured request budget silently,
- run live production discovery automatically on code push,
- run two next-1,000 discovery jobs concurrently.

---

## Agent 1 checklist

```text
[ ] Historical first 1,000 are bootstrapped
[ ] Google Maps usage/terms reviewed for the actual account/use
[ ] ZIP universe synced
[ ] Global Place-ID/domain/suppression sets loaded
[ ] Search minRating = 4.0
[ ] Exact returned postal_code matches target ZIP
[ ] Rating >= 4.0
[ ] Review count >= 20
[ ] OPERATIONAL
[ ] Website seed exists
[ ] Same-ZIP pagination handled before marking coverage
[ ] Website opened by Crawl4AI
[ ] Public final business domain is not a directory/social profile
[ ] Registrable domain globally deduped
[ ] Public homepage links persisted
[ ] Campaign state = Ready for Validation
[ ] qualified = 0
[ ] Request ledger updated
[ ] ZIP status/history updated
[ ] Agent 2 handoff ready
```
