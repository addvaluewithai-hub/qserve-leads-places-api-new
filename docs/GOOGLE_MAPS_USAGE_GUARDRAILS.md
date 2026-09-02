# Google Maps Usage Guardrails

Status: **production safety note**

Last reviewed: **2026-09-02**

This is an engineering guardrail, not legal advice.

## Why this file exists

Google Maps Platform terms, Service Specific Terms, product policies, SKU pricing, and the customer's actual billing-account agreement can change.

Do not assume that something being technically available through an API automatically means every downstream lead-generation, storage, enrichment, export, or outreach use is permitted.

Before a live production discovery run, the operator must review the then-current Google Maps Platform terms/policies and the agreement that applies to the actual account/project.

## V2 engineering rule

The lawyer V2 path uses Text Search Enterprise non-ID fields transiently during one request-processing step for:

- exact-ZIP screening,
- business-status screening,
- rating/review-count screening,
- obtaining a website seed for an immediate public-web crawl.

The website seed is passed directly to Crawl4AI.

Crawl4AI then independently visits the public website and records our public-web evidence:

```text
final URL
registrable domain
homepage title
same-domain homepage/header/footer/nav links
crawl status
```

The V2 builder is intentionally designed **not** to write these Google non-ID fields into the new lead row/artifact as canonical CRM data:

```text
websiteUri
rating
userRatingCount
formattedAddress
location
addressComponents
```

The intended persistent Google identifier is:

```text
Place ID
```

Discovery screening provenance is stored as a boolean/timestamped event rather than by copying the exact Google screening values into the CRM.

## Important limitation

This transient-handling design reduces caching/provenance ambiguity. It does **not** prove that the intended production lead-generation use is permitted under the customer's actual Google Maps Platform agreement.

If the applicable terms/policies do not permit the intended use, replace the discovery adapter with a provider/license that does. The rest of the architecture can remain:

```text
ZIP manager
→ global business dedupe
→ public website crawl
→ Agent 2 gap validation
→ owner/direct-email enrichment
→ outreach suppression
```

## Workflow guard

The live GitHub workflow requires an explicit input:

```text
ack_google_maps_terms_review = true
```

Without that acknowledgement, the workflow exits before making live Google discovery requests.

This acknowledgement means only that the operator reviewed the applicable terms. It is not a legal/compliance determination by the code.

## Billing guard

The repository currently uses an internal lawyer-discovery ceiling of:

```text
900 Text Search Enterprise requests / month
```

The repository writes its own successful request events to:

```text
api_usage_ledger
```

This ledger is a safety mechanism, not authoritative billing data. It cannot see:

- requests made by other repositories,
- requests made manually,
- other applications using the same project/billing account,
- changes to Google's pricing/free usage caps.

Google Cloud Billing remains authoritative.

## No live work on push

Production Google discovery must remain manual-dispatch only.

Normal code/documentation pushes must not create live Google discovery requests, Crawl4AI campaign runs, outreach, or D1 campaign writes.

## Grounding Lite

Maps Grounding Lite was useful during experimentation, but it is not part of the V2 production lawyer path.

Do not reintroduce programmatic extraction of generated Grounding output into the production lead pipeline without a fresh terms/policy review and a clear product reason.

## Data provenance rule

For every persistent field, know its source.

Examples:

```text
Place ID                         → Google external identifier
public final URL/domain/title    → Crawl4AI/public website
homepage internal links          → Crawl4AI/public website
service-gap evidence             → Agent 2/public website validation
owner/direct public email        → public evidence recorded by Agent 2
contacted/suppressed state        → our outreach workflow
```

Avoid silently mixing transient provider data with independently observed public-web data.
