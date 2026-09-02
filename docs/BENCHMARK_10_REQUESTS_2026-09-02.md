# Lawyer Discovery Benchmark — 10 Requests

Date: **2026-09-02**

This benchmark validates the low-cost architecture documented in `docs/FINAL_LEAD_ENGINE_ARCHITECTURE.md`.

## Test design

Ten generic lawyer Text Search requests were executed across ten non-Texas US markets:

- Phoenix, AZ
- Tampa, FL
- Charlotte, NC
- Columbus, OH
- Indianapolis, IN
- Nashville, TN
- Kansas City, MO
- Denver, CO
- Sacramento, CA
- Richmond, VA

Each request used:

```text
includedType = lawyer
strictTypeFiltering = true
minRating = 4.7
pageSize = 20
```

Text Search field mask:

```text
places.id
places.displayName
places.formattedAddress
places.businessStatus
```

No Place Details requests and no review text were used.

Every unique operational result was then queried through Maps Grounding Lite using business name + address and asking for official website + rating + review count. Grounding results were accepted automatically only when the returned Place ID matched the discovery Place ID.

## Results

```text
Text Search requests attempted:          10
Text Search requests successful:         10
Raw places returned:                    147
Unique Place IDs:                       147
Operational unique Place IDs:           147
Grounding calls:                        147
Grounding identity matches:             146
Website resolved + identity matched:    146
Unique website domains resolved:        146
Rating/review count parsed:             147
```

One result was conservatively excluded from the strict identity-matched working set because Grounding resolved the correct-looking firm/site but returned a different Place ID.

## Working-set yield

After website-domain dedupe:

```text
Minimum 10 reviews: 146 unique domains
Minimum 20 reviews: 141 unique domains
Minimum 50 reviews: 127 unique domains
```

The search request already required `minRating=4.7`.

Observed review-count distribution among the 147 grounded results:

```text
>= 10 reviews:   147
>= 20 reviews:   142
>= 50 reviews:   127
>= 100 reviews:   96
>= 200 reviews:   64
>= 500 reviews:   24
>= 1000 reviews:   5
```

Median returned review count was approximately **174**.

## Projection to 1,000 initial working law-firm domains

Using the measured yield:

```text
>= 10 reviews → ~69 Text Search requests
>= 20 reviews → ~71 Text Search requests
>= 50 reviews → ~79 Text Search requests
```

Projected Grounding calls:

```text
>= 10 reviews → ~1,007
>= 20 reviews → ~1,043
>= 50 reviews → ~1,158
```

These projections are approximately linear and production should include a safety margin for overlapping firms, repeated domains and market saturation.

## Cost implication

As validated on 2026-09-02:

- Places API Text Search Pro has a 5,000-request monthly free cap.
- Maps Grounding Lite has a 10,000-request monthly free cap.

A roughly 71-search / 1,043-grounding-call build for 1,000 initial working law-firm domains therefore fits comfortably inside those per-SKU monthly free caps if they have not already been consumed elsewhere in the billing account.

## Decision

Use **20 reviews** as the default initial working-set threshold for the first 1,000-lawyer build:

```text
rating >= 4.7
review count >= 20
OPERATIONAL
Grounding Place ID identity match
official website resolved
unique website domain
```

The resulting websites then move to homepage-only Crawl4AI and service-gap verification.
