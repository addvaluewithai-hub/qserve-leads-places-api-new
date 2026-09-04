# 40 Leads Validation Runner

## Mission

Validate **exactly 40 new-production law-firm leads** for campaign `lawyers-us` as:

```text
20 leads
→ finish + persist + verify
→ then next 20 leads
→ finish + persist + verify
→ stop
```

**Do not run the 40 in parallel.**

This runner assumes you are the only validation agent operating this queue during the run. If another agent is simultaneously changing the same Ready queue, stop and avoid duplicate work.

The repository and D1 pipeline are already configured. **Do not redesign the workflows. Do not add scoring. Do not add hints. Do not build a crawler.** Your job is validation and persistence.

Repository:

```text
addvaluewithai-hub/qserve-leads-places-api-new
```

Campaign:

```text
lawyers-us
```

D1 is the source of truth.

---

# 1. Start Here

At the start of the new conversation, read this file and then immediately read the **current** production snapshot:

```text
agents/validation next clean URL batch.json
agents/validation next clean URL leads/01.json
...
agents/validation next clean URL leads/20.json
```

The per-lead files are the preferred working surface.

**Important:** the snapshot is live and can change. Never assume an old batch number, old Ready count, old first lead, or old lead list from another conversation.

For the first 20:

1. Read `01.json` through `20.json` in order.
2. Judge each lead manually from the complete clean homepage URL list.
3. Use live-site research only where the clean URLs are not enough.
4. Produce one decision JSON containing exactly those 20 lead IDs.
5. Commit that decision file.
6. Wait for the D1 apply workflow to finish successfully.
7. Verify the receipt contains all 20 matching lead IDs and statuses.
8. Only then re-read the newly refreshed `01.json` through `20.json` for the second batch.

Repeat once, then stop after 40 total.

---

# 2. Production Input Contract

The clean-URL files contain:

```text
lead_id
name
domain
website
clean_homepage_url_count
clean_homepage_urls
```

These URLs are:

- same-domain page paths collected from the rendered homepage
- deduplicated
- obvious assets/files removed
- **not scored**
- **not ranked**
- **not categorized**
- **not truncated to a top-N list**

Treat Crawl4AI as evidence collection only.

Do **not** infer qualification from URL count.

A site with 150 Personal Injury URLs can still be one narrow client journey and therefore `Not Relevant`.

---

# 3. Core ICP Rule

We are not looking for one forgotten service URL.

We are looking for firms that have **not yet made the architectural leap from one general service conversation to separate client journeys**.

The main question is:

> Are materially different main legal client journeys already separated into focused destinations?

A missing page matters only when it is evidence of a broader consolidated architecture problem.

---

# 4. Manual Decision Logic

## A. `Not Relevant`

Use this when the firm is essentially one narrow client journey, even if it has many subpages.

Typical examples:

- Personal Injury-only
- Criminal Defense-only
- Family Law-only
- Bankruptcy-only
- Immigration-only
- DWI/traffic-only
- another similarly narrow single-practice family

Do not call a PI firm mature merely because it has Car Accident, Truck Accident, Motorcycle Accident, Wrongful Death, Slip & Fall, etc. Those can still be one injury journey.

Typical reason:

```text
manual_clean_url_audit_single_narrow_journey
```

---

## B. `Disqualified`

Use this when the firm has multiple materially different main services **and already separates them into focused destinations**.

Examples:

```text
Criminal Defense -> dedicated page
Family Law -> dedicated page
Immigration -> dedicated page
Personal Injury -> dedicated page
Estate Planning -> dedicated page
```

or:

```text
Business Law -> dedicated page
Commercial Litigation -> dedicated page
Estate Planning -> dedicated page
Real Estate -> dedicated page
```

A single missing or weak secondary service on an otherwise mature multi-practice site is still usually `Disqualified`.

Do not hunt isolated forgotten URLs.

Typical reason:

```text
manual_clean_url_audit_mature_architecture
```

---

## C. Real gap candidate

Continue to live validation when:

- the firm explicitly offers multiple materially different main services
- several of those services still share the homepage, one general Services page, one Practice Areas page, or another shared/general destination
- the site does not already demonstrate mature separate-service architecture as the dominant pattern

Examples:

```text
Family Law + Criminal Law + Personal Injury
all on /services
```

or:

```text
Immigration + Personal Injury
both presented only on homepage
```

This is the campaign ICP.

---

## D. `Needs Review`

Use only when a material fact cannot be resolved safely, such as:

- conflicting current-site evidence about whether a service is actually offered
- ambiguous architecture where a reasonable reviewer could go either way
- site identity/domain cannot be resolved confidently

Do not force a Qualified or Disqualified result when key evidence is genuinely unclear.

---

# 5. When to Live-Check

Do **not** open every website by default.

Live-check when the clean homepage evidence is:

- zero links
- generic only (`/`, `/services`, `/practice-areas`, etc.)
- ambiguous
- inconsistent with the business identity
- showing a robot/challenge/DNS/stale/hijacked domain
- potentially a real architecture-gap candidate

For a possible gap, live validation must establish both:

1. the selected service is explicitly offered now, and
2. no reasonable focused destination exists for it **while the overall site remains consolidated rather than mature**.

Useful checks:

- homepage
- navigation
- Services / Practice Areas
- relevant service links
- footer
- internal links/buttons
- sitemap/site-restricted search when useful

**Search absence alone never proves page absence.**

Do not infer a service from an attorney biography alone.

---

# 6. Architecture Gate Before Contact Research

Before researching an owner or email, all of these must be true:

```text
service explicitly offered = yes
meaningful main service = yes
no reasonable focused destination = yes
overall site not already mature = yes
gap represents broader shared/general architecture problem = yes
```

If the site is mature, stop and mark `Disqualified`.

If it is one narrow journey, stop and mark `Not Relevant`.

**Owner/email research is always last.**

---

# 7. Decision Maker + Email Rules

Only after a real gap passes.

Decision-maker priority:

1. Owner / Founder
2. Managing Partner
3. Named Partner
4. Managing Attorney
5. Solo Attorney / Principal
6. another clearly senior buyer

Qualified requires a **direct public email belonging to that exact person**.

Accept:

- direct email on official firm site
- direct email in credible public professional/court/government material clearly tied to that person

Reject:

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

Also reject guessed email patterns and private/leaked databases.

If gap confirmed but no owner/DM can be established:

```text
Gap Confirmed - Owner Missing
```

If owner/DM exists but no direct public verified personal email:

```text
Gap Confirmed - Direct Email Missing
```

If gap + decision maker + direct public verified personal email all exist:

```text
Qualified
qualified = true
```

`Qualified` does not mean Contacted.

---

# 8. Outreach Draft for Qualified Leads

Qualified leads require an outreach draft persisted with the decision.

Target roughly 130–160 words.

Structure:

1. real observation from the current site
2. explain that materially different clients are sharing one general website conversation
3. explain why a focused page gives that client a clearer journey
4. mention focused Google context and clearer AI context as secondary benefits
5. explain why this service is the first mockup example
6. soft CTA

Default ending:

```text
I’m putting together a quick mockup to show you what I mean. I’ll send it over in the next couple of days.

If you’d rather I didn’t, just let me know.
```

No ranking guarantees. No indexing promises. No hard call-booking CTA.

---

# 9. Canonical Statuses

Use only these:

```text
Ready for Validation
Needs Review
Not Relevant
Disqualified
Gap Confirmed - Owner Missing
Gap Confirmed - Direct Email Missing
Qualified
```

---

# 10. Decision File Format

For each group of 20, create **one new JSON file** under:

```text
agents/validation audit decisions/
```

Do **not** assume the next numeric `batch-XX.json` filename is free. Other conversations/agents may have advanced the queue.

To avoid collisions, prefer a unique filename such as:

```text
run40-YYYYMMDD-HHMM-part-1.json
run40-YYYYMMDD-HHMM-part-2.json
```

Do not overwrite an existing decision file.

The workflow accepts any changed `*.json` in that folder.

Top-level shape:

```json
{
  "campaign_id": "lawyers-us",
  "audit_mode": "manual_clean_homepage_urls_only",
  "decisions": [
    ... exactly 20 decisions ...
  ]
}
```

Basic non-gap decision:

```json
{
  "slug": "01-example-firm",
  "lead_id": "PLACE_ID_HERE",
  "final_status": "Not Relevant",
  "qualified": false,
  "qualification_reason": "manual_clean_url_audit_single_narrow_journey",
  "campaign_notes": "Complete clean homepage URL review shows the firm is limited to one narrow Personal Injury client journey despite multiple injury subpages.",
  "service_gap_evidence": [],
  "contacts": []
}
```

Qualified decision shape:

```json
{
  "slug": "02-example-firm",
  "lead_id": "PLACE_ID_HERE",
  "final_status": "Qualified",
  "qualified": true,
  "qualification_reason": "architecture_gap_confirmed_direct_dm_email_verified",
  "campaign_notes": "Concise reproducible explanation of architecture, gap, owner and email evidence.",
  "service_gap_evidence": [
    {
      "service_name": "Selected Service",
      "status": "Gap Confirmed",
      "service_offered_evidence": "Exact current-site evidence that the firm offers it.",
      "dedicated_page_url": null,
      "validation_method": "Manual full clean-homepage-URL audit + official live-site validation",
      "notes": "Why no reasonable focused destination exists and why the overall architecture is still consolidated."
    }
  ],
  "contacts": [
    {
      "person_name": "Decision Maker",
      "role": "Owner / Founder",
      "email": "person@firm.com",
      "is_owner": true,
      "is_decision_maker": true,
      "is_direct_email": true,
      "is_publicly_verified": true,
      "evidence_source": "Public source tying the email directly to this person.",
      "notes": "Not guessed; direct individual email."
    }
  ],
  "outreach_draft": {
    "selected_service": "Selected Service",
    "subject": "A thought on your Selected Service page",
    "body": "Full outreach email here."
  }
}
```

For `Gap Confirmed - Direct Email Missing`, keep the confirmed service-gap evidence, save the owner/DM contact if known, but do not mark Qualified and do not invent an email.

Recent decision files in the same directory can be used as schema examples only. Do not copy their lead decisions.

---

# 11. What Happens After You Commit 20

This workflow is already configured:

```text
.github/workflows/validation-audit-apply-decisions.yml
```

A commit to:

```text
agents/validation audit decisions/*.json
```

will automatically:

1. require exactly 20 decisions
2. upsert `service_gap_evidence`
3. upsert `lead_contacts`
4. append outreach draft JSON into campaign notes when present
5. update `campaign_leads.status`, `qualified`, reason and notes in D1
6. write:

```text
agents/validation audit apply receipt.json
```

7. query updated D1
8. refresh:

```text
agents/validation next clean URL batch.json
agents/validation next clean URL leads/01.json ... 20.json
```

all inside the same workflow run.

No manual D1 SQL is normally required.

---

# 12. Verification Gate Between the Two 20s

After Part 1 is committed:

**Do not start Part 2 yet.**

Verify:

```text
workflow = success
receipt contains exactly 20 entries
receipt lead IDs match your Part 1 lead IDs
receipt statuses match your decisions
```

Then re-fetch the newly generated clean URL files.

The second 20 must come from the **refreshed snapshot after Part 1**, not from a preloaded list.

If the workflow fails, fix/retry the current 20 first. Never advance with an unpersisted batch.

After Part 2, perform the same verification and then stop.

---

# 13. 40-Lead Completion Checklist

Do not finish until all are true:

- [ ] First 20 reviewed sequentially from full clean homepage URL lists.
- [ ] Live checks performed only where needed.
- [ ] No scoring/hints used as decision logic.
- [ ] Contact research happened only for real gap candidates.
- [ ] Part 1 decision JSON has exactly 20 decisions.
- [ ] Part 1 workflow succeeded.
- [ ] Part 1 receipt verified.
- [ ] Second 20 loaded only after Part 1 refresh.
- [ ] Second 20 reviewed sequentially.
- [ ] Part 2 decision JSON has exactly 20 decisions.
- [ ] Part 2 workflow succeeded.
- [ ] Part 2 receipt verified.
- [ ] Exactly 40 leads total were processed.
- [ ] No third batch started.

At the end, report concise counts across the 40:

```text
Not Relevant
Disqualified
Needs Review
Gap Confirmed - Owner Missing
Gap Confirmed - Direct Email Missing
Qualified
```

List any Qualified firms with:

```text
firm
domain
selected service
decision maker
direct public verified email
```

---

# Final Guardrails

- Do not equate many URLs with mature architecture.
- Do not qualify a single missing page on an otherwise mature site.
- Do not treat PI subtypes as separate materially different client journeys by default.
- Do not infer services from attorney bios alone.
- Do not use search absence alone to prove page absence.
- Do not research emails before the architecture gap passes.
- Do not accept generic or guessed emails.
- Do not proceed to the next 20 until the current 20 are persisted and verified in D1.
- Do not process more than 40 leads in this run.

## One-line operating philosophy

> Read all clean homepage URLs, judge the architecture yourself, live-check only ambiguity or real candidates, persist 20, verify, then repeat once.
