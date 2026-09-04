# 40 Leads Runner

## Mission

Validate **exactly 40 new-production law-firm leads** for campaign `lawyers-us` as **two sequential batches of 20**.

This is a production execution runner, not a research experiment.

```text
Batch 10 = 20 leads
→ finish all 20
→ persist all 20 to D1
→ verify the D1 apply receipt + refreshed next batch
→ only then start Batch 11

Batch 11 = next 20 leads
→ finish all 20
→ persist all 20 to D1
→ verify the D1 apply receipt
→ STOP after 40 total leads
```

**Do not run the two batches in parallel.**

The agent should be able to execute this file directly. Do not ask the user to restate the ICP or workflow unless a genuine technical blocker makes execution impossible.

---

# 1. Current Starting Point

Campaign:

```text
lawyers-us
```

Repository:

```text
addvaluewithai-hub/qserve-leads-places-api-new
```

Completed production validation through:

```text
batch-09.json
```

Current new-production Ready count at handoff:

```text
644
```

Current first lead in the next clean-URL batch:

```text
Texas Injury Lawyers Delivering Life-Changing Results - Grossman Law
injuryrelief.com
lead_id = ChIJm1MpQL8gTIYRd7iR1GQmiFo
```

The next 20 are already generated in:

```text
agents/validation next clean URL batch.json
agents/validation next clean URL leads/01.json
...
agents/validation next clean URL leads/20.json
```

Start with those files. They are **Batch 10**.

After Batch 10 is applied to D1, the same GitHub Actions workflow automatically regenerates those paths with the next 20. Those refreshed files become **Batch 11**.

If another validator has changed the queue since this file was written, trust the **current contents** of `agents/validation next clean URL batch.json`, not the numeric count above. Never re-run already-finalized leads.

---

# 2. The Only Input Surface You Should Use First

For each lead, read its full file:

```text
agents/validation next clean URL leads/01.json ... 20.json
```

Each file contains:

- lead ID
- firm name
- domain / website
- **all clean same-domain page paths collected from the rendered homepage**

The clean URL collection removes obvious asset/file targets only.

It does **not** classify, score, rank, truncate, or decide anything.

## Critical: deprecated surfaces

Do **not** use these as decision logic:

- old scoring
- old hints such as `likely_mature`
- old service categorization
- old top-N structural links
- `agents/validation new crawl prescreen.json` as a qualification surface

The agent must judge the architecture manually from the complete clean URL list.

---

# 3. Core ICP — The Question You Are Actually Answering

We are **not** looking for any firm with one missing service page.

We are looking for firms that have **not yet made the architectural leap from one shared/general service conversation to separate client journeys**.

The key question is:

> Are materially different main legal client journeys already separated into focused destinations?

Not:

> Does the site have many service-looking URLs?

And not:

> Can I find one service without a page?

A missing page matters only when it is evidence of a broader consolidated architecture problem.

---

# 4. Status Logic — Get This Exactly Right

Canonical final statuses:

```text
Needs Review
Not Relevant
Disqualified
Gap Confirmed - Owner Missing
Gap Confirmed - Direct Email Missing
Qualified
```

## `Not Relevant`

Use when the firm is essentially **one narrow client journey**, even if it has dozens or hundreds of focused pages.

Common examples:

- Personal Injury only
- Criminal Defense only
- Family Law only
- Immigration only
- Bankruptcy only
- Tax only
- Workers' Compensation only

Examples inside one PI journey:

```text
Car Accidents
Truck Accidents
Motorcycle Accidents
Wrongful Death
Dog Bites
Premises Liability
Medical Malpractice
Work Injuries
```

A PI-only firm with 150 URLs is usually **Not Relevant**, not Disqualified.

Likewise, a Criminal Defense firm with DWI, drugs, assault, sex crimes, federal defense, fraud, weapons, etc. is usually one criminal-defense journey.

## `Disqualified`

Use when the firm has **materially different main services and already separates them into focused destinations**.

Examples:

```text
/criminal-defense
/personal-injury
/family-law
/immigration
```

or:

```text
/estate-planning
/business-litigation
/employment-law
/personal-injury
```

If the firm already routinely applies separate client/service pages, it is Disqualified even if you find one isolated secondary service without a page.

**Do not hunt forgotten URLs on a mature site.**

## `Needs Review`

Use only when a material fact cannot be resolved safely, for example:

- current offered services conflict across official pages
- site identity/domain is unclear
- architecture remains genuinely ambiguous after a reasonable live check

Do not force a binary answer when the evidence is genuinely unclear.

## Gap statuses

Only continue to gap/contact research when:

1. the firm offers multiple materially different main services, and
2. several of those services still share a homepage/general Services/Practice Areas experience, and
3. separate-page architecture is not already dominant.

Then choose one meaningful main service as the first mockup example.

If the gap is confirmed but no actual owner/decision maker can be established:

```text
Gap Confirmed - Owner Missing
```

If the decision maker is known but no **direct public individual email** can be verified:

```text
Gap Confirmed - Direct Email Missing
```

## `Qualified`

Qualified requires **all** of these:

```text
real broader architecture gap
+ meaningful selected service gap
+ actual owner / decision maker
+ direct public verified individual email for that exact person
+ outreach draft persisted
```

Qualified does **not** mean contacted.

---

# 5. Manual Review Procedure for Each Lead

## Step A — Read every clean homepage URL

Read the whole URL list for the lead.

Do not decide from URL count alone.

Ask:

1. What appear to be the firm's materially different main legal conversations?
2. Are those different conversations already represented by separate focused destinations?
3. Or do the URLs mostly represent subtopics/geographies inside one narrow practice?

### Fast examples

This is usually `Not Relevant`:

```text
/personal-injury
/car-accidents
/truck-accidents
/motorcycle-accidents
/wrongful-death
/dog-bites
```

This is usually `Disqualified`:

```text
/criminal-defense
/family-law
/personal-injury
/business-law
```

This deserves deeper checking:

```text
/services
/about
/contact
```

with homepage copy showing several different practices.

---

## Step B — Decide whether a live check is needed

Do a live/public-site check when the clean URL evidence is:

- zero links
- generic only (`/services`, `/practice-areas`, `/about`, etc.)
- blocked / robot challenge
- DNS/stale-domain issue
- ambiguous about materially different services
- potentially redirected to a new domain/property

Also live-check any promising gap before proving page absence.

### Zero links rule

```text
0 clean URLs ≠ opportunity
```

It only means Crawl4AI evidence is inadequate. Check the current site or credible current public evidence.

### Current identity rule

If the domain:

- redirects
- changed firms
- is stale
- is hijacked/spam/gambling
- has moved to a new official law-firm domain

verify the current identity before classifying.

---

## Step C — Architecture Maturity Gate

Before looking for a specific missing page, ask:

> Would a reasonable reviewer say this firm already knows and routinely applies separate service/client-journey pages?

If yes:

```text
Disqualified
```

If the site is essentially one narrow practice:

```text
Not Relevant
```

If no, and several materially different main services remain consolidated:

```text
continue to gap validation
```

If unclear:

```text
Needs Review
```

### Important mixed-architecture rule

A few dedicated pages do not automatically make the site mature.

If several materially different main services still live in a shared/general experience and separate-page adoption is not dominant, the lead can still fit.

But one isolated missing page on an otherwise mature service-by-service site does **not** fit.

---

# 6. Gap Validation Rules

Only use services the firm **explicitly says it handles**.

Never infer a service only because an attorney bio says the lawyer has experience in it.

A valid selected gap should be a meaningful main service such as:

- Family Law
- Criminal Defense
- Personal Injury
- Immigration
- Business Litigation
- Employment Law
- Estate Planning / Probate
- Civil Rights

Do not hunt micro-subservice gaps such as Child Support under a good Family Law page or Green Cards under a good Immigration page.

A page counts as dedicated based on its actual content and client purpose, not only its URL slug.

## Absence proof

Search absence alone is **never** sufficient proof that a page does not exist.

Use a combination of:

- complete clean homepage links
- live navigation
- service cards/buttons
- general Services / Practice Areas page
- footer
- relevant internal links
- site-restricted/public search when useful

If you cannot prove absence safely, use `Needs Review` rather than manufacturing a gap.

---

# 7. Contact Research Comes LAST

Do not research owner/email for:

- Not Relevant
- Disqualified
- ordinary Needs Review cases where the architecture gate has not passed

Only do it after a real architecture gap is confirmed.

Decision-maker priority:

1. Owner / Founder
2. Managing Partner
3. Named Partner
4. Managing Attorney
5. Solo Attorney / Principal
6. another clearly senior buyer

## Direct email rule

Qualified requires a **public email attributable to that exact person**.

Accept examples:

```text
jane@firm.com
firstname.lastname@firm.com
personal legacy address clearly published by the firm for that attorney
```

Reject as direct email:

```text
info@
contact@
office@
admin@
hello@
team@
intake@
legal@
```

Never guess an email pattern.

Never qualify from a guessed address.

A generic verified firm inbox can be stored as evidence, but it produces:

```text
Gap Confirmed - Direct Email Missing
```

not Qualified.

---

# 8. Outreach Draft for Qualified Leads

For every Qualified lead, persist a short outreach draft, roughly 130–160 words.

Structure:

1. specific observation from the current site
2. explain that materially different clients are sharing the same general service experience
3. explain why a focused page gives that client a clearer journey
4. mention Google focused-page context secondarily
5. mention clearer AI context secondarily
6. explain why the selected service is the first mockup example
7. soft CTA

Default close:

```text
I’m putting together a quick mockup to show you what I mean. I’ll send it over in the next couple of days.

If you’d rather I didn’t, just let me know.
```

Do not promise rankings, indexing speed, leads, or revenue.

Client experience comes first; Google/AI are supporting benefits.

---

# 9. How to Persist Each Batch

Do **not** create one workflow commit per lead.

After reviewing all 20 leads in the current batch, create one file:

For the first 20 of this mission:

```text
agents/validation audit decisions/batch-10.json
```

For the second 20:

```text
agents/validation audit decisions/batch-11.json
```

Use this top-level structure:

```json
{
  "campaign_id": "lawyers-us",
  "batch_number": 10,
  "audit_mode": "manual_clean_homepage_urls_only",
  "decisions": [
    ... exactly 20 decisions ...
  ]
}
```

Each decision should use:

```json
{
  "slug": "01-example-firm",
  "lead_id": "PLACE_ID_HERE",
  "final_status": "Not Relevant",
  "qualified": false,
  "qualification_reason": "manual_clean_url_audit_single_narrow_pi_journey",
  "campaign_notes": "Concise reproducible evidence for the decision.",
  "service_gap_evidence": [],
  "contacts": []
}
```

For a confirmed gap, populate `service_gap_evidence`:

```json
{
  "service_name": "Family Law",
  "status": "Gap Confirmed",
  "service_offered_evidence": "Official-site evidence that the firm explicitly offers the service.",
  "dedicated_page_url": null,
  "validation_method": "Manual full clean-homepage-URL audit + official live-site verification",
  "notes": "Why the service remains in the shared/general architecture and why this is broader than one forgotten URL."
}
```

For contact research, populate `contacts` with:

```json
{
  "person_name": "Jane Doe",
  "role": "Founder / Managing Attorney",
  "email": "jane@firm.com",
  "is_owner": true,
  "is_decision_maker": true,
  "is_direct_email": true,
  "is_publicly_verified": true,
  "evidence_source": "Official site / credible public source",
  "notes": "Why the email belongs to this exact decision maker."
}
```

For Qualified leads also include:

```json
"outreach_draft": {
  "selected_service": "Family Law",
  "subject": "A thought on your Family Law page",
  "body": "..."
}
```

Use recent files such as:

```text
agents/validation audit decisions/batch-07.json
agents/validation audit decisions/batch-08.json
agents/validation audit decisions/batch-09.json
```

as schema examples only. Do not copy their decisions into the new batch.

---

# 10. What Happens After You Commit a 20-Lead Decision File

The workflow is already configured:

```text
.github/workflows/validation-audit-apply-decisions.yml
```

A push to:

```text
agents/validation audit decisions/*.json
```

triggers one workflow that:

1. validates there are exactly 20 decisions
2. upserts service-gap evidence
3. upserts contact evidence
4. stores outreach draft in campaign notes when present
5. updates all 20 `campaign_leads` rows in D1
6. writes:

```text
agents/validation audit apply receipt.json
```

7. queries the updated D1 queue
8. refreshes:

```text
agents/validation next clean URL batch.json
agents/validation next clean URL leads/01.json ... 20.json
```

9. commits the receipt + refreshed next batch

## Mandatory verification before moving on

After committing Batch 10:

- verify the workflow completed successfully
- verify the receipt contains **20 rows** with `source_file = agents/validation audit decisions/batch-10.json`
- verify the clean URL batch changed to the next 20
- only then begin Batch 11

After committing Batch 11:

- verify workflow success
- verify the receipt contains **20 rows** from `batch-11.json`
- then stop; do not start Batch 12 in this mission

If the workflow fails for a technical reason, fix/retry the same batch. **Do not advance to the next 20 until D1 persistence succeeds.**

The apply operation is intended to be safe to re-run on the same decision batch if necessary.

---

# 11. Expected 40-Lead Cadence

## Batch 10

```text
Read current 01–20 files
→ manually classify all 20
→ live-check only zero/generic/ambiguous/promising-gap cases
→ contact research only for real gaps
→ create batch-10.json with exactly 20 decisions
→ commit
→ verify workflow success
→ verify 20-row D1 receipt
→ verify refreshed next clean 20
```

## Batch 11

```text
Read newly refreshed 01–20 files
→ repeat the same process
→ create batch-11.json with exactly 20 decisions
→ commit
→ verify workflow success
→ verify 20-row D1 receipt
→ STOP
```

Do not pre-read or process Batch 11 while Batch 10 is still in progress.

Do not process 40 in one JSON file.

Do not create or apply the two batches in parallel.

---

# 12. Quality-Control Checklist Before Finalizing Any Lead

Ask:

- [ ] Did I read the complete clean homepage URL list?
- [ ] Did I avoid score/hint/category shortcuts?
- [ ] Is this truly multiple materially different client journeys, or just one narrow practice with many subpages?
- [ ] If it is one narrow journey, did I use `Not Relevant` rather than `Disqualified`?
- [ ] If multiple different journeys exist, are they already separately represented?
- [ ] If the site is mature, did I stop instead of hunting one missing URL?
- [ ] If URL evidence was zero/generic/ambiguous, did I live-check the current site?
- [ ] Did I verify current domain/firm identity if there was a redirect, stale site, or challenge screen?
- [ ] For a gap, is the selected service explicitly offered?
- [ ] Is the gap meaningful rather than a micro-subservice?
- [ ] Did I avoid using search absence alone as proof?
- [ ] Did I delay owner/email research until after the architecture gate passed?
- [ ] If Qualified, does the direct public email belong to the actual decision maker?
- [ ] Is the email neither generic nor guessed?
- [ ] If Qualified, is the outreach draft persisted?
- [ ] Is the final reasoning reproducible from `campaign_notes` and evidence fields?

---

# 13. Important Learned Edge Cases

These rules came from real production errors and corrections. Keep them.

### Many URLs can still be one journey

A 100-page PI site is usually still `Not Relevant`.

A 100-page Criminal Defense site is usually still `Not Relevant`.

Do not confuse depth with multi-practice maturity.

### A general `/services` page can be a strong candidate

If the official site explicitly offers, for example:

```text
Family Law
Criminal Law
Personal Injury
```

and all three remain on the same `/services` page, that is exactly the type of architecture gap we want.

### One service missing on a mature site is not enough

If a site has focused Criminal, PI, Family, Business, Estate, etc. pages and one service is not separately surfaced, the concept is already adopted. Usually `Disqualified`.

### Generic email is not Qualified

A real gap + founder + `legal@firm.com` is:

```text
Gap Confirmed - Direct Email Missing
```

not Qualified.

### Stale/blocked sites require identity checking

Do not infer opportunity from a robot screen, DNS failure, zero links, or dead domain.

---

# 14. End-of-Mission Output

After Batch 11 is successfully persisted, give the user a concise report containing:

- `40/40` completed
- Batch 10 status counts
- Batch 11 status counts
- combined 40-lead counts
- names of any new Qualified leads
- names of any `Gap Confirmed - Direct Email Missing` / `Owner Missing` leads
- any `Needs Review` leads
- confirmation that both batches were applied to D1
- current remaining new-production Ready count from the refreshed clean batch
- exact next batch number (`batch-12`) but **do not start it**

Also update:

```text
agents/validation runner last update.md
```

with the two completed batches, notable edge cases, current remaining count, and the exact next action.

---

# 15. Infrastructure Status

Everything required for this 40-lead run is already wired:

- clean homepage URL evidence exists
- per-lead 01–20 files exist
- no score/hint decision surface is needed
- batch decision JSON schema is established
- GitHub Actions applies the 20 decisions to D1
- the same workflow refreshes the next clean 20 after D1 update
- receipt verification is available

**Do not redesign the workflow during this mission unless a real technical failure blocks execution.**

If something fails, make the smallest safe repair, re-run the same batch, verify persistence, then continue.

---

# Final Instruction to the Agent

Start now with the current:

```text
agents/validation next clean URL leads/01.json ... 20.json
```

Treat them as **Batch 10**.

Finish and persist those 20 first.

Only after successful D1 receipt + automatic refresh, process the next 20 as **Batch 11**.

Then stop after exactly **40 validated leads**.
