# Validation Runner Last Update

> Required handoff record between validation sessions.
> Read this before validation work. D1 is the source of truth.

## Last Updated

- Date: 2026-09-04
- Runner / session: ChatGPT validation runner — 100 new-production leads, 5 batches x 20
- Repository / dataset: `addvaluewithai-hub/qserve-leads-places-api-new` / D1 `lawyers-us`
- Campaign: `lawyers-us`

## Current Operating Mode

Continue prioritizing **new production leads with existing Crawl4AI homepage evidence**.

Selection rule:

```text
campaign_id = lawyers-us
status = Ready for Validation
qualified = 0
qualification_reason = working_set_ready_for_validation
```

After the completed 100-lead run, D1 reports:

```text
new-production Ready for Validation remaining = 724
```

## Crawl4AI-First Flow

Agent 1 / Crawl4AI is an evidence collector only:

```text
homepage only
→ render public page
→ collect same-domain page-like links
→ remove obvious asset/file targets
→ dedupe URLs
→ keep a short useful anchor
→ stop
```

No deep crawl, service classification, gap decision, or contact research belongs in Agent 1.

Agent 2 normal first pass:

```text
20 new-production Ready leads
→ compact `path | anchor` view
→ Architecture Maturity Gate
→ obvious mature sites can be Disqualified from sufficient crawl evidence
→ only promising / ambiguous / crawl-review leads get live-site deep validation
→ owner/email research only after a real architecture gap passes
```

Production contract:

```text
docs/CRAWL4AI_HOMEPAGE_EVIDENCE_CONTRACT.md
```

Compact snapshot:

```text
agents/validation new crawl prescreen.json
```

The snapshot workflow now refreshes automatically after each validation apply receipt, so the normal cadence is:

```text
validate 20
→ apply 20 to D1
→ automatic next compact 20 snapshot
→ repeat
```

## Completed 100-Lead Run

D1 verification file:

```text
agents/validation 100-run verification.json
```

Verification result: `PASS`

Exact D1 counts for the 100 processed leads:

```text
Disqualified                         88
Not Relevant                         6
Needs Review                         2
Gap Confirmed - Direct Email Missing 2
Qualified                            2
TOTAL                              100
```

All 100 result files were found, all 100 D1 rows were found, and zero of the 100 remain `Ready for Validation`.

## Qualified Leads From This 100

### Bruce Kaye PLLC

- Lead ID: `ChIJq4SPGS-ZToYRTYEC5f9S9rY`
- Domain: `brucekaye.com`
- D1: `Qualified`, qualified=1
- Architecture: Criminal Law + Entertainment Law + Wrongful Death share a general homepage rather than a mature service-page system
- Selected service: `Entertainment Law`
- Decision maker: Bruce Kaye
- Direct public email: `bruce@brucekaye.com`
- Outreach draft persisted in campaign notes

### Kelley Law Firm

- Lead ID: `ChIJjxRE8t2YToYRFGVqWHfrv4M`
- Domain: `kelleyfirm.com`
- D1: `Qualified`, qualified=1
- Architecture: public site is primarily a consolidated injury experience while the official owner profile explicitly describes Business Litigation work; no focused Business Litigation destination surfaced
- Selected service: `Business Litigation`
- Decision maker: Kevin Kelley — Attorney / Owner
- Direct public email: `kelley@kelleyfirm.com`
- Outreach draft persisted in campaign notes

## Strong Fits That Did Not Become Qualified

### Salvador Ongaro Law Offices

- Status: `Gap Confirmed - Direct Email Missing`
- Shared Practice Areas page combines Immigration, Personal Injury, Criminal Defense, and Divorce/Child Custody
- Selected gap: Immigration
- Decision maker: Salvador Ongaro — Managing Partner / CEO
- Only generic firm email was verified; no direct DM email

### Law Offices of William W. Black, P.C.

- Status: `Gap Confirmed - Direct Email Missing`
- Consolidated site combines multiple injury/wrongful-death matter types as sections rather than focused destinations
- Selected gap: Wrongful Death
- Decision maker: William W. Black
- No verified direct DM email

## Needs Review From This 100

- `landeroslegal.com` — crawl evidence sparse and live architecture could not be proven safely enough
- `matthewthomaslaw.com` — current homepage contains conflicting copy about whether Criminal Defense is actively offered alongside Immigration

## Important Findings From the 100-Lead Test

1. **20-by-20 works well.** It materially reduces unnecessary website opens while preserving review safeguards.
2. A high `signals` count is useful evidence of architecture maturity, but the hint is never a final decision.
3. `crawl_review` must not be interpreted as opportunity. Several zero-link/robot-challenge leads proved mature after live review.
4. A low-signal location page can hide mature service architecture elsewhere, so `candidate_deep_check` / `review_links` still require live verification.
5. Single-practice niche firms should be `Not Relevant` even when the site is consolidated if all matters are one core client journey.
6. Do not convert an ambiguous offered service into a gap; use `Needs Review`.

## Next Compact 20

The post-run snapshot refreshed successfully from D1.

- New-production Ready remaining: `724`
- Batch size: `20`
- First lead in next batch:
  - `Armstrong Law, PLLC`
  - domain: `armstronglawyer.com`
  - lead ID: `ChIJoXYdxJMhTIYR4T7Q4iKaLZ4`
  - Crawl hint: `likely_mature`

The next compact batch is already available at:

```text
agents/validation new crawl prescreen.json
```

## Exact Next Action

> Continue new-production validation with the current compact 20-lead snapshot. Process all 20, apply them to D1 in one batch commit, confirm the apply receipt, then use the automatically refreshed next compact 20. Keep the corrected Architecture Maturity Gate and all contact rules unchanged.

Historical first-1,000 validation remains intentionally deferred until the new-production flow is fully settled.

## Handoff Confirmation

- [x] 100 new-production leads processed as 5 x 20.
- [x] All five apply runs completed successfully.
- [x] D1 verification passed for all 100 IDs.
- [x] Exact status counts recorded.
- [x] Two Qualified leads persisted with direct public DM emails and outreach drafts.
- [x] Compact 20-lead snapshot flow is productionized.
- [x] Snapshot now auto-refreshes after each apply receipt.
- [x] Next compact 20 is already generated.
