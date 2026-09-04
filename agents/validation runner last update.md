# Validation Runner Last Update

> Required handoff record between validation sessions. Read this before validation work. D1 is the source of truth.

## Last Updated

- Date: 2026-09-04
- Runner / session: ChatGPT validation runner — manual clean-homepage-URL validation
- Repository / dataset: `addvaluewithai-hub/qserve-leads-places-api-new` / D1 `lawyers-us`
- Campaign: `lawyers-us`

## Current Operating Mode — IMPORTANT

The scoring/hint pre-screen is **deprecated as a decision surface**.

Production Agent 2 input is:

```text
20 new-production Ready leads
→ ALL clean same-domain page URLs collected from the rendered homepage
→ obvious asset/file targets removed only
→ NO scoring
→ NO hints
→ NO categorization
→ NO ranking
→ NO top-N truncation
→ Agent 2 manually judges architecture from the URLs
→ live-site check only when URL evidence is zero / generic / ambiguous
→ owner + direct-email research only after a real architecture gap passes
```

Agent 1 / Crawl4AI remains an evidence collector only. It does not deep crawl, classify services, decide architecture maturity, find gaps, or research contacts.

## Production clean-URL artifacts

```text
agents/validation next clean URL batch.json
agents/validation next clean URL leads/01.json ... 20.json
```

Standalone generator:

```text
.github/workflows/validation-runner-clean-url-batch.yml
```

More importantly, the normal audit apply workflow now refreshes the next clean 20 **inside the same workflow run after D1 is updated**:

```text
.github/workflows/validation-audit-apply-decisions.yml
```

This avoids relying on a second GitHub Actions workflow being triggered by a `github-actions[bot]` receipt commit.

Normal cadence is now:

```text
review 20 sequentially
→ commit one batch decision JSON
→ same workflow applies all 20 to D1
→ same workflow writes receipt
→ same workflow queries updated D1
→ same workflow writes next clean 20
→ repeat
```

Selection rule:

```text
campaign_id = lawyers-us
status = Ready for Validation
qualified = 0
qualification_reason = working_set_ready_for_validation
```

## Manual Audit Baseline — First 100

The original 100 new-production leads were re-reviewed from scratch as five sequential batches of 20.

Verification result: `PASS`.

Exact post-audit D1 counts for those same 100 IDs:

```text
Disqualified                         68
Not Relevant                        26
Needs Review                         2
Gap Confirmed - Direct Email Missing 1
Qualified                            3
TOTAL                              100
```

Qualified from those 100:

- Bruce Kaye PLLC — Entertainment Law — `bruce@brucekaye.com`
- Kelley Law Firm — Business Litigation — `kelley@kelleyfirm.com`
- Meyer Friedman Reed PLLC — Criminal Law — Daniel J. Meyer — `dmeyer@mfrlaw.net`

Main audit correction: many sites with lots of separate URLs were still one narrow client journey, especially Personal Injury, Criminal Defense, Family Law, Bankruptcy, Tax, etc. URL count is never architecture maturity by itself.

Correct question:

> Are materially different main client journeys already separated into focused destinations?

## Batch 06 — Leads 101–120

Decision file:

```text
agents/validation audit decisions/batch-06.json
```

D1 apply receipt confirmed all 20.

Result:

```text
Not Relevant  12
Disqualified   8
Needs Review   0
Qualified      0
TOTAL         20
```

Notable live checks:

- `erinhendrickslaw.com`: current official site is Criminal Defense only → `Not Relevant`.
- `greenclark.law` / previous `stephengreenlaw.com`: current site has focused Federal Criminal Defense, White Collar, DEA Drug Diversion, Plaintiffs Civil Litigation and Personal Injury destinations → `Disqualified`.
- `handlemytickets.com`: sparse homepage URL evidence required live verification; the same attorney/practice also operates a separate focused Richard Trial Attorneys property for Personal Injury/Wrongful Death, so the practice already deliberately separates materially different journeys → `Disqualified`.
- `barbarelawyer.com`: current domain is no longer a law-firm site and serves gambling/casino content → `Not Relevant`.
- `belachewlaw.com`: Personal Injury and Estate Planning/Probate are both explicitly offered and separately surfaced → `Disqualified`.
- `dunhamlaw.com`: deep Criminal Defense architecture plus a separate large Injury Lawyers architecture → `Disqualified`.

After Batch 06:

```text
new-production Ready remaining = 704
```

## Architecture Rules

1. **Single journey beats URL count.** A PI-only firm with 150 focused injury pages is usually `Not Relevant`, not `Disqualified`.
2. **Separate pages matter across materially different main services.** Criminal + PI, Family + Business, Immigration + PI, etc. are the architecture test.
3. **One isolated missing page on an otherwise mature multi-practice site is `Disqualified`.** Do not hunt forgotten URLs.
4. **Mixed architecture is qualitative.** If several materially different main services remain in the shared/general experience and separate-page adoption is not dominant, continue to gap validation.
5. **Zero Crawl links never imply opportunity.** Live-check blocked/challenge cases.
6. **Search absence alone never proves a missing page.** Use clean homepage evidence plus live/site-restricted verification where needed.
7. **Owner/email research stays last.** `Qualified` requires a real gap + actual owner/DM + direct public verified individual email.
8. **Current site identity matters.** If the domain has changed business, redirects to a new law-firm property, or is stale/hijacked, verify before classifying.

## Next Production Batch — Leads 121–140

Already generated from updated D1.

- New-production Ready remaining: `704`
- Batch size: `20`
- First lead:
  - `Dallas Personal Injury Attorney | Mullen & Mullen Law Firm`
  - domain: `mullenandmullen.com`
  - lead ID: `ChIJb0ob10-ZToYREVKWnUdMZJ8`
  - clean homepage URL count: `34`

Use:

```text
agents/validation next clean URL leads/01.json ... 20.json
```

Review all 20 sequentially, commit one `batch-07.json`, and let the updated apply workflow handle D1 + receipt + next clean 20 in one run.

Historical first-1,000 validation remains intentionally deferred.

## Handoff Confirmation

- [x] First 100 manually re-audited and D1-verified.
- [x] Batch 06 (leads 101–120) reviewed sequentially and applied to D1.
- [x] Batch 06 result: 12 Not Relevant / 8 Disqualified / 0 Qualified.
- [x] New-production Ready remaining: 704.
- [x] Apply workflow now refreshes next clean 20 in the same run.
- [x] Batch 07 clean URLs already generated; first lead is Mullen & Mullen Law Firm.
