# Final Lead Engine Architecture — V2 ZIP Coverage

Status: **current production architecture**

Last updated: **2026-09-02**

This document is the source of truth for the lawyer lead engine after the ZIP-scaling redesign.

## Goal

Build batches of **net-new law-firm businesses**, not raw Google listings.

The operating target is usually:

```text
1,000 net-new unique business domains
```

A business is globally deduped. If it has already been discovered, it is not counted as a new business. If it has already been contacted, it is globally suppressed from future outreach unless an explicit re-engagement state is created.

## Production pipeline

```text
ZIP coverage queue
state → preferred city → ZIP
        ↓
Google Places Text Search Enterprise
one ZIP at a time
        ↓
transient screening only:
Place ID
business status
rating
review count
websiteUri
postal address components
        ↓
exact postal_code == target ZIP
rating >= 4.0
reviews >= 20
OPERATIONAL
website seed present
        ↓
global Place-ID/domain/suppression exclusion
        ↓
Crawl4AI immediately opens the website seed
homepage only
        ↓
persist PUBLIC-WEB evidence:
final URL
registrable business domain
homepage title
homepage links
        ↓
D1 status = Ready for Validation
qualified = 0
        ↓
Agent 2:
gap validation
→ owner/decision maker
→ direct public owner email
→ Qualified
        ↓
actual outreach
        ↓
global outreach suppression
```

Grounding Lite is **not part of the V2 production path**.

---

## 1. ZIP is the coverage unit

Do not use a whole city as one search request.

The static high-level plan is:

```text
market_plans/lawyers-us-zips.json
```

The dynamic coverage source of truth is:

```text
D1.zip_coverage
D1.zip_run_history
```

ZIPs are generated from the `pgeocode`/GeoNames US postal-code dataset. The plan controls state priority and preferred cities; D1 records what has actually been searched.

Current first-priority phase starts with:

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

Texas preferred cities are ordered before the rest of the Texas ZIP universe.

A state is never represented by one `done` flag. Coverage is aggregated from its ZIP rows.

---

## 2. Google Text Search Enterprise request

Current lawyer request:

```text
textQuery = "lawyer in <ZIP>"
includedType = "lawyer"
strictTypeFiltering = true
minRating = 4.0
pageSize = 20
locationRestriction = rectangle around ZIP centroid
```

The ZIP rectangle is a search-recall aid. It is **not** the final geographic test.

The final geographic gate is:

```text
places.addressComponents postal_code == target ZIP
```

If Google returns a business from a neighboring ZIP, it is ignored for that ZIP.

### Field mask

The production field mask is:

```text
places.id
places.displayName
places.formattedAddress
places.addressComponents
places.businessStatus
places.location
places.rating
places.userRatingCount
places.websiteUri
nextPageToken
```

The highest fields in that mask place the request in **Text Search Enterprise**.

We intentionally do not request:

```text
reviews[]
generative summaries
review summaries
Atmosphere fields
```

---

## 3. Rating/review gate

Current business rule:

```text
minimum rating = 4.0
minimum review count = 20
business status = OPERATIONAL
```

The request-side `minRating` is exactly `4.0`.

The exact values are also checked in-memory before the candidate is passed to Crawl4AI.

The V2 data model does not require retaining the exact Google rating/review-count values as permanent CRM data. They are screening inputs.

---

## 4. Pagination: solve the 20-result problem inside the ZIP

Text Search returns at most 20 results per page and currently supports up to 60 results across pages.

The V2 strategy:

1. Search page 1 for a ZIP.
2. Count raw results and results whose returned postal code matches the ZIP.
3. If page 1 is dense enough and `nextPageToken` exists, fetch page 2.
4. Continue to page 3 when appropriate.
5. Do the pages in the same run while the token is valid.
6. Record the number of pages searched in `zip_coverage`.

Default pagination trigger:

```text
page 1 raw results >= 20
AND
page 1 exact-ZIP results >= 5
```

Default maximum:

```text
3 pages per ZIP
```

This replaces the old behavior where a metro could repeatedly return the same first 20 results on future passes.

ZIP status:

```text
queued
in_progress
partial
covered
saturated
failed
cooling
```

`partial` is used when the overall 1,000 target or request budget stops the run before the ZIP is fully processed.

---

## 5. Google data is transient; Crawl4AI creates the stored website evidence

For the V2 production code, Google non-ID fields are used during the request-processing step to:

- apply the quality gate,
- confirm the result belongs to the target ZIP,
- obtain a website seed.

The website seed is passed immediately to Crawl4AI.

Crawl4AI then independently loads the public website and records:

```text
final URL
registrable domain
homepage title
same-domain homepage/header/footer/nav links
HTTP/crawl status
```

The production builder does **not** intentionally persist these Google fields as lead data:

```text
websiteUri
rating
userRatingCount
formattedAddress
location
```

The Google Place ID is retained as the stable external identifier.

This handling reduces caching/provenance ambiguity, but it does **not by itself establish that every lead-generation use is permitted by the customer's Google Maps Platform agreement**. See `docs/GOOGLE_MAPS_USAGE_GUARDRAILS.md`.

---

## 6. Domain identity and global dedupe

Dedupe is global, not campaign-local.

Before a candidate can count toward a new 1,000 batch, exclude it when any of these are true:

```text
Place ID already exists in canonical leads
registrable website domain already exists
domain is globally outreach-suppressed
same Place ID/domain already appeared in the current run
```

For new V2 discovery, registrable-domain dedupe collapses subdomains such as:

```text
houston.examplelaw.com
austin.examplelaw.com
```

to the business domain:

```text
examplelaw.com
```

Multi-office Google listings therefore do not count as multiple sales opportunities.

The historical first 1,000 should be bootstrapped before running the next-1,000 builder so the global exclusion registry is complete.

---

## 7. Crawl4AI remains a dumb collector

Crawl4AI must:

1. load the homepage,
2. render it,
3. capture public final URL/title,
4. collect same-domain links visible from the homepage,
5. retry once if necessary,
6. stop.

It must not:

- deep crawl,
- recursively follow service links,
- classify services,
- decide gaps,
- find emails,
- make qualification decisions.

The V2 builder performs Crawl4AI immediately after transient discovery screening, so a separate website-URL staging table is not required.

---

## 8. Agent 2 qualification

Agent 2 receives public-web homepage evidence.

For each potential service:

```text
service genuinely offered
+
no dedicated exact-service page after mandatory website double-check
=
Gap Confirmed
```

A general `/services` or `/practice-areas` page does not automatically disqualify a gap.

A dedicated page for another service does not disqualify the target service.

If the service is not genuinely offered:

```text
Not Relevant
```

If evidence is ambiguous:

```text
Needs Review
```

Only after at least one gap is confirmed does Agent 2 research the owner/decision maker and direct public email.

Final qualification:

```text
confirmed service gap
+
owner/decision maker identified
+
direct public email for that exact person
=
Qualified
```

Generic/reception/intake emails are not accepted.

---

## 9. Outreach suppression

Qualification is not the same as contact.

When actual outreach occurs, write a global suppression record:

```text
outreach_suppression
```

Default rule:

```text
contacted once
→ suppressed from future outreach/discovery-as-new-business
```

Possible contact states include:

```text
Contacted
Replied
Interested
Not Interested
Do Not Contact
Bounced
Re-engage Later
```

An explicit `reengage_after` can be recorded for future follow-up, but re-engagement should operate on the existing canonical lead, not rediscover the business as a new lead.

---

## 10. D1 model

Core canonical/campaign tables:

```text
leads
lead_domains
campaigns
campaign_runs
campaign_leads
```

ZIP management:

```text
zip_coverage
zip_run_history
api_usage_ledger
```

Discovery/public-web evidence:

```text
lead_discovery_screening
homepage_link_evidence
```

Validation/contact evidence:

```text
service_gap_evidence
lead_contacts
```

Global outreach protection:

```text
outreach_suppression
```

Older `market_coverage`, `market_run_history`, and Grounding-era scripts remain only for historical audit/reference.

---

## 11. Request budget

Current Google pricing must always be checked before a live production run.

As of the architecture validation date, Text Search Enterprise has a 1,000-request monthly free usage cap and each page request is a request event.

The repository uses an internal safety budget:

```text
900 Text Search Enterprise requests/month
```

for `lawyers-us`, leaving headroom.

The local `api_usage_ledger` tracks requests made by this repository. It is **not authoritative billing data** and cannot see unrelated usage on the same Google billing account.

A run stops partially rather than silently exceeding its internal budget.

---

## 12. Concurrency and failure handling

Only one lawyer ZIP-discovery workflow should run at a time.

GitHub Actions uses a concurrency group:

```text
lawyers-us-zip-discovery
```

If a process crashes while a ZIP is `in_progress`, `zip_manager.py` recovers stale rows after a timeout and moves them to retryable failure state.

Accepted leads are written incrementally. If a run stops at 600/1,000, those 600 stay canonical and the next run excludes them automatically.

---

## 13. Current production command

After historical bootstrap:

```bash
python scripts/build_next_1000_lawyers_zip.py \
  --campaign lawyers-us \
  --target 1000 \
  --max-zips 5000 \
  --max-search-requests 900
```

Coverage status:

```bash
python scripts/zip_manager.py status --campaign lawyers-us --next 50
```

Global contact suppression after outreach:

```bash
python scripts/mark_business_contacted.py \
  --lead-id <PLACE_ID> \
  --campaign lawyers-us \
  --email owner@example.com \
  --status Contacted
```

---

## Current decision

The normal lawyer production path is:

```text
ZIP queue
→ Text Search Enterprise transient screening
→ immediate homepage Crawl4AI
→ global dedupe
→ D1 public-web evidence
→ Agent 2 gap/contact qualification
→ global outreach suppression
```

Grounding Lite and metro-based discovery are not part of the V2 production path.
