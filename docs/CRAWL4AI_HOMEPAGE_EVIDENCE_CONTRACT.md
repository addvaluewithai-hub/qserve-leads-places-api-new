# Crawl4AI Homepage Evidence Contract

Status: production contract

## Purpose

Crawl4AI is an Agent 1 evidence collector, not a validator.

For each accepted new business it must:

```text
open homepage only
→ render the public page
→ observe final public URL/domain/title
→ collect visible same-domain PAGE links from the rendered homepage
→ stop
```

The collected links may come from header, navigation, footer, cards, buttons, or body content. Agent 1 must not decide which legal services matter.

## Agent 1 filtering

Persist page-like links only.

Exclude obvious non-page targets such as:

```text
images
fonts
CSS/JS
media files
archives
PDFs
WordPress upload assets
```

Normalize/dedupe URLs and keep one short useful anchor per URL.

Agent 1 must NOT:

```text
deep crawl
follow collected links recursively
classify service architecture
declare a service gap
find owners/emails
```

Raw public-web evidence remains in `homepage_link_evidence`.

## Agent 2 first-pass batch

For new-production leads, Agent 2 should not start by opening websites one by one.

Normal first pass:

```text
20 Ready-for-Validation new-production leads
→ read existing Crawl4AI homepage evidence
→ render compact path + short-anchor view
→ omit asset/date-blog/obvious utility noise from the first-pass view
→ identify obviously mature separate-page sites
→ deep-check only promising/ambiguous leads
```

Compact display example:

```json
{
  "domain": "example.com",
  "page_link_count": 18,
  "architecture_signal_count": 6,
  "screen_hint": "likely_mature",
  "links": [
    ["/car-accidents", "Car Accidents"],
    ["/truck-accidents", "Truck Accidents"],
    ["/wrongful-death", "Wrongful Death"]
  ]
}
```

Do not repeat homepage URL, final URL, crawl timestamp, or full crawl metadata on every displayed link.

## Screen hints

`screen_hint` is only a triage heuristic:

```text
likely_mature
candidate_deep_check
review_links
crawl_review
```

It is never a final qualification decision.

A lead can only be finally disqualified/qualified under Agent 2 rules after the evidence is sufficient. Absence still requires an independent website double-check.

## Batch-size rule

Start with 20 leads per compact pre-screen batch.

Increase toward 30 only after real batches show that:

```text
context remains compact
no meaningful architecture signals are being hidden
false-positive/false-negative triage remains low
```

The objective is not to maximize batch size. The objective is to minimize website opens while preserving reliable qualification decisions.
