# Validation Runner Last Update

> Current production handoff. D1 is the source of truth.

## Last Updated

- Date: 2026-09-05
- Campaign: `lawyers-us`
- Repository: `addvaluewithai-hub/qserve-leads-places-api-new`
- Operating mode: manual full clean-homepage-URL validation

## Current Production Rule

The scoring/hint pre-screen is deprecated as a decision surface.

Production Agent 2 flow is:

```text
20 Ready leads
→ read ALL clean same-domain homepage page URLs
→ no score
→ no hint
→ no categorization
→ no ranking
→ no top-N truncation
→ manually judge architecture
→ live-check only zero/generic/ambiguous/promising-gap cases
→ owner + direct-email research only after a real architecture gap passes
→ commit one 20-decision JSON
→ workflow applies all 20 to D1
→ same workflow writes receipt and refreshes next clean 20
→ repeat
```

Primary artifacts:

```text
agents/validation next clean URL batch.json
agents/validation next clean URL leads/01.json ... 20.json
agents/validation audit decisions/batch-XX.json
agents/validation audit apply receipt.json
```

Apply workflow:

```text
.github/workflows/validation-audit-apply-decisions.yml
```

## Architecture Rules That Must Not Drift

1. **Single journey beats URL count.** PI-only, Criminal-only, Family-only, Immigration-only, etc. are usually `Not Relevant` even with many pages.
2. **Disqualified means materially different main journeys are already separated.** Do not call a deep single-practice site mature multi-practice architecture.
3. **One isolated missing page on an otherwise mature multi-practice site is not the ICP.** Usually `Disqualified`.
4. **Several materially different main services sharing one homepage/general Services/Practice Areas experience can be a real gap.**
5. **Zero/blocked Crawl evidence never proves opportunity.** Live-check.
6. **Search absence alone never proves a page is missing.**
7. **Current domain identity matters.** Verify redirects, stale domains, hijacked/spam domains, or moved firms.
8. **Owner/email research is last.**
9. **Qualified requires a real gap + actual decision maker + direct public verified individual email.**
10. Generic inboxes such as `info@`, `contact@`, `legal@`, `office@`, etc. do not make a lead Qualified.

## Completed Production Batches

### First 100 — manual re-audit

Final verified counts:

```text
Disqualified                          68
Not Relevant                         26
Needs Review                          2
Gap Confirmed - Direct Email Missing  1
Qualified                             3
TOTAL                               100
```

Qualified from those 100:

- Bruce Kaye PLLC — Entertainment Law — `bruce@brucekaye.com`
- Kelley Law Firm — Business Litigation — `kelley@kelleyfirm.com`
- Meyer Friedman Reed PLLC — Criminal Law — Daniel J. Meyer — `dmeyer@mfrlaw.net`

### Batch 06 — leads 101–120

```text
Not Relevant  12
Disqualified   8
Qualified      0
TOTAL         20
```

### Batch 07 — leads 121–140

```text
Not Relevant                         11
Disqualified                          7
Gap Confirmed - Direct Email Missing  1
Qualified                             1
TOTAL                                20
```

New Qualified:

- Law Offices of Rogelio Herrera
- selected gap: Family Law
- decision maker: Roger Herrera — Owner
- direct public verified email: `Law_rogelioherrera@sbcglobal.net`

Gap without direct email:

- BG Law — Immigration + Personal Injury remain in shared homepage architecture; Brenda Garcia is founder/DM; only generic `legal@bglawoffice.com` verified.

### Batch 08 — leads 141–160

```text
Not Relevant                         13
Disqualified                          6
Gap Confirmed - Direct Email Missing  1
Qualified                             0
TOTAL                                20
```

Gap without direct email:

- David Bower / `davidbowerlawyer.com` — multiple materially different services share a general `/services` experience; only generic `contact@DavidBowerLawyer.com` verified.

### Batch 09 — leads 161–180

```text
Not Relevant  17
Disqualified   3
Qualified      0
TOTAL         20
```

All 20 were successfully applied to D1 and receipt-verified.

Notable Batch 09 live checks:

- Duffee + Eitzen — Family Law-only → `Not Relevant`.
- Timothy A. Jeffrey — current public evidence supports Criminal-only → `Not Relevant`.
- Law Offices of Mark T. Lassiter (`lomtl.com`) — Criminal Defense-only → `Not Relevant`.
- Kinder Law — Personal Injury/Wrongful Death-only → `Not Relevant`.

## Current Queue State

After Batch 09:

```text
new-production Ready remaining = 644
```

The next clean 20 have already been generated.

Current first lead:

```text
Texas Injury Lawyers Delivering Life-Changing Results - Grossman Law
injuryrelief.com
lead_id = ChIJm1MpQL8gTIYRd7iR1GQmiFo
```

These are the next production leads and should be treated as **Batch 10**.

## 40-Lead Mission Runner

A self-contained runner now exists for a fresh conversation:

```text
agents/40 leads runner.md
```

It instructs the next agent to:

```text
Batch 10 = current 20
→ finish all 20
→ persist/verify D1
→ wait for automatic refreshed next 20
→ Batch 11 = next 20
→ persist/verify D1
→ STOP after exactly 40 leads
```

The two batches must not be processed in parallel.

## Exact Next Action

For a new conversation, tell the agent:

```text
Read agents/40 leads runner.md and execute it exactly. Validate 40 leads as two sequential batches of 20. Do not start the second 20 until the first 20 are successfully applied to D1 and the next clean batch has refreshed.
```

Historical first-1,000 validation remains intentionally deferred.
