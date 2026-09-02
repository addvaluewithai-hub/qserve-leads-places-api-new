# Multi-Campaign Places Lead CRM

A reusable lead-discovery and outreach CRM built on Google Places API (New), Crawl4AI, GitHub Actions, Cloudflare Pages and Cloudflare D1.

The repository started as a QServe cafe finder. It now treats cafes, law firms, dental practices and future verticals as **campaign configurations** instead of separate applications.

## Architecture

```text
campaigns/*.json
    ↓
Google Places Text Search (discovery)
    ↓
coarse filters: operational + rating + review count + phone/website
    ↓
Place Details reviews (activity/freshness signal)
    ↓
quality score + qualification
    ↓
Crawl4AI (when website_crawl_required=true)
    ├── same-domain deep crawl
    ├── page + title inventory
    ├── internal link graph + anchor text
    ├── general Services / Practice Areas detection
    ├── dedicated service URL detection
    └── service-gap evidence
    ↓
Cloudflare D1
    ├── leads              one canonical Google Place/business
    ├── campaigns          reusable campaign definitions
    ├── campaign_runs      audit trail for campaign executions
    ├── campaign_leads     campaign-specific score/status/notes
    └── lead_signals       review freshness/contact signals
    ↓
Cloudflare Pages CRM UI
```

## Included campaigns

- `campaigns/lawyers-tx.json` — Texas law firms, split across smaller cities and ZIP-code search terms
- `campaigns/dentists-tx.json` — Texas dental practices
- `campaigns/cafes-eg.json` — the original October / Sheikh Zayed cafe campaign represented in the same format

Add a new niche by creating another JSON file. The engine does not need to be copied.

## Quality filters

Each campaign can independently define:

- Google place type (`lawyer`, `dentist`, `cafe`, etc.)
- query variants
- cities / ZIP codes / area terms
- minimum rating
- minimum total Google review count
- allowed business status (normally `OPERATIONAL`)
- required phone / website
- optional price levels
- review-recency window
- minimum number of recent reviews found in the returned review sample
- scoring weights
- downstream website-enrichment requirements

### Important review-recency limitation

Places API (New) returns at most five reviews for a Place and orders them by relevance. The engine therefore stores fields named `latest_sampled_review_at` and `recent_sampled_reviews`. These are useful activity signals but are **not a complete review history** and should not be presented as the true latest review unless independently verified.

The runner keeps review retrieval as a second stage so expensive review fields are requested only for businesses that already pass the coarse rating/review/contact filters.

## Crawl4AI website enrichment

Crawl4AI is installed and executed inside this repository; no second crawler repository is required.

Campaigns opt in with:

```json
{
  "enrichment": {
    "website_crawl_required": true
  },
  "crawl": {
    "engine": "crawl4ai",
    "max_depth": 2,
    "max_pages_per_site": 30,
    "same_domain_only": true,
    "capture_link_graph": true,
    "general_service_pages_are_allowed": true
  }
}
```

The crawler deliberately does **not** treat a general `/practice-areas` or `/services` page as a dedicated service page. Strong dedicated-page evidence is based on a service-specific internal URL such as `/family-law` or `/estate-planning`. Title-only signals are stored separately for manual or later model review.

For campaigns with target services, the crawler also records services mentioned on the homepage/general service page and compares them with dedicated service URLs.

Crawl outputs are added to the normal campaign artifact:

```text
crawl_results.json      per-lead crawl summary and service evidence
crawl_summary.json      aggregate crawl counts
crawl_pages.csv         discovered same-domain pages, titles and classifications
crawl_links.csv         source URL → target URL + anchor text
leads_enriched.json     Google lead records plus crawl evidence
```

Run just the crawl stage after a campaign discovery run with:

```bash
pip install -r requirements-crawl.txt
crawl4ai-setup
python scripts/crawl_campaign_websites.py --campaign lawyers-tx --limit 10
```

## Run locally

```bash
export GOOGLE_API_KEY=...
python scripts/run_campaign.py --campaign lawyers-tx --limit 50 --max-pages 2
```

Outputs are written to:

```text
out/lawyers-tx/
  campaign.json
  all_candidates.json
  leads.json
  leads.csv
  summary.json
```

If the campaign requires website crawling, run `crawl_campaign_websites.py` before syncing or reviewing the final artifact.

To sync a completed run to D1:

```bash
export CLOUDFLARE_ACCOUNT_ID=...
export CLOUDFLARE_API_TOKEN=...
export D1_DATABASE_ID=...
python scripts/sync_campaign_to_d1.py --campaign lawyers-tx
```

## GitHub Actions

Use **Actions → Run lead campaign** and choose:

- campaign
- target lead limit
- maximum Google result pages per query
- whether to sync results into D1

The workflow automatically detects `website_crawl_required=true`, installs Crawl4AI + Chromium, and runs the crawl stage after Google discovery. Pushes that touch the campaign engine run a small `lawyers-tx` smoke test without modifying D1.

Required GitHub secrets:

```text
GOOGLE_API_KEY
CLOUDFLARE_ACCOUNT_ID
CLOUDFLARE_API_TOKEN
D1_DATABASE_ID
```

The older cafe-specific workflow and export script are retained for backwards compatibility. New campaigns should use `run-lead-campaign.yml` and `scripts/run_campaign.py`.

## Cloudflare Pages

Build settings:

```text
Framework preset: None
Build command: npm run build
Build output directory: dist
```

Bindings / environment:

```text
GOOGLE_API_KEY=...
DB=<Cloudflare D1 binding>
```

The UI loads campaigns from `/api/campaigns` and campaign-specific leads from `/api/leads?campaign=<id>`. CRM status, priority and notes are stored per campaign rather than globally on the business.

## Lawyers pipeline

The current lawyer pipeline is:

```text
active/reputable law firm from Google Places
    ↓
Crawl4AI same-domain crawl
    ↓
identify explicitly offered target services
    ↓
map internal URLs and detect dedicated service pages
    ↓
decision maker + direct public email enrichment (next enrichment stage)
    ↓
final outreach-qualified lead
```

`campaigns/lawyers-tx.json` contains the target services, crawl settings and enrichment requirements used by the workflow.

## Next production hardening

Useful next additions:

1. Persist crawl summaries/page evidence into dedicated D1 enrichment tables when `sync_d1=true`.
2. Add per-area coverage records so we know which ZIP/city/query combinations have been searched and when.
3. Preserve every Google query that matched a business instead of only the primary discovery query.
4. Add retry/rate-limit and API-cost telemetry per campaign run.
5. Add owner/email verification and outreach eligibility fields instead of storing them only in free-text notes.
6. Add scheduled refreshes so stale leads are rechecked and closed/inactive businesses are automatically downgraded.
7. Add suppression lists for contacted, opted-out and permanently rejected businesses.
