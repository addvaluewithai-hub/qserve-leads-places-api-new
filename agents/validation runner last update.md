# Validation Runner Last Update

> This file is the required handoff record between validation sessions.
> Read it before doing any validation work.
> D1 is the source of truth; this file is the human-readable handoff.

## Last Updated

- Date: 2026-09-04
- Runner / session: ChatGPT validation runner — Crawl4AI-first new-production test
- Repository / dataset: `addvaluewithai-hub/qserve-leads-places-api-new` / D1 `lawyers-us`
- Campaign: `lawyers-us`

## Current Operating Mode

Temporarily prioritize **new production leads** over the historical first-1,000 queue so the current Crawl4AI handoff can be tested before historical backfill work.

New-production selection rule:

```text
campaign_id = lawyers-us
status = Ready for Validation
qualified = 0
qualification_reason = working_set_ready_for_validation
```

The new-production snapshot showed **830 Ready for Validation** leads before this test batch.

## Crawl4AI-First Validation Flow

For new production leads, start from `homepage_link_evidence` before opening the live site.

1. Review homepage internal URL paths + anchor text in batches.
2. Apply the Architecture Maturity Gate from Crawl4AI evidence.
3. If the homepage links clearly prove a mature separate-service architecture, mark `Disqualified` without owner/email research.
4. Only open the website deeply when Crawl4AI evidence is sparse, ambiguous, or suggests a shared/general service architecture.
5. A gap can still only be confirmed after independent live-site double-check.

A compact helper snapshot now exists:

```text
agents/validation new crawl prescreen.json
```

It ranks structural/service-like homepage links for the next 10 new-production leads. This is a pre-screen only, not a final classifier.

## First New-Production Test Batch

The first six leads through the stop condition were applied to D1 in one commit/workflow run.

### Disqualified from Crawl4AI architecture evidence

1. Castillo Lawyer — `castillolawphoenix.com`
   - 29 homepage internal links
   - clear separate pages for Assault, DUI, Drug Defense, Sex Crimes, etc.

2. Alcock Law — `alcocklaw.com`
   - 82 homepage internal links
   - very mature Criminal Defense / Family / Personal Injury service architecture

3. Shah Law Firm — `arjashahlaw.com`
   - 64 homepage internal links
   - separate DUI / criminal-defense pages and geo/service depth

4. Sotelo Law Group — `sotelolawgroup.com`
   - 25 homepage internal links
   - dedicated `case-types` pages for Car, Motorcycle, Slip & Fall, Truck, etc.

5. Hartley Law — `hartleylawusa.com`
   - 25 homepage internal links
   - dedicated pages for Car, Motorcycle, Truck, Medical Malpractice, etc.

No owner/email research was performed for these five because they failed the Architecture Maturity Gate.

### Qualified — Owen Law Firm

- Lead ID: `ChIJKb6Hs5wTK4cRlg9qnRRmGgs`
- Domain: `amyowenlaw.com`
- Crawl4AI homepage evidence: 8 internal links, zero structural service-page signals
- Deep validation: official `Areas of Practice` page combines **Personal Injury + Civil Rights** on one shared page
- Selected first mockup service: **Civil Rights**
- Dedicated Civil Rights page: none found after navigation + site-restricted search
- Decision maker: **Amy Owen — Founder & Managing Attorney**
- Direct public email: **amy@amyowenlaw.com**
- D1 final status: `Qualified`
- D1 qualified flag: `1`
- Outreach draft stored in campaign notes

## What This Test Showed

The Crawl4AI collection itself is doing the intended job for new production leads: homepage rendering + same-domain visible internal link collection is enough to eliminate obvious mature-architecture firms very quickly.

Current finding: **do not add deep crawling to Crawl4AI yet.** The biggest improvement needed was on the Agent 2 presentation/pre-screen layer, not the crawler depth.

The raw Crawl4AI data contains some noise (assets, blog URLs, generic `Learn More` anchors), so the compact pre-screen helper filters/ranks structural links while preserving the full raw evidence in D1.

## Exact Next Action

> Continue in new-production mode from the next unprocessed lead after Owen Law in the tested batch: `landeroslegal.com`, lead ID `ChIJL74zCAoRK4cRxk5vFlMj6DA`. Its Crawl4AI snapshot has only 6 homepage links and zero structural service signals, so it requires a live-site identity/architecture double-check. Then continue 10-by-10 using Crawl4AI pre-screening until the next genuinely new Qualified lead is found.

Historical first-1,000 validation is intentionally deferred for now. Later, decide whether to backfill their `homepage_link_evidence` with Crawl4AI.

## Handoff Confirmation

- [x] Architecture Maturity Gate remains mandatory.
- [x] New production leads are temporarily prioritized.
- [x] Crawl4AI-first 10-lead pre-screen snapshot exists.
- [x] Five mature sites were disqualified from Crawl evidence without unnecessary contact research.
- [x] Owen Law passed deep validation and was written to D1 as Qualified.
- [x] Exact next new-production lead is recorded.
