# Multi-Campaign Places Lead CRM

A reusable lead-discovery and outreach CRM built on Google Places API (New), GitHub Actions, Cloudflare Pages and Cloudflare D1.

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

Pushes that touch the campaign engine run a small `lawyers-tx` smoke test without modifying D1.

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

Google Places discovery is only the first half of the lawyer campaign. The intended pipeline is:

```text
active/reputable law firm from Google Places
    ↓
website crawler (Crawl4AI / browser fallback)
    ↓
identify explicitly offered target services
    ↓
map internal URLs and detect dedicated service pages
    ↓
decision maker + direct public email enrichment
    ↓
final outreach-qualified lead
```

`campaigns/lawyers-tx.json` already contains the target service and enrichment requirements so the crawl stage can consume the same campaign definition later.

## Next production hardening

Useful next additions:

1. Connect the Crawl4AI repository as an enrichment worker and write crawl results back to `campaign_leads` / a dedicated enrichment table.
2. Add per-area coverage records so we know which ZIP/city/query combinations have been searched and when.
3. Add domain normalization and cross-source duplicate detection (Google Place ID + normalized website domain + phone).
4. Add retry/rate-limit and API-cost telemetry per campaign run.
5. Add owner/email verification and outreach eligibility fields instead of storing them only in free-text notes.
6. Add scheduled refreshes so stale leads are rechecked and closed/inactive businesses are automatically downgraded.
7. Add suppression lists for contacted, opted-out and permanently rejected businesses.
