# Coder Task: Turn QServe into a Highly Personalized Venue Experience Engine

## Goal

Modify the main QServe product repository so a coder/agent can generate **highly customized guest experiences for each cafe/restaurant/lounge from enrichment data**, while keeping a single maintainable React codebase.

The experience should feel like the venue's own digital product, not a generic QServe template with different colors.

Main product repository:

`https://github.com/addvaluewithai-hub/Qserve`

Lead/enrichment repository:

`https://github.com/addvaluewithai-hub/qserve-leads-places-api-new`

This task should use the first two researched venues — **Koffee Kulture** and **1980 Coffee** — as reference implementations.

## Product philosophy

QServe already supports venue-driven guest routes such as:

- `/v/:slug`
- `/v/:slug/t/:table`
- `/v/:slug/t/:table/menu`

The existing venue schema already contains business identity, locale, themes, actions, rewards, menu and contact data. The problem is that visual customization is still too dependent on a single shared composition plus per-venue CSS overrides.

We need to evolve QServe from:

`same layout + different colors/content`

into:

`same product capabilities + different venue-specific composition and visual system`

The implementation must remain data-driven. Do not create a bespoke React app for every customer.

## Existing architecture to preserve

The main concepts should remain reusable:

- GuestHome
- MenuPage
- ServiceRequestSheet
- RewardClubSheet
- venue registry
- venue routing
- localized text objects
- shared analytics/events
- shared QServe service behavior

Do not duplicate entire pages for each venue.

## New concept: experience configuration / presets

Add a generic venue-level configuration layer that can control more than colors.

Suggested shape:

```js
experience: {
  preset: 'editorial-coffee',
  density: 'relaxed',
  brandPresentation: 'wordmark',
  hero: {
    style: 'editorial',
    media: '/assets/...',
    overlay: 'soft',
    alignment: 'left'
  },
  home: {
    layout: 'editorial-stack',
    actionStyle: 'cards',
    primaryActionStyle: 'feature-panel',
    rewardsStyle: 'membership-card'
  },
  menu: {
    layout: 'image-led',
    cardStyle: 'editorial',
    categoryStyle: 'pills',
    showPrices: true
  },
  motion: 'soft',
  typography: {
    tone: 'modern-humanist'
  }
}
```

The exact schema may differ, but the goal is to expose composition decisions as data.

## Do not make presets rigid

A preset should provide defaults, but individual venue config should be able to override parts.

For example:

```js
experience: {
  preset: 'graphic-retro',
  home: { actionStyle: 'compact-blocks' },
  menu: { showPrices: false }
}
```

## Minimum variation dimensions

Support meaningful variation across at least these dimensions:

### Brand presentation

- logo image
- wordmark image
- text fallback / logoMark
- rounded vs square brand mark
- compact header vs large brand statement

Add support for a real `logoUrl`/`wordmarkUrl` rather than relying only on a letter `logoMark`.

### Home hero

Support at least:

- minimal/text hero
- image-backed hero
- editorial split hero
- bold graphic hero

### Action composition

Support at least:

- large primary + grid secondary
- compact stacked service list
- icon tiles
- editorial cards

The order of actions remains venue-configurable.

### Menu presentation

Support at least:

- image-led cards
- text-first menu rows
- compact dense menu
- editorial menu cards

Prices must be optional **per menu and per item**.

Current code assumes `item.price` always exists and formats it. Fix this so missing/unverified prices do not show `NaN`, `EGP 0`, or misleading placeholders.

### Imagery strategy

Support:

- venue hero image
- category hero image
- item image
- no-image/text-first mode

A venue with weak photography should still look intentional rather than broken.

### Shape/tone

Expose enough tokens for:

- radius
- borders
- shadows
- surface contrast
- spacing/density
- accent treatment
- icon treatment

## Reference implementation 1: Koffee Kulture

### Research findings

Use these as input, not as absolute official-brand claims where confidence is lower.

Business:

- Name: Koffee Kulture
- Type: coffee shop / specialty cafe
- Tested Google Place: rating ~4.8 with 8K+ reviews
- Official website found: `https://koffee-kulture.com/`
- Official Linktree exposes venue/location menu links including KAIRO

Menu research:

A strong current menu source was found, with 138 items / 18 categories in the researched listing. A representative subset is enough for the demo.

Sample menu items and prices from the enrichment experiment:

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

Detailed enrichment file:

`https://github.com/addvaluewithai-hub/qserve-leads-places-api-new/blob/main/experiments/menu-enrichment/koffee-kulture.json`

### Visual direction

Research/photo experiment suggested:

- modern specialty coffee
- minimal / warm
- charcoal or deep brown
- cream / off-white surfaces
- muted green/mint as plausible accent
- polished, premium but not luxury

### Desired QServe experience

Koffee Kulture should feel **editorial, calm, premium, coffee-first**.

Suggested direction:

- light cream base
- restrained dark typography
- muted green accent
- generous whitespace
- real wordmark/logo if a safe asset is available
- image-led menu when good product imagery is available
- main CTA emphasizes Menu
- secondary services feel quiet and integrated rather than loud dashboard buttons
- loyalty/rewards should look like a branded membership card
- menu prices may be shown because confidence is relatively strong

Potential preset name:

`editorial-coffee`

The user should feel they opened a Koffee Kulture digital experience powered quietly by QServe, not a QServe demo painted green.

## Reference implementation 2: 1980 Coffee

### Research findings

Business:

- Name: 1980 Coffee
- Type: coffee shop
- Tested branch rating ~4.8 with 2K+ reviews
- No official website was returned by Google Places for the tested branch
- Official app/order ecosystem was found
- Official App Store screenshots expose real menu UI

Detailed enrichment file:

`https://github.com/addvaluewithai-hub/qserve-leads-places-api-new/blob/main/experiments/menu-enrichment/1980-coffee.json`

### Visual direction

Strong repeated brand evidence showed:

- burnt orange / red-orange
- charcoal / black
- cream / warm gray
- repeated `1980` mark across cups, packaging and environment
- bold
- graphic
- retro-modern
- casual specialty coffee

### Menu evidence

Known menu families/items include:

- specialty coffee
- breakfast/brunch
- Benedict
- rolled omelettes
- sandwiches
- mains
- desserts
- seasonal items

Observed item names include:

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

Only one price was treated as directly verified in the experiment:

- Salmon — EGP 422

Therefore, the 1980 demo should mostly **omit prices unless verified**.

### Desired QServe experience

1980 should feel **bold, graphic, fast, retro-modern**, clearly different from Koffee Kulture.

Suggested direction:

- burnt-orange dominant brand area
- charcoal text / blocks
- cream background
- stronger typography scale
- rectangular or lower-radius shapes compared with Koffee Kulture
- graphic blocks / labels / numbers
- `1980` mark prominently presented
- text-first menu where item photography is unavailable
- table-service actions can feel punchier and more direct
- rewards can look like a bold stamp/pass rather than a soft editorial membership card
- show only verified prices

Potential preset name:

`graphic-retro`

## Functional changes required

### 1. Add price-optional menu support

Update `MenuPage`, `MenuCard`, `ItemSheet`, Featured items and any dashboard previews so `price == null` is valid.

Rules:

- if price exists: format normally
- if price is null/undefined: render no price
- no fake placeholders
- menu-level `showPrices: false` should hide all prices even if values exist

### 2. Add real brand asset support

Extend business/branding schema, for example:

```js
business: {
  ...,
  logoMark,
  logoUrl,
  wordmarkUrl
}
```

Components should gracefully fall back:

`wordmarkUrl -> logoUrl -> logoMark -> first letter`

### 3. Add experience preset hooks

GuestHome and MenuPage should expose `data-experience`, `data-home-layout`, `data-menu-layout`, etc., based on venue data so generic CSS/component variants can respond without hard-coding venue names.

Avoid building customization primarily with selectors like:

```css
[data-venue="specific-customer"]
```

Some per-venue final polish is acceptable, but most behavior should come from reusable preset/layout selectors.

### 4. Add reusable experience CSS

Create something like:

`src/styles/venue-experiences.css`

with reusable selectors such as:

```css
[data-experience="editorial-coffee"] { ... }
[data-experience="graphic-retro"] { ... }
[data-menu-layout="text-first"] { ... }
[data-action-style="compact-blocks"] { ... }
```

### 5. Add the two venue configs

Create:

- `src/data/venues/koffeeKultureVenue.js`
- `src/data/venues/coffee1980Venue.js`

Register them in the venue registry.

Suggested slugs:

- `koffee-kulture`
- `1980-coffee`

Suggested demo URLs:

- `/v/koffee-kulture/t/12`
- `/v/koffee-kulture/t/12/menu`
- `/v/1980-coffee/t/7`
- `/v/1980-coffee/t/7/menu`

### 6. Use honest demo data

Do not present weakly sourced content as certain.

For the first implementation:

- Koffee Kulture: use representative verified/high-confidence prices
- 1980: omit most prices
- do not invent Wi-Fi passwords, phone numbers, promotions, opening hours, or rewards terms as though they are real

If a demo-only service/reward value is needed, clearly mark it in code/config as a demo concept.

### 7. Rewards should be venue-customizable

Do not force every cafe to show "10% off".

Allow reward mode/content/style to vary or be disabled.

Examples:

- Koffee Kulture: tasteful guest-club / next-visit benefit demo
- 1980: bold membership/pass concept

But avoid fabricating a real existing loyalty program.

### 8. Action sets should vary by venue model

Do not automatically give every coffee shop `lighter`, `water`, etc.

Venue configs choose the appropriate actions.

For example:

Koffee Kulture:

- Menu
- Call waiter if appropriate
- Request bill if appropriate
- Wi-Fi if verified/configured
- Guest club

1980:

- Menu
- Call waiter
- Bill
- potentially order/help-oriented CTA depending on the intended demo

### 9. Keep localization architecture

Preserve the existing localized object approach.

For these demo configs, do not claim translations are official brand copy. Use concise neutral experience copy.

### 10. Keep QServe subtle

The venue brand should dominate the guest experience.

`Powered by QServe` can remain but should be visually subordinate.

## Acceptance criteria

The task is complete when:

1. Both new routes work.
2. Koffee Kulture and 1980 clearly look like different digital products at first glance.
3. They still share the same QServe GuestHome/Menu/service architecture.
4. No page is duplicated per venue.
5. New venue creation is primarily a data/config task.
6. Experience preset/layout fields are documented.
7. Missing menu prices render cleanly.
8. Real logo/wordmark assets are supported.
9. Existing Nile Table and Brew & Bean experiences still work.
10. `npm run build` passes.
11. Mobile layouts are tested around 360–430px widths.
12. RTL behavior is not broken by the new generic experience system.

## Documentation update

Update `docs/VENUE_SCHEMA.md` to explain:

- experience presets
- layout options
- brand asset fields
- price-optional items
- imagery fields
- how an enrichment agent maps its output into a venue config

Include a small example showing how a future enriched lead can become a new venue config without adding bespoke React components.

## Important implementation principle

Do not optimize only for these two cafes.

The real test is:

> If the enrichment agent gives us a third cafe tomorrow with a luxury black/gold identity, or a playful colorful brunch identity, can a coder/agent build a convincing experience mostly by changing venue data and selecting/composing reusable variants?

If the answer still requires copying GuestHome/MenuPage or writing hundreds of customer-specific CSS lines, the abstraction is not finished.
