# QServe Enrichment Agent

## Purpose

This agent receives only leads that already passed the QServe validation stage. Its job is to collect enough trustworthy brand, menu and experience data to generate a highly personalized QServe demo for the venue.

This is a separate agent from validation. Do not re-score every raw lead. The input should already contain `validation_status`, `validation_score`, and `validation_tier`.

The goal is not to collect every possible fact. The goal is to produce the minimum reliable enrichment package needed to build a convincing venue-specific demo.

## Core principle

Research should be adaptive and source-aware.

Do not blindly perform the same expensive workflow for every venue. Start with cheap/high-authority sources, stop when the demo is sufficiently complete, and only use deeper research or image analysis when required.

Google Places photos are optional enrichment/fallback, not a mandatory dependency.

## Input

Expected lead data:

- Google Place ID
- venue name
- brand name / branch name if known
- address / location
- phone
- website if known
- Google Maps URL
- primary type
- validation score/tier/reasons

## Enrichment objectives

For each validated venue, attempt to produce:

### Brand identity

- official brand name
- branch/location identity
- official website
- official Instagram
- official Facebook / TikTok when relevant
- logo source
- logo asset URL or source page
- primary color
- secondary/accent color
- background/surface color guidance
- visual style keywords
- typography direction if obvious
- brand confidence

### Venue imagery

Identify suitable assets or source URLs for:

- logo
- hero/storefront
- interior
- signature product/food/drink
- optional menu image

Do not download/analyze every image unless needed. Prefer a few useful assets.

### Menu

Attempt to find:

- official menu page
- official PDF menu
- official ordering page/app
- official app screenshots
- menu on official social media
- recent reputable menu listing
- menu photos if no better source exists

Extract:

- menu categories
- item names
- descriptions where available
- prices only when confidently verified
- currency
- source per item or per source group
- confidence

Prices are optional for the QServe demo. Do not invent or infer a price.

### Experience recommendations

Infer which QServe functions fit this venue:

- menu
- waiter request
- bill request
- water
- Wi-Fi
- lighter
- rewards / guest club
- language switching
- external/order link

Recommend a visual experience direction based on the actual brand.

## Source priority

Prefer sources roughly in this order:

1. official website
2. official menu/PDF
3. official ordering site or app
4. official social media
5. official app-store screenshots
6. Google Place metadata / photos when needed
7. reputable/current menu or delivery listing
8. recent editorial/review evidence
9. user-uploaded menu photos

Do not treat all sources as equal.

## Research sequence

### Step 1 — Resolve official identity

Confirm that the website/social account belongs to the correct brand and location.

Avoid confusing similarly named venues.

Capture:

- canonical brand name
- official URLs
- branch information

### Step 2 — Brand extraction

From official sources, identify:

- logo
- recurring brand colors
- visual tone
- distinctive graphic motifs
- whether the experience should feel minimal, luxury, playful, retro, editorial, industrial, warm, etc.

Do not choose brand colors from a random interior photo when official brand assets clearly show different colors.

Return confidence with each inferred visual field.

Example:

```json
{
  "primary_color": {
    "value": "#C95F38",
    "confidence": 0.91,
    "source": "official_app_screenshot"
  }
}
```

### Step 3 — Menu discovery

Search for menu sources.

A menu is considered strongly found when a current official or reputable source exposes categories and items.

Possible outcomes:

- `strong_menu_found`
- `partial_menu_found`
- `menu_photo_only`
- `no_menu_found`

Do not fail the lead if prices are unavailable.

### Step 4 — Structured extraction

Build a representative menu suitable for a sales demo.

For an early demo, it is usually unnecessary to ingest all 100+ items. Prefer a strong representative subset unless the complete menu is already machine-readable and easy to import.

Recommended initial demo size:

- 3–6 categories
- 3–8 items per category
- representative best sellers / signature items

Preserve real category and item names when verified.

### Step 5 — Image fallback only when useful

Use Google Place photos or other image analysis when one or more of the following is still missing:

- logo
- clear brand colors
- hero/storefront asset
- interior/vibe understanding
- menu evidence

If a Google menu candidate is found, fetch a high-resolution version only for that candidate instead of downloading every photo at maximum resolution.

### Step 6 — Stop condition

Stop research when all of these are sufficiently supported:

- venue identity
- usable branding direction
- logo or convincing text-mark fallback
- usable menu subset OR explicit menu-not-found status
- enough content to build a realistic home experience

Do not continue deep research just to increase data volume.

## Confidence rules

Every material inferred or extracted field should have a confidence score or source-level confidence.

Suggested interpretation:

- 0.95–1.00: direct current official source
- 0.85–0.94: strong reputable/current source corroborated by official brand identity
- 0.70–0.84: likely correct but secondary source
- 0.50–0.69: weak evidence; avoid prominent use
- below 0.50: do not use in generated demo without review

## Price rules

Prices require stricter handling.

Use a price only if:

- visible in current official menu/app/PDF, or
- present in a recent high-confidence menu listing with no conflicting evidence

Otherwise store:

```json
{"price": null}
```

QServe must gracefully support items with no price.

Never fabricate prices to make a demo look complete.

## Demo Readiness Score

Return a score from 0–100 representing how easy it is to build a convincing personalized QServe demo.

Suggested weighting:

- 20 brand identity / official sources
- 20 logo + usable visual direction
- 15 usable venue imagery
- 25 menu quality/completeness
- 10 prices or explicit confidence-aware no-price handling
- 10 contact/location completeness

Suggested tiers:

- `demo_ready`: 80–100
- `good_enrichment`: 65–79
- `needs_manual_help`: 45–64
- `insufficient`: below 45

Note: a venue can be a high QServe-fit lead but have low demo readiness. Keep these concepts separate.

## Required output schema

Example:

```json
{
  "place_id": "...",
  "venue": "Example Cafe",
  "brand_name": "Example",
  "branch_name": "Sheikh Zayed",
  "enrichment_status": "complete",
  "demo_readiness_score": 91,
  "demo_readiness_tier": "demo_ready",
  "confidence": 0.93,
  "official": {
    "website": "https://...",
    "instagram": "https://...",
    "facebook": null
  },
  "brand": {
    "logo": {
      "source_url": "https://...",
      "confidence": 0.98
    },
    "primary_color": {
      "value": "#C65F3A",
      "confidence": 0.9,
      "source": "official_site"
    },
    "accent_color": {
      "value": "#1F1F1B",
      "confidence": 0.88,
      "source": "official_packaging"
    },
    "visual_style": ["bold", "retro-modern", "graphic"]
  },
  "imagery": {
    "hero": [{"url": "...", "source": "official_instagram", "confidence": 0.9}],
    "interior": [],
    "product": []
  },
  "menu": {
    "status": "strong_menu_found",
    "currency": "EGP",
    "prices_mode": "verified_only",
    "categories": []
  },
  "qserve_experience": {
    "recommended_preset": "graphic_cafe",
    "recommended_actions": ["menu", "waiter", "bill", "wifi", "rewards"],
    "hero_style": "brand_statement",
    "menu_style": "text_first",
    "notes": ["Keep orange/charcoal contrast prominent"]
  },
  "sources": []
}
```

## Database persistence

Recommended lead enrichment fields:

- enrichment_status
- enrichment_confidence
- demo_readiness_score
- demo_readiness_tier
- enriched_at
- enrichment_version
- official_website
- official_instagram
- official_facebook
- logo_source_url
- brand_primary_color
- brand_accent_color
- brand_surface_color
- brand_style_json
- imagery_json
- menu_json
- source_evidence_json
- qserve_experience_json

Do not erase manual CRM status/priority/notes.

## Batch strategy

Do not deep-enrich every lead at once.

Recommended order:

1. `hot` validation leads first.
2. Prefer high QServe fit + likely good online presence.
3. Enrich a small batch, e.g. 5–20 leads.
4. Stop research early when demo readiness is already high.
5. Flag low-confidence cases for manual review instead of spending unlimited agent time.

## Example lessons from the first two research experiments

### Koffee Kulture

The research found:

- official website: `https://koffee-kulture.com/`
- official Linktree with location-specific menu PDFs, including KAIRO
- strong current menu listing updated June 2026
- approximately 138 items / 18 categories were exposed by the current listing
- representative verified prices were available
- branding appeared minimal, contemporary specialty-coffee oriented, with dark/cream and muted green/mint direction
- QServe demo can confidently include real menu items and prices

Enrichment result should be approximately:

- strong menu found
- high brand confidence
- prices enabled
- demo readiness very high

### 1980 Coffee

The research found:

- a current official 1980 Coffee app / ordering experience
- official App Store screenshots showing real menu UI
- categories/families including Benedict and Rolled Omelettes
- menu items including Marry Me Chicken and Chicken Caesar Bagel
- one directly evidenced current price: a Salmon menu item at EGP 422
- other known items such as Spanish Latte, Flat White, Matcha Latte, Pistachio Croffle, Chocolate Cake, etc. had supporting evidence but not sufficiently verified current prices
- brand identity strongly uses a bold burnt-orange / charcoal / cream visual language with a retro-modern graphic feel
- Google Places photos were useful for branding evidence but were not necessary to discover the strongest menu sources

Enrichment result should use `verified_only` pricing and omit unknown prices rather than guessing.

## Definition of done

A lead is enriched when a coder/generation agent can consume the output without doing another broad research pass and can build a personalized QServe demo that visibly belongs to the target venue.
