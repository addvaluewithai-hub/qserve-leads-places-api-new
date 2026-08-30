# QServe Leads Places CRM

A quick Cloudflare Pages CRM for finding premium café/restaurant leads with Google Places API (New), then tracking outreach status locally in the browser.

## What it does

- Searches Google Places API (New) through a Cloudflare Pages Function
- Keeps `GOOGLE_API_KEY` server-side, not in browser JavaScript
- Filters by place type: café or restaurant
- Filters by price levels: `$`, `$$`, `$$$`, `$$$$`
- Defaults to premium leads: `$$$` and `$$$$`
- Tracks CRM status, priority and notes in `localStorage`
- Exports the visible lead list to CSV

## Cloudflare Pages settings

Use these build settings:

```txt
Framework preset: None
Build command: npm run build
Build output directory: dist
```

Add this environment variable in Cloudflare Pages:

```txt
GOOGLE_API_KEY=your_google_places_api_key
```

The GitHub Actions secret used by the smoke test is separate from the Cloudflare Pages runtime variable. Add the key in Cloudflare too, otherwise `/api/search` will return a missing-key error.

## Local setup

```bash
npm install
npm run dev
```

For local API testing with Cloudflare Pages Functions, use Wrangler/Pages dev and provide `GOOGLE_API_KEY` in your local environment.

## Existing smoke test

`test_places_price.py` is still included for GitHub Actions. It verifies that the Google key can call Places API (New) with `PRICE_LEVEL_VERY_EXPENSIVE`.
