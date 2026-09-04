# Validation Runner

## Purpose

This runner validates US law-firm leads for the Service-Page Gap campaign and writes the first outreach email.

The campaign is **not** looking for any isolated missing service page.

The real target is a firm that still makes materially different legal clients share the same general website conversation because the firm has **not yet adopted a mature separate-service-page architecture**.

> **We are selling the concept of separate client journeys, not pointing out one forgotten URL.**

A firm that already uses dedicated service pages extensively is usually **not a fit for this campaign**, even if one secondary service is missing a focused page. That firm already understands and applies the concept we are trying to introduce.

---

# 1. Source of Truth & Persistence

## D1 is authoritative

The validation state belongs to the lead in D1. `agents/validation runner last update.md` is only a human-readable handoff.

Normal queue:

```text
campaign_leads.campaign_id = lawyers-us
AND campaign_leads.status = Ready for Validation
AND campaign_leads.qualified = 0
```

Do not re-run finalized leads unless explicitly queued for re-review.

## Table ownership

### `leads`
Canonical business identity only.

### `campaign_leads`
Fast answer to: has this lead been worked and where is it now?

Persist at minimum:
- campaign_id
- lead_id
- status
- qualified
- qualification_reason
- notes
- crm_updated_at

### `service_gap_evidence`
Reproducible proof behind the website-architecture decision.

Persist meaningful services evaluated, including:
- campaign_id
- lead_id
- service_name
- status
- service_offered_evidence
- dedicated_page_url when one exists
- validation_method
- notes
- validated_at

### `lead_contacts`
Decision-maker and direct-public-email evidence.

### Outreach draft
The subject/body must be recoverable with the lead. Prefer a dedicated outreach-draft table; otherwise store a clearly delimited structured block in `campaign_leads.notes`.

## Canonical statuses

```text
Ready for Validation
Needs Review
Not Relevant
Disqualified
Gap Confirmed - Owner Missing
Gap Confirmed - Direct Email Missing
Qualified
```

`Qualified` means outreach-ready, not contacted.

## Write-after-each-lead rule

A lead is not finished until its final status and material evidence are persisted in D1.

After every finalized lead:
1. Update `campaign_leads.status` and `qualified`.
2. Persist service evidence.
3. Persist contact evidence only if contact research was reached.
4. Persist outreach subject/body if written.
5. Save a concise qualification reason.
6. Only then advance to the next lead.

---

# 2. Non-Negotiable Rules

1. Work only with services the firm **explicitly says it handles**.
2. Do not infer practice areas from attorney background, credentials or general capability.
3. Search results alone can never prove page absence.
4. The live website is the source of truth for architecture.
5. Do not hunt micro-subservice gaps inside a substantial parent-service page.
6. **Do not qualify an isolated missing page on a site that already has mature separate-service architecture.**
7. Client experience comes first; Google and AI are secondary benefits.
8. No ranking guarantees or indexing-time promises.
9. If an important fact is unclear, use `Needs Review`.
10. Email research happens only after the architecture and service gates pass.
11. Qualified requires a direct public email for the actual decision maker.
12. Reject generic inboxes such as `info@`, `contact@`, `office@`, `admin@`, `hello@`, `team@`, `intake@`, etc.
13. Never guess an email pattern.
14. Preserve evidence for every material conclusion.

---

# 3. Workflow

## Step 0 — Load the Lead

Load from D1:
- firm name
- domain
- lead / Place ID
- city/state if known
- campaign status and qualified flag
- prior notes
- existing service-gap evidence
- existing contacts
- homepage-link evidence when available

Prior notes are context, not current proof. Re-check the live site for material conclusions.

---

## Step 1 — Understand the Firm

Inspect the actual website before looking for a gap.

At minimum check:
- homepage
- main navigation
- Services / Practice Areas
- relevant service sections
- footer
- service buttons / Learn More links
- About / Attorneys when useful
- internal links
- sitemap when useful

Capture:
- main services explicitly offered
- where each service appears
- whether major services share one broad page
- which services already have dedicated pages
- whether service buttons route to a general page
- the overall architecture pattern

---

# Step 2 — Architecture Maturity Gate (MANDATORY)

This gate comes **before** hunting for an individual missing page.

Ask:

> Does this firm already clearly understand and implement the separate-service-page concept across its website?

### Mature architecture signals

A firm is usually **Disqualified for this campaign** when several of these are true:

- Most meaningful main services already have dedicated pages.
- Main navigation exposes many service-specific destinations.
- Each practice area has its own client-specific copy, CTA and structure.
- The site contains deep service hierarchies / subservice pages.
- The firm has clearly invested in intentional service-by-service SEO/content architecture.
- A single missing or underdeveloped service is an exception inside an otherwise mature system.

### Critical interpretation

**Do not qualify a firm just because Service X is the one exception.**

Example:

```text
Car Accident -> dedicated page
Truck Accident -> dedicated page
Workers' Comp -> dedicated page
Wrongful Death -> dedicated page
Slip & Fall -> dedicated page
Medical Malpractice -> only mentioned in articles
```

This is **not automatically a campaign opportunity**. The firm already understands separate service pages. Medical Malpractice may be a content gap, but this campaign is selling the architecture concept itself.

Default outcome for a clearly mature site:

```text
status = Disqualified
qualified = 0
reason = Separate-service architecture already mature; isolated missing page is not the campaign ICP.
```

### What we actually want

Strong campaign fit looks more like:

- several materially different main services share one homepage / Services / Practice Areas page
- a one-page site with multiple main practice areas
- repeated service cards or sections that all lead to the same general destination
- little or no evidence that the firm has adopted separate client journeys
- only one or two incidental dedicated pages while most major services remain consolidated

### Mixed architecture

If the site has a small number of dedicated pages but the **dominant pattern is still consolidated**, it may remain valid.

The test is not mathematical page counting. Ask:

> Would a reasonable reviewer say this firm already knows and routinely applies the separate-page strategy we are trying to pitch?

If **Yes** -> Disqualified.
If **No** -> continue.
If genuinely ambiguous -> Needs Review.

---

## Step 3 — Identify a Meaningful Main-Service Gap

Only after the firm passes the Architecture Maturity Gate.

A strong gap is a meaningful main service that is explicitly offered but still lives only in:
- the homepage
- a general Services page
- a broad Practice Areas page
- a one-page site
- a shared/general destination

A page counts as dedicated based on its content, not its URL shape.

Reject micro-gaps such as:
- Child Support under a strong Family Law page
- Green Cards under a strong Immigration page
- Wills under a strong Estate Planning page
- equivalent narrow subtopics

---

## Step 4 — Think in Client Conversations

Ask:

> Who is the person looking for this service, and what do they need to understand when they arrive?

The point is practical: different legal matters can need different messaging, hierarchy, imagery, CTA, tone and visual emphasis.

Do not write amateur psychology.

---

## Step 5 — Choose the Best First Mockup Service

The selected service is the **first example of a broader structural opportunity**, not the only missing page.

Good reasons to choose it:
- client journey is clearly different
- existing content can support a focused page
- it is a meaningful main service
- it is easy to demonstrate visually/structurally
- a Learn More path currently lands on a general page

Bad reason:
- it happens to be the only service without a page on an otherwise mature site

---

## Step 6 — Internal Validation Note

Before contact research, record:

```text
Architecture maturity: Immature / Mixed-but-valid / Mature
Architecture evidence:
Main services explicitly offered:
Pages checked:
Service chosen for mockup:
Service evidence:
Why this represents a broader structural opportunity:
Why the client conversation is materially different:
Validation status:
```

For Qualified or Needs Review decisions, evidence must explain both:
1. why the selected service lacks a reasonable focused destination, and
2. why the **firm as a whole has not already adopted mature separate-service architecture**.

---

# Step 7 — Validation Gate

Before contact research, all must be true:

1. Service explicitly offered — **Yes**
2. Live site inspected — **Yes**
3. Selected service lacks a reasonable dedicated destination — **Yes**
4. Service is meaningful, not a micro-subservice — **Yes**
5. **Overall site is not already mature in separate-service architecture — Yes**
6. Selected service can be presented as the first example of a broader structural issue — **Yes**
7. Genuine live-site personalization exists — **Yes**
8. Client-experience argument works before Google/AI — **Yes**
9. No ranking/indexing guarantee is needed — **Yes**

If #5 fails, the lead is `Disqualified` even when #3 is true.

If any important answer is unclear:

```text
status = Needs Review
qualified = 0
```

If the architecture/service gate fails, stop. Do **not** research decision-maker email.

---

# Step 8 — Identify the Decision Maker

Only after the website opportunity passes validation.

Priority:
1. Owner / Founder
2. Managing Partner
3. Named Partner
4. Managing Attorney
5. Solo Attorney / Principal
6. other clearly senior buyer

Save name, title, evidence source and why this person is the likely buyer.

If no realistic decision maker can be established:

```text
status = Gap Confirmed - Owner Missing
qualified = 0
```

---

# Step 9 — Find a Direct Public Decision-Maker Email

Search official site/assets first, then credible public professional sources.

Accept only a public address clearly attributable to the selected decision maker.

Reject:
- generic inboxes
- forms only
- guessed patterns
- leaked/private databases
- assistant/reception/intake addresses

If the gap is confirmed but no acceptable direct public email exists:

```text
status = Gap Confirmed - Direct Email Missing
qualified = 0
```

---

# Step 10 — Write the Email

Target: roughly 130–160 words.

Order:
1. real personalized site observation
2. explain the broader shared-client-conversation problem
3. explain why separate pages create clearer client journeys
4. three short benefits: client relevance, focused Google context, clearer AI context
5. explain why the selected service is the first mockup example
6. soft CTA

Default CTA:

> I’m putting together a quick mockup to show you what I mean. I’ll send it over in the next couple of days.
>
> If you’d rather I didn’t, just let me know.

No hard sell. No call-booking request. No ranking promises.

Persist subject/body before marking Qualified.

---

# Step 11 — Final Record

Every finalized lead must be reproducible from D1.

Minimum record:

```text
Firm
Domain / lead ID
Architecture maturity decision
Architecture evidence
Main services explicitly offered
Pages checked
Selected mockup service
Service evidence
Why this represents broader structural opportunity
Decision maker + evidence
Direct public email + source
Subject
Email body
Canonical status
Qualified flag
Qualification reason
Reviewer notes
Validation time
```

---

# Quality-Control Checklist

A lead can be **Qualified** only when all are true:

- [ ] Main services were inspected on the live site.
- [ ] The firm does **not** already have mature separate-service architecture.
- [ ] The problem is broader than one isolated forgotten page.
- [ ] Selected service is explicitly offered.
- [ ] No reasonable dedicated page exists for it.
- [ ] It is a meaningful main service, not a micro-gap.
- [ ] The service is the first example of a broader consolidated-architecture problem.
- [ ] Search results were not used alone to prove absence.
- [ ] Client experience is the primary argument.
- [ ] Decision maker is publicly evidenced.
- [ ] Direct public email belongs to that exact person.
- [ ] Email is not generic or guessed.
- [ ] Evidence and outreach draft are persisted.
- [ ] D1 final state is saved before advancing.

---

# Anti-Patterns

Immediately reject/correct work that:

- finds one missing service page on an otherwise mature service-by-service site and calls it Qualified
- treats a content gap as proof the firm needs the separate-pages concept
- counts URLs without judging overall architecture maturity
- uses search snippets alone to prove absence
- hunts micro-subservices
- researches email before the architecture gate passes
- accepts generic or guessed email
- starts outreach with SEO rather than client experience
- makes ranking/indexing promises
- finishes work in chat without persisting it

---

# Session Rules

At session start:
1. Read `agents/validation runner last update.md`.
2. Read current D1 next-lead state.
3. Skip finalized leads unless explicitly re-reviewing.
4. Preserve prior evidence.
5. Note material live-site changes instead of silently overwriting conclusions.

At session end:
1. Update the handoff file.
2. Record counts and exact stop point.
3. Record Qualified / Needs Review / Disqualified outcomes.
4. Record new edge cases or rule changes.
5. Record the exact next action.

---

# Core Philosophy

> We are looking for firms that have **not yet made the architectural leap** from one general service conversation to separate client journeys.

A missing page matters only when it is evidence of that broader problem.

If the firm already demonstrates that it understands and routinely implements separate service pages, it is not the right prospect for this campaign—even if one service could still use another page.
