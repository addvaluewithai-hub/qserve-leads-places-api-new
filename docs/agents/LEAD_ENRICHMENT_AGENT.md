# QServe Lead Enrichment Agent

## Purpose

This is the second agent in the QServe prospecting pipeline. It must run **only after validation** and only for leads/brands marked `accepted` (normally the canonical brand record, not every branch sibling).

Its job is to collect enough trustworthy brand/menu/business context to let QServe generate a personalized sales demo that feels genuinely made for the prospect.

The agent is not trying to create a perfect production database. It is trying to create a **high-confidence demo package** with explicit evidence, confidence, and gaps.

## Input gate

Do not enrich raw leads directly.

Expected input:

```json
{
  "lead_id": "google_place_id",
  "validation_status": "accepted",
  "fit_score": 84,
  "demo_readiness_hint": 78,
  "brand_key": "example-brand",
  "canonical_lead_id": "google_place_id",
  "venue_model": "table_service | hybrid | counter_service",
  "name": "Brand / venue name",
  "website": "https://...",
  "phone": "...",
  "google_maps_url": "...",
  "address": "..."
}
```

Skip `rejected` and `brand_sibling` records unless specifically instructed to research a branch-specific menu/identity.

Never modify the human CRM fields `status`, `priority`, or `notes`.

## Core output

Produce one structured enrichment record per canonical prospect.

```json
{
  "lead_id": "...",
  "brand_key": "...",
  "enrichment_status": "strong | partial | insufficient",
  "overall_confidence": 0.0,
  "demo_ready": true,
  "brand": {},
  "business": {},
  "menu": {},
  "media": {},
  "experience_recommendation": {},
  "sources": [],
  "gaps": [],
  "enriched_at": "ISO-8601",
  "enrichment_version": "qserve-enrichment-v1"
}
```

Persist enrichment separately from the raw Places fields and separately from human CRM state. Prefer a versioned `lead_enrichments` record/table or JSON column so later runs can be compared rather than silently overwriting provenance.

## Source priority

Research in this order. Stop early when evidence is already strong.

### Tier 1 — official first-party sources

1. Official website.
2. Official menu page or PDF.
3. Official ordering site/app.
4. Official Linktree / bio link hub.
5. Official Instagram/Facebook/TikTok pages.
6. Official App Store / Google Play listing and screenshots.

### Tier 2 — strong commercial sources

7. Delivery/ordering platforms such as Talabat when clearly matched to the same branch/brand.
8. Current menu directories with an explicit recent update date.

### Tier 3 — supporting evidence

9. Reputable editorial articles.
10. Search-result snippets / review platforms for corroboration.

### Fallback only — Google Places photos

Google Places photos are useful but should **not** be a default dependency.

Use them only when one of these important gaps remains after normal web research:

- no usable logo/wordmark,
- unclear brand palette/style,
- no hero/interior/product imagery,
- no menu/menu-board evidence.

Do not download ten Google photos for every accepted lead. If needed, retrieve a small sample, classify it, and fetch a higher-resolution version only for a promising menu/branding candidate. Preserve required attribution metadata. Treat Google imagery as research/fallback material, not as an owned asset.

## Research process

### 1. Resolve the official brand identity

Start from the Places website if present, then search intelligently.

Useful queries:

```text
"<brand>" official Egypt
"<brand>" Instagram
"<brand>" menu
site:<official-domain> menu
site:<official-domain> pdf
"<brand>" order online
"<brand>" Linktree
```

Confirm that each page belongs to the same Egyptian brand/location before using it.

Collect:

- official brand name and preferred capitalization,
- official website,
- public social handles,
- ordering/menu URLs,
- public phone/WhatsApp/business email if available,
- known branches/locations where useful.

### 2. Build the brand profile

Collect or infer:

```json
{
  "name": "Koffee Kulture",
  "logo": {
    "url": "...",
    "source_url": "...",
    "confidence": 0.98
  },
  "wordmark": {},
  "palette": {
    "primary": "#...",
    "secondary": "#...",
    "surface": "#...",
    "confidence": 0.0,
    "status": "verified | inferred"
  },
  "visual_style": ["editorial", "warm", "minimal"],
  "tone": ["casual", "premium"],
  "typography_direction": "geometric sans / editorial serif / etc",
  "tagline": {
    "value": "...",
    "status": "verified | absent"
  }
}
```

Color extraction rules:

- Prefer colors repeated on official logo/site/app/packaging.
- Do not treat random interior wall, food, or mall colors as brand colors.
- It is acceptable to return qualitative colors (`burnt orange`, `charcoal`, `cream`) if exact hex values cannot be responsibly verified.
- If converting to hex for a demo, mark it `inferred` and preserve the visual source.

### 3. Find and structure the menu

The menu is valuable, but **prices are optional** for the QServe sales demo.

Search source priority:

```text
official menu HTML/PDF
→ official ordering app/site
→ official social menu post/highlight
→ current delivery listing
→ recent menu directory
→ menu photo
→ review/editorial evidence
```

Menu output:

```json
{
  "status": "full | strong_partial | partial | not_found",
  "currency": "EGP",
  "prices_policy": "verified | partially_verified | omit",
  "categories": [
    {
      "name": "Hot Coffee",
      "source_url": "...",
      "confidence": 0.95,
      "items": [
        {
          "name": "Spanish Latte",
          "description": null,
          "price": 125,
          "currency": "EGP",
          "source_url": "...",
          "confidence": 0.92,
          "price_confidence": 0.92
        }
      ]
    }
  ]
}
```

Rules:

- `price` must be `null` when not confidently verified.
- Never infer a price from neighboring items or an old-looking screenshot.
- Track branch relevance: a menu from another branch can prove an item family exists but should not automatically prove the current branch price.
- Do not claim a full menu when only representative items were found.
- A representative 15-30 item menu is often enough for a sales demo. Full extraction is unnecessary unless the lead is highly qualified or the source is machine-readable.

### 4. Collect demo-safe media references

Collect references for:

- logo/wordmark,
- one possible hero/brand visual,
- optional product imagery,
- optional interior image,
- optional menu screenshot/PDF.

For each asset save:

```json
{
  "role": "logo | hero | product | interior | menu_evidence",
  "url": "...",
  "source_url": "...",
  "source_type": "official_site | official_social | app_store | google_places | third_party",
  "confidence": 0.0,
  "usage_note": "official public brand asset / research-only / requires attribution"
}
```

Do not pretend third-party user photos are official brand assets. Prefer first-party imagery for personalized demos.

### 5. Infer the service model for QServe

Collect evidence for the guest journey:

```json
{
  "service_model": "table_service | hybrid | counter_service | unknown",
  "dwell_time_hint": "high | medium | low",
  "food_depth": "large | medium | small",
  "repeat_visit_potential": "high | medium | low",
  "multi_branch": true,
  "branch_count_hint": 3
}
```

These fields guide the demo composition.

Do not invent waiter service. If evidence only proves a specialty coffee shop with seating, mark `hybrid` or `counter_service` and let QServe emphasize menu/rewards/analytics rather than waiter/bill actions.

### 6. Recommend the personalized QServe experience

This is an important enrichment output. The coder/demo generator should not have to rediscover the creative direction.

Example:

```json
{
  "experience_recommendation": {
    "preset": "editorial | graphic | hospitality | lounge | minimal",
    "density": "airy | compact",
    "hero_style": "brand_statement | image | product_feature | minimal",
    "menu_layout": "editorial_list | visual_cards | compact_list",
    "price_display": "always | when_known | hidden",
    "image_strategy": "featured_only | item_images | brand_only | text_first",
    "recommended_actions": ["menu", "waiter", "bill", "water"],
    "primary_action": "menu",
    "rewards_emphasis": "high | medium | low",
    "language_recommendation": ["ar", "en"],
    "notes": "Why this composition fits the brand/service model"
  }
}
```

Recommended actions are **demo suggestions**, not claims about what the cafe currently offers. Never fabricate Wi-Fi credentials, reward percentages, policies, or operational promises from the prospect.

## Confidence model

Every important fact should have a source and confidence.

Suggested guidance:

- 0.95-1.00: current official first-party evidence.
- 0.85-0.94: strong/current commercial source, or multiple corroborating sources.
- 0.70-0.84: credible supporting evidence / inferred from strong visuals.
- 0.50-0.69: weak or possibly stale evidence; useful only as a hint.
- <0.50: do not use in the demo as factual content.

Also label facts as:

- `verified`
- `inferred`
- `demo_suggestion`
- `unknown`

This separation is mandatory.

## Stop conditions and cost control

The agent should stop when it has enough for a convincing demo, not when the entire internet has been exhausted.

A strong stopping point is:

- brand name confirmed,
- official logo/identity or clear wordmark direction,
- useful palette/style evidence,
- at least one official digital property,
- meaningful menu structure with roughly 12+ verified items or several real categories,
- at least one good hero/brand media option or a strong text-first brand treatment,
- enough service-model evidence to choose QServe actions,
- sources and confidence recorded.

Suggested normal budget per accepted canonical brand:

- ~6-10 targeted searches,
- ~10-15 meaningful page opens,
- only escalate beyond that for very high-fit leads.

Do not repeatedly research the same brand sibling.

## Demo readiness

Compute `demo_ready` from evidence, not menu completeness alone.

### Strong / ready

Typical requirements:

- brand identity confidence >= 0.80,
- service/business identity confidence >= 0.80,
- menu status `full` or `strong_partial`, OR a smaller official menu adequate for a convincing demo,
- no critical identity conflict.

Prices can be missing.

### Partial / still demoable

A venue can still be `demo_ready=true` with:

- strong branding,
- reliable categories/items,
- incomplete prices.

Set `price_display=when_known` or `hidden`.

### Insufficient

Do not auto-generate a prospect-facing demo when:

- brand identity is ambiguous,
- menu appears to belong to a different brand,
- nearly all useful data is low-confidence,
- or the only available content would require fabrication.

## Known reference cases from the experiment

### Koffee Kulture

Research showed a very strong enrichment case:

- Official website: `https://koffee-kulture.com/`
- Official Linktree: `https://linktr.ee/Koffee.kulture`
- Official link hub exposes location-specific menu PDFs including a KAIRO menu.
- A current menu listing updated June 2026 exposed 138 items / 18 categories.
- Representative verified/high-confidence prices used in the experiment included:
  - Amerikano — EGP 90
  - Kappuccino — EGP 115
  - Flat White — EGP 100
  - KK Latte — EGP 120
  - Spanish Latte — EGP 125
  - Pistachio Latte — EGP 165
  - Sub Out — EGP 290
  - The Everything Club — EGP 350
  - Philly Cheese Steak Sandwich — EGP 400
  - Spicy Tunacado — EGP 310
  - Cream Cheese Bagel — EGP 170
  - Chicken Caesar-style Lunch Bagel — EGP 285
  - Chocolate Cake — EGP 175
  - San Sebastian Cheesecake — EGP 195
  - Passion Mojito — EGP 140
  - Peach Ice Tea — EGP 120
- Visual direction inferred from repeated brand evidence: modern/minimal specialty coffee, warm editorial feel; cream/off-white + dark charcoal/deep brown with a muted green/mint accent. Exact color values remain an inference unless extracted from a first-party asset.
- Recommended experience: airy/editorial, menu-first, strong loyalty/repeat-visit emphasis, use known prices.

### 1980 Coffee

Research showed a different, still useful partial-menu case:

- Google Places identified it as a strong coffee shop but did not expose an official website in the Places record.
- An official 1980 Coffee app exists on the Egypt App Store and is published through Prepit.
- Official app screenshots expose real menu UI and menu families such as `Benedict` and `Rolled Omelettes`.
- One directly visible current price was captured from an official app screenshot:
  - Salmon — EGP 422
- Other evidenced items/menu families included Spanish Latte, Caramel Latte, Flat White, Turkish Coffee, Matcha Latte, Caramel Frappe, Mojito, Salmon Benedict, Mushroom Toast, Marry Me Chicken, Chicken Caesar Bagel, Philly Cheese, Pistachio Croffle, Chocolate Cake, Tiramisu, and Tres Leches. Their prices should remain `null` unless separately verified.
- Visual direction from repeated brand imagery/app presentation: bold burnt-orange/red-orange + charcoal/black + warm cream; retro-modern, graphic, numeric `1980` identity. Treat exact hex values as inferred unless verified from an official asset.
- Recommended experience: bold/graphic, compact, strong typography, menu text-first or mixed, high-contrast action tiles; `price_display=when_known`.

These examples demonstrate the intended behavior: one brand can have a nearly complete priced menu while another remains highly demoable with only partial verified pricing.

## Success metric

The enrichment agent succeeds when a coder/demo-generation agent can consume its JSON and create a credible personalized QServe experience **without new manual research**, while clearly knowing which data is verified, inferred, optional, or missing.