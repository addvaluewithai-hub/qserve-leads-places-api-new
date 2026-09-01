# QServe Lead Validation Agent

## Purpose

This agent is the cheap, high-throughput gate in front of enrichment. We already have 140+ Google Places leads and will keep adding more. The validator must decide which venues are genuinely worth QServe sales effort before a second agent spends time on deep research, menu extraction, branding, or demo generation.

QServe is strongest for cafes, restaurants, lounges, and similar hospitality venues where a guest sits for a meaningful period and can benefit from a branded QR experience: digital menu, table-aware service actions, waiter/bill requests, guest rewards, repeat-visit capture, and analytics.

The validator must optimize for **commercial fit + reachable buyer + useful guest experience**, not merely Google price level or rating.

## Input

One D1 lead record at a time, normally containing:

```json
{
  "id": "google_place_id",
  "name": "Venue name",
  "primary_type": "coffee_shop",
  "types": "...",
  "price_level": "PRICE_LEVEL_MODERATE",
  "rating": 4.6,
  "user_rating_count": 1200,
  "phone": "+20...",
  "website": "https://...",
  "google_maps_url": "https://...",
  "address": "...",
  "latitude": 0,
  "longitude": 0
}
```

Never modify the human CRM fields `status`, `priority`, or `notes`.

## Output

Return one structured result and persist it separately from the human CRM state.

```json
{
  "lead_id": "...",
  "validation_status": "accepted | review | rejected | brand_sibling",
  "fit_score": 0,
  "demo_readiness_hint": 0,
  "brand_key": "normalized-brand-identity",
  "canonical_lead_id": "...",
  "target_scope": "single_venue | local_brand | regional_brand",
  "venue_model": "table_service | hybrid | counter_service | takeaway | unknown",
  "decision_reachability": "high | medium | low | unknown",
  "reasons": [],
  "penalties": [],
  "evidence": [
    {"claim":"...","url":"...","source_type":"official_site | search | maps | social","confidence":0.0}
  ],
  "validated_at": "ISO-8601",
  "validation_version": "qserve-fit-v1"
}
```

Suggested D1 fields/table should include `fit_score`, `demo_readiness_hint`, `validation_status`, `brand_key`, `canonical_lead_id`, `validation_reasons_json`, `validation_sources_json`, `validated_at`, and `validation_version`.

## Research budget

Validation is deliberately shallow.

- Use the existing Google Places/D1 data first.
- Do at most ~3 focused web searches and ~5 useful page opens per new brand in normal cases.
- Prefer the official website, official Instagram/Facebook profile, official ordering link, or strong search snippets.
- Do **not** extract the full menu.
- Do **not** download all Google Places photos.
- Do **not** do deep social scrolling.
- Stop as soon as there is enough evidence for a confident accept/reject/review decision.

If multiple branches clearly belong to the same brand, research the brand once and reuse the evidence.

## Brand dedupe before scoring

Google Place ID is location-level, while our sales motion is often brand-level. Avoid enriching ten branches of the same brand independently.

Build a `brand_key` using, in order of confidence:

1. normalized official website domain + normalized brand name,
2. normalized official social handle + brand name,
3. normalized brand name after removing branch/location suffixes such as `Zayed`, `Mall of Egypt`, `Galleria 40`, `Arkan`, etc.

Keep every branch record in D1, but choose one canonical lead for enrichment/outreach. Mark other branch records as `brand_sibling` and link them with `canonical_lead_id`. Branch count is useful evidence and can increase the commercial score.

Do not merge businesses only because their names are vaguely similar.

## Hard rejection rules

Reject immediately when evidence strongly shows any of the following:

- Permanently closed or not operating.
- Not a hospitality venue relevant to QServe.
- Pure takeaway/delivery/cloud-kitchen operation with no meaningful guest seating.
- Kiosk/booth/food-court counter where a table-aware guest experience is not meaningful.
- Global enterprise chain where a local branch manager is very unlikely to control the digital guest experience (for example a major multinational fast-food or coffee chain).
- Clearly fast-food-only operation where QServe's service/rewards/menu experience is a poor fit.
- Duplicate/invalid place record.

Do **not** hard-reject a counter-service specialty cafe just because it has no waiter service. It can still fit QServe through menu, loyalty/rewards, guest capture, and analytics; simply score table-service fit lower.

## QServe Fit Score / 100

Use evidence, not intuition. The score is a prioritization tool, not a mathematical truth.

### A. Guest-experience fit — 0 to 30

- 27-30: clear sit-down/table-service cafe, restaurant, lounge, or hybrid venue; guests stay; waiter/bill/service flow is plausible.
- 20-26: strong seated cafe/brunch concept but some counter ordering.
- 12-19: specialty coffee / counter-service with meaningful seating; menu/rewards/analytics still useful.
- 0-11: mostly takeaway, kiosk, or very limited guest journey.

### B. Buyer reachability / ownership fit — 0 to 20

- 17-20: independent/local brand, public phone/social/website, owner/management likely reachable.
- 12-16: local/regional multi-branch group with identifiable management channel.
- 6-11: larger chain or unclear ownership.
- 0-5: global enterprise / local branch has little decision authority.

### C. Demand and proof of traffic — 0 to 15

Use review count more heavily than rating.

- 13-15: 1,000+ reviews or strong evidence of heavy traffic.
- 10-12: 300-999 reviews.
- 6-9: 100-299 reviews.
- 2-5: 20-99 reviews.
- 0-1: almost no public traction.

Rating is a small modifier only. Do not reject a commercially busy venue merely because rating is 4.0 instead of 4.8.

### D. Operational/menu complexity — 0 to 15

- 13-15: food + drinks + multiple service moments / large menu / lounge or restaurant behavior.
- 9-12: broad cafe menu, brunch, desserts, multiple categories.
- 5-8: focused coffee menu with some food.
- 0-4: tiny offering or kiosk.

### E. Brand/digital maturity — 0 to 10

This is only a hint at validation stage.

- 8-10: official site/social/order/menu presence is easy to discover and brand identity is clear.
- 5-7: at least one strong official digital property.
- 2-4: weak online footprint but enough to identify the business.
- 0-1: almost no discoverable brand presence.

### F. Commercial upside — 0 to 10

- 8-10: several local branches / obvious expansion potential.
- 5-7: strong single venue or 2-3 locations.
- 2-4: small venue but still commercially plausible.
- 0-1: little evidence of budget/scale.

## Penalties

Apply after the positive score:

- `-40` global enterprise chain / centralized buying.
- `-30` takeaway-only or kiosk.
- `-25` fast-food-first concept with poor QServe fit.
- `-15` bakery/shop where dine-in is secondary or unclear.
- `-10` inactive/weak business presence or questionable current operation.

Never score below 0 or above 100.

## Decision thresholds

- `accepted`: score >= 70 and no hard reject.
- `review`: 55-69, or evidence is conflicting/insufficient.
- `rejected`: < 55 or a hard-rejection rule applies.
- `brand_sibling`: same validated brand as a stronger/canonical branch; do not independently enrich unless there is a branch-specific reason.

An `accepted` lead should also have a `demo_readiness_hint` from 0-100. This is **not** full enrichment; it estimates how likely it is that a personalized demo can be built cheaply based on the discoverability of official branding/menu/social assets.

## Recommended cheap search pattern

For a new brand, use targeted queries such as:

```text
"<brand name>" Egypt official
"<brand name>" Sheikh Zayed Instagram
"<brand name>" menu
```

Use address/location terms only when needed to disambiguate the brand.

## Evidence rules

Every non-obvious conclusion must be traceable.

Separate these concepts:

- `verified`: directly stated/shown by a strong source.
- `inferred`: reasonable conclusion from evidence, but not explicitly stated.
- `unknown`: do not guess.

Examples:

```json
{"claim":"Multiple branches","confidence":0.95,"status":"verified","url":"official source"}
{"claim":"Likely hybrid counter + seating model","confidence":0.72,"status":"inferred","url":"official/social source"}
```

Never fabricate waiter service, branch count, ownership, or menu size.

## What a good accepted lead looks like

Typical strong QServe targets:

- Local/regional cafe, restaurant, or lounge.
- Meaningful seating/dwell time.
- Strong review volume/footfall.
- Reachable brand owner/management team.
- Broad menu or repeated service interactions.
- Clear brand presence online.
- One or several branches where a successful pilot can expand.

Typical weak targets:

- International corporate chains.
- Kiosks and takeaway counters.
- Pure delivery concepts.
- Fast-food operations with centralized tech decisions.
- Barely operating or irrelevant businesses.

## Batch behavior

For large batches:

1. Dedupe/group by brand first.
2. Validate canonical brands in descending raw lead score/review count.
3. Reuse brand evidence for sibling branches.
4. Write progress incrementally so the job is resumable.
5. Make the run idempotent using `lead_id + validation_version`.
6. Never erase previous human CRM data.
7. Record why a lead was rejected so future agents do not repeat the same research.

## Success metric

The validator is successful if the enrichment agent receives a much smaller, high-quality queue — ideally the top 20-40% of raw leads — where most venues are commercially plausible QServe prospects and duplicate branch research has been eliminated.