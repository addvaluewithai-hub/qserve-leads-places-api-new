# Multi-Campaign Places Lead CRM

A reusable lead-discovery and outreach CRM built on Google Places API (New), Crawl4AI, GitHub Actions, Cloudflare Pages and Cloudflare D1.

The repository started as a QServe cafe finder. It now treats cafes, law firms, dental practices and future verticals as campaign configurations instead of separate applications.

## Architecture

```text
campaigns/*.json
    ↓
Google Places Text Search
    ↓
operational + rating + review count + phone/website filters
    ↓
Place Details review sample for activity/freshness
    ↓
quality score + shortlist
    ↓
Crawl4AI homepage load only
    ↓
collect same-domain links visible on the homepage
    ↓
manual / ChatGPT service-gap verification
    ↓
Cloudflare D1 + CRM
```

## Included campaigns

- `campaigns/lawyers-tx.json` — Texas law firms across smaller cities and ZIP-code search terms
- `campaigns/dentists-tx.json` — Texas dental practices
- `campaigns/cafes-eg.json` — October / Sheikh Zayed cafes

## Google quality filters

Campaigns can independently define place type, search queries, cities/ZIP codes, rating floor, minimum review count, required phone/website, review freshness window and scoring weights.

### Review freshness limitation

Places API (New) returns at most five reviews for a Place and orders them by relevance. `latest_sampled_review_at` and `recent_sampled_reviews` are therefore activity signals, not a complete review history.

## Crawl4AI: homepage links only

Crawl4AI is intentionally a dumb collector in this project. It does not deep crawl, follow links, classify pages or make qualification decisions.

For each shortlisted lead it does exactly one browser-rendered homepage fetch and stores every same-domain link exposed by that homepage. Because the rendered homepage includes the normal navigation/header/footer, this gives us the URLs a visitor can reach directly from the main site navigation without recursively crawling the website.

Lawyer campaign config:

```json
{
  "crawl": {
    "engine": "crawl4ai",
    "mode": "homepage_links_only",
    "same_domain_only": true,
    "follow_links": false,
    "classification": false
  }
}
```

Outputs:

```text
homepage_links.csv            one row per lead + destination URL + anchor text
homepage_links.json           same data grouped by lead
homepage_fetch_summary.json   one row per homepage fetch
homepage_links_summary.json   aggregate counts
```

The crawler deliberately does not decide whether `/family-law`, `/practice-areas`, `/probate`, or any other URL is good or bad. That interpretation happens afterward during manual/ChatGPT verification.

Run the homepage link stage after discovery with:

```bash
pip install -r requirements-crawl.txt
crawl4ai-setup
python scripts/crawl_campaign_websites.py --campaign lawyers-tx --limit 10
```

## Run discovery locally

```bash
export GOOGLE_API_KEY=...
python scripts/run_campaign.py --campaign lawyers-tx --limit 50 --max-pages 2
```

Discovery outputs are written under `out/<campaign>/` and include `campaign.json`, `all_candidates.json`, `leads.json`, `leads.csv`, and `summary.json`.

## GitHub Actions

Use **Actions → Run lead campaign** and choose the campaign, target lead limit, maximum Google Text Search pages, and whether to sync to D1.

For campaigns with `website_crawl_required=true`, the same workflow installs Crawl4AI + Chromium after Google discovery and collects homepage links. Push smoke tests do not write campaign data into D1.

Required GitHub secrets:

```text
GOOGLE_API_KEY
CLOUDFLARE_ACCOUNT_ID
CLOUDFLARE_API_TOKEN
D1_DATABASE_ID
```

## Cloudflare D1

The data model separates canonical businesses from campaign membership:

```text
leads
campaigns
campaign_runs
campaign_leads
lead_signals
```

This means one business can appear in multiple campaigns without mixing campaign-specific status, score, priority or notes.

## Lawyers review workflow

```text
Google-qualified Texas law firm
    ↓
Crawl4AI fetches homepage only
    ↓
inspect homepage_links.csv
    ↓
if target service has an obvious dedicated internal URL → Disqualified for that gap
    ↓
if no dedicated target-service link appears → manually double-check the website
    ↓
Qualified only after the double-check
    ↓
owner + direct email enrichment
```

The important rule is that a general `/services` or `/practice-areas` page is allowed. We only reject the gap when the exact target service has its own separate page.

## Next hardening

Useful next additions:

1. Record exact Google API call counts and estimated SKU cost per campaign run.
2. Persist homepage link evidence into a dedicated D1 table when desired.
3. Add per-area coverage records for city/ZIP/query combinations.
4. Preserve every Google query that matched a business instead of only the primary query.
5. Add decision-maker/direct-email enrichment.
6. Add scheduled revalidation and outreach suppression lists.
