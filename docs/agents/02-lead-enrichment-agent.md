# QServe Lead Enrichment Agent

## Goal

Take only leads that already passed QServe validation and collect enough real-world brand/menu information to build a convincing personalized QServe demo for that venue.

This is a separate agent from validation. It should not waste time researching poor-fit leads.

The target outcome is not "collect everything on the internet." The target outcome is: **collect the minimum reliable evidence needed to generate a high-fidelity venue-specific QServe experience.**

## Inputs

A validated lead should include at least:

- Google Place ID
- venue name
- address / branch
- primary type
- phone
- website if known
- Google Maps URL
- rating / reviews
- validation status
- QServe Fit Score
- venue-model classification

## Required output

Return a structured enrichment record with evidence and confidence.

Example:

```json
{
  "place_id": "...",
  "venue": "Example Cafe",
  "research_status": "demo_ready",
  "demo_readiness_score": 91,
  "brand": {
    "logo": {
      "url": "...",
      "source": "official_website",
      "confidence": 0.98
    },
    "primary_color": {
      "value": "#D45A2A",
      "source": "official_site_and_packaging",
      "confidence": 0.91
    },
    "secondary_color": {
      "value": "#1C1C1A",
      "confidence": 0.88
    },
    "visual_direction": ["bold", "retro-modern", "graphic"]
  },
  "menu": {
    "status": "strong_menu_found",
    "currency": "EGP",
    "prices_supported": true,
    "categories": []
  },
  "social": {
    "instagram": "...",
    "facebook": "..."
  },
  "assets": {
    "hero_candidates": [],
    "interior_candidates": [],
    "food_candidates": []
  },
  "sources": [],
  "missing": []
}
```

## Core research strategy

Research adaptively. Do not force every venue through the same expensive flow.

Recommended order:

1. Official website
2. Official social profiles / Linktree
3. Official menu page / PDF
4. Official ordering app or ordering website
5. App Store / Play Store screenshots if the official app contains menu UI
6. Delivery/menu platforms when current and clearly matched to the venue/branch
7. Search results / editorial / recent posts
8. Google Places photos only when useful as fallback or supplementary evidence

Google Places photos are useful but should not be a mandatory first step. In the experiments, the agent was able to obtain most important branding/menu evidence from ordinary web research without depending on Google photo analysis.

## Branding enrichment

Collect:

- official logo or strongest logo candidate
- logo type: wordmark / monogram / icon / combination
- primary brand color
- secondary/accent color
- surface/background direction
- typography direction if reasonably inferable
- overall visual personality / keywords
- hero image candidates
- storefront/interior image candidates
- product/food image candidates

Possible visual personality tags:

- minimal
- premium
- warm
- editorial
- playful
- bold
- retro-modern
- industrial
- luxury
- cozy
- specialty-coffee
- nightlife/lounge
- contemporary

### Branding confidence

Never pretend a sampled image color is definitely an official brand color.

For each extracted attribute, keep:

- value
- source
- confidence 0–1
- optional note

Example:

```json
{
  "primary_color": {
    "value": "burnt orange",
    "confidence": 0.91,
    "source": "official_app_screenshots + packaging + interior",
    "note": "Consistent repeated color across multiple branded assets"
  }
}
```

## Menu research

The menu is one of the highest-value enrichment targets.

Search for:

- official menu page
- PDF menu
- Linktree menu links
- ordering platform owned/linked by the venue
- official mobile app
- current App Store screenshots
- delivery platforms
- recent menu listing sites
- social-menu images
- Google Place menu photos if needed

### Do not require prices

A QServe demo can still be high quality without prices.

Menu output should explicitly state price coverage:

```json
{
  "status": "partial_menu_found",
  "menu_completeness": 0.72,
  "price_coverage": 0.18,
  "use_prices": "only_verified_prices"
}
```

Allowed menu statuses:

- `strong_menu_found`
- `partial_menu_found`
- `menu_evidence_only`
- `no_menu_found`

### Item-level rules

Every menu item may contain:

```json
{
  "name": "Spanish Latte",
  "description": null,
  "price": 125,
  "currency": "EGP",
  "source": "current_menu_listing",
  "confidence": 0.92
}
```

If a price is not current/reliable, store `null` rather than guessing.

If two sources conflict, prefer:

1. current official source
2. current official ordering app
3. current branch-specific menu
4. recent delivery/menu platform
5. old/uncertain third party

Keep conflict notes when relevant.

## Image research

Do not download/analyze large image sets unless needed.

First use the web to find strong existing assets from official channels.

Use image/vision analysis when it can answer a concrete unresolved question such as:

- Is this the real logo?
- Which colors repeat across the brand?
- Is this image a menu/menu board?
- Is this a useful hero image?
- Can a high-resolution menu image provide readable items/prices?

If Google Places photos are used:

- classify images first
- categories: `logo`, `storefront`, `interior`, `food`, `drink`, `menu`, `packaging`, `irrelevant`
- only fetch/analyze high resolution for useful candidates
- preserve required attributions where applicable

## Social discovery

Try to identify official:

- Instagram
- Facebook
- TikTok when useful
- Linktree/beacons-style profile

Avoid confusing fan pages or similarly named businesses with the actual venue.

Use branch/location evidence to disambiguate.

## Demo Readiness Score

Calculate a separate 0–100 score for how easily a convincing personalized demo can be produced.

Suggested signals:

```text
+20 verified logo / clear brand identity
+20 clear brand palette / visual direction
+20 strong menu source
+10 usable prices
+10 official social presence
+10 usable hero/interior/product imagery
+10 reliable contact/location data
```

Suggested interpretation:

- 85–100: `demo_ready`
- 70–84: `demo_ready_with_gaps`
- 50–69: `partial_enrichment`
- below 50: `needs_more_research`

Do not equate Demo Readiness with QServe Fit. A venue can be a great customer but hard to research online.

## Recommended research-status values

- `not_researched`
- `researching`
- `assets_found`
- `menu_found`
- `demo_ready_with_gaps`
- `demo_ready`
- `needs_manual_review`

## Cost-control / stopping rule

Stop researching when the agent has enough to build a convincing demo.

For example, stop when all are true:

- clear business identity
- logo or convincing logo representation
- coherent visual palette/direction
- at least 2–4 menu categories
- enough real items to make the menu believable
- at least one usable hero/interior/product asset OR a design direction that does not depend on photography
- contact/location confirmed

Do not keep searching just to achieve 100% menu completeness for an unqualified sales lead.

## Source discipline

Every important fact should retain a source.

Preferred source record:

```json
{
  "type": "official_menu",
  "url": "https://...",
  "label": "Official KAIRO menu PDF",
  "confidence": 0.99,
  "retrieved_at": "2026-09-01"
}
```

Never silently combine weak evidence into a false certainty.

## Reference experiment: Koffee Kulture

Observed enrichment results:

- Place type: coffee shop
- Strong/high-traffic QServe candidate
- Official website found: `https://koffee-kulture.com/`
- Official Linktree found and exposes location-specific menu links/PDFs including KAIRO
- A current menu listing updated June 2026 exposed a very broad menu: 138 items across 18 categories
- Representative verified/current-ish menu sample used in the experiment:
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
  - Chocolate Cake — EGP 175
  - San Sebastian Cheesecake — EGP 195
  - Passion Mojito — EGP 140
  - Peach Ice Tea — EGP 120
- Visual direction from research/photo experiment: modern specialty coffee, minimal/warm, charcoal/deep-brown + cream/off-white, with muted green/mint appearing as a plausible accent
- Branding/menu confidence is high enough for a full personalized demo

Existing experiment file in the lead repo:

`experiments/menu-enrichment/koffee-kulture.json`

## Reference experiment: 1980 Coffee

Observed enrichment results:

- Place type: coffee shop
- Strong local brand candidate
- Google Places did not return an official website for the tested branch
- Official app/order ecosystem found through Prepit / App Store evidence
- Official App Store screenshots expose real menu UI and categories
- Strong visual identity: burnt orange / red-orange, charcoal/black, cream/warm gray
- `1980` mark repeats consistently on cups, packaging and interior material
- Visual direction: bold, graphic, retro-modern, casual specialty coffee
- Verified menu structure/categories include specialty coffee, breakfast/brunch, Benedict, rolled omelettes, sandwiches, mains, desserts and seasonal items
- Items observed from evidence include:
  - Spanish Latte
  - Caramel Latte
  - Flat White
  - Turkish Coffee
  - Matcha Latte
  - Caramel Frappe
  - Mojito
  - Salmon / Salmon Benedict
  - Mushroom Toast
  - Marry Me Chicken
  - Chicken Caesar Bagel
  - Philly Cheese
  - Pistachio Croffle
  - Chocolate Cake
  - Tiramisu
  - Tres Leches
- One directly evidenced official-app price in the experiment: Salmon — EGP 422
- Most other prices should remain omitted until verified
- Demo is ready using real items with prices shown only where verified

Existing experiment file in the lead repo:

`experiments/menu-enrichment/1980-coffee.json`

## Final batch output

For every enriched batch report:

- leads attempted
- demo-ready count
- partial count
- failed/no-data count
- average research time/calls if available
- top sources used
- menu-found rate
- logo-found rate
- social-found rate
- price-coverage rate

The downstream personalized-demo builder should consume only the structured enrichment output, not raw browsing notes.
