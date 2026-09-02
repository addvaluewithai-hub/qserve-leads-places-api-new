# Final Lead Engine Architecture

Status: **current working architecture**

Last validated: **2026-09-02**

This document is the source of truth for the low-cost QServe lead engine architecture. It is intentionally separate from the README so the core design is not lost while experiments and campaigns evolve.

## Goal

Build large working sets of high-quality local-service businesses (starting with lawyers) with the lowest practical Google Maps Platform cost, then verify the actual website architecture ourselves.

For lawyers, the target is not a single niche such as Family Law. The discovery target is **good active law firms generally**. Service-page gaps are discovered later from the firm's own website.

## Final pipeline

```text
Google Places Text Search Pro
(minimal fields only)
        ↓
Place ID + business name + address + business status
        ↓
Maps Grounding Lite
(name + address → official website + rating + review count)
        ↓
Identity validation + domain dedupe
        ↓
High-rating / minimum-review working set
        ↓
Crawl4AI homepage load only
        ↓
Collect same-domain links visible on homepage/header/footer/nav
        ↓
ChatGPT / manual service-gap validation
        ↓
Qualified / Disqualified / Not Relevant / Needs Review
        ↓
Owner + direct public email enrichment
        ↓
CRM / D1
```

## 1. Google discovery: minimal Text Search Pro

Use **generic vertical discovery**, not niche-service discovery.

For lawyers:

```text
textQuery: "lawyer in <market>"
includedType: "lawyer"
strictTypeFiltering: true
minRating: 4.7
pageSize: 20
```

Recommended field mask:

```text
places.id
places.displayName
places.formattedAddress
places.businessStatus
```

Do **not** request these during discovery:

```text
rating
userRatingCount
websiteUri
phone
openingHours
reviews[]
```

Those fields are not required at this stage and would move discovery into more expensive SKUs.

### Why not IDs-only?

We tested Grounding Lite using only a Place ID in `search_places` on three known law firms. The MCP requests returned HTTP 200 but an empty `{}` result for all three.

Therefore the working design must retain at least enough human-readable identity to query Grounding Lite. **Business name + address** is sufficient and has been validated in live tests.

## 2. Maps Grounding Lite enrichment

For each unique Place ID, send a grounded query using the name and address, for example:

```text
Gibbins Law, PLLC, 1515 W SW Loop 323, Tyler, TX 75701 official website rating review count
```

Live tests on 2026-09-02 confirmed that Grounding Lite returned, in the generated summary:

- official website URL
- Google rating
- Google review count
- address
- the matching Place ID / Google Maps source

The official website is not a structured `websiteUri` field. It appears in the grounded summary when explicitly requested.

### Identity validation

Never trust the summary blindly.

For each Grounding response:

1. Compare the returned Place ID with the discovery Place ID.
2. Keep the Google Maps attribution/source from the grounding response.
3. Extract the non-Google official website URL from the summary.
4. Open/fetch that website independently.
5. Confirm the website identity matches the business before treating the domain as verified.

If the Place ID does not match, or no official website is confidently resolved, mark the lead `Needs Review` / unresolved rather than guessing.

## 3. Quality gate

The discovery request already uses a high `minRating` filter. Grounding Lite supplies the actual rating and review count so we can apply a stronger gate without fetching `reviews[]`.

Current benchmark defaults:

```text
minimum rating: 4.7
minimum review count: 20
business status: OPERATIONAL
verified official website: required
```

The minimum review threshold is configurable. Benchmarks should report yield at 10, 20 and 50 reviews so we can choose the best quality/volume tradeoff.

We do not need review text or review samples for this workflow.

## 4. Dedupe

Dedupe in two stages:

1. **Place ID** immediately after Google discovery.
2. **Verified website domain** after Grounding Lite enrichment.

Domain dedupe is important because a multi-office firm may have multiple Google Places listings but only one company/site opportunity.

## 5. Crawl4AI role

Crawl4AI is intentionally a dumb collector.

For each verified website it should:

1. Load the homepage once.
2. Render the page normally so header, nav and footer are present.
3. Collect all same-domain links exposed on that homepage.
4. Save destination URL + anchor text.
5. Stop.

It must **not**:

- deep crawl
- follow the collected links recursively
- classify service pages
- decide Qualified/Disqualified
- use an LLM to interpret the site

Primary outputs:

```text
homepage_links.csv
homepage_links.json
homepage_fetch_summary.json
homepage_links_summary.json
```

## 6. Service-gap validation

Lawyer discovery is generic. We do not pre-select Family Law, Probate, Estate Planning, Immigration, etc.

After homepage links are collected, review the firm's services and URL architecture.

Important qualification rule:

- `/practice-areas/`, `/services/`, or similar general pages are allowed.
- Dedicated pages for other services are allowed.
- Reject a specific service gap only when **that exact service** has its own dedicated internal page/URL.
- If no dedicated target-service link is visible from the homepage, manually double-check the site before declaring the gap Qualified.
- If the firm does not actually offer the service, mark it Not Relevant for that service rather than Qualified.

One firm can have multiple valid service gaps.

## 7. Cost model

Pricing changes over time, so always verify current Google Maps Platform pricing before financial reporting.

Validated 2026-09-02 pricing/free caps used for this design:

- Places API Text Search Pro: **5,000 free requests/month**; list price after the free cap starts at **$32 / 1,000 requests**.
- Maps Grounding Lite: **10,000 free requests/month**; list price after the free cap starts at **$7 / 1,000 requests**.

The architecture intentionally avoids Place Details Enterprise and `reviews[]` by default.

## 8. Scaling to 1,000 lawyer working leads

The unit we care about is not raw Google results. It is:

```text
unique law firm domain
+ identity matched
+ official website resolved
+ rating >= threshold
+ review count >= threshold
```

Use benchmarks to measure the yield per Text Search request.

If a 10-request benchmark produces `Q` unique high-quality working leads, estimate the discovery requests needed for 1,000 as:

```text
ceil(1000 / Q * 10)
```

Then add a safety margin for overlap, unresolved websites and market saturation.

### Geographic strategy

Do not restrict the 1,000-lead working set to Texas unless a campaign requires it.

Use many independent metro/city markets across the US. Prefer a broad spread of medium and large markets rather than repeatedly paginating one market. This reduces duplicate firms and creates a more diverse sales pipeline.

## 9. Storage / provenance

Keep Google Place ID as the stable Google identifier.

Grounding outputs should retain their Google Maps source/attribution as required by Google Maps Grounding Lite terms. Treat the resolved official website as a starting point for independent open-web verification; do not blindly treat generated summary text as canonical business data.

CRM-specific decisions, crawl evidence, qualification status, owner/email enrichment and outreach history are our own data and should live in D1.

## 10. Failure handling

Use conservative states:

```text
Resolved
Needs Review
Not Relevant
Disqualified
Qualified
```

Never convert missing evidence into a positive qualification.

Examples:

- Grounding returns the wrong Place ID → Needs Review.
- No website resolved → Needs Review / skip crawl.
- Homepage crawl fails → retry homepage once, then Needs Review.
- Service is not actually offered → Not Relevant for that service.
- Exact dedicated target-service page exists → Disqualified for that gap.
- Service is offered, no exact dedicated page found, double-check confirms absence → Qualified.

## Current decision

Until a better validated path is found, the default production architecture is:

```text
Minimal Text Search Pro
→ Maps Grounding Lite
→ verified website
→ homepage-only Crawl4AI
→ ChatGPT/manual validation
```

Place Details Enterprise is a fallback only, not part of the normal path.
