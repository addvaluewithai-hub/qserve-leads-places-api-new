# Validation Runner

## Purpose

This runner validates US law-firm leads for the Service-Page Gap campaign and writes the first outreach email.

The job is **not** to find “a missing page.”

The job is to understand how the firm presents its main services, decide whether different legal clients are being forced to share the same general website conversation when one or more services deserve their own client-specific experience, select the strongest service as the first mockup example, and only then locate a direct public email for the relevant decision maker.

> **The gap is not “this service is missing a page.” The gap is that different legal clients are being asked to share the same conversation. The service we choose is simply the best first example.**

---

# Source of Truth, Persistence & Resume Rules

## D1 is the source of truth

The validation state belongs to the lead in D1. The handoff markdown file is only a session summary and resume aid; it is **not** the authoritative record of whether a lead has already been processed.

Before starting any lead, check its `campaign_leads` record for campaign `lawyers-us`.

Normal work queue:

```text
campaign_leads.campaign_id = lawyers-us
AND campaign_leads.status = Ready for Validation
```

Do not re-run a finalized lead merely because it appears in an old CSV, report, artifact, or handoff note.

If a lead already contains partial validation evidence, resume from the first unfinished stage instead of repeating completed work unless the live site changed materially.

## What each table owns

### `leads`

Canonical business identity only. Keep firm-level identity here; do not overload it with campaign-specific validation history.

### `campaign_leads`

This is the fast answer to: **Has this lead been worked, and where is it now?**

Store/update at minimum:

- `campaign_id`
- `lead_id`
- `status`
- `qualified`
- `qualification_reason`
- `notes`
- `crm_updated_at`

When supported by the live schema, also store `validated_at`.

### `service_gap_evidence`

This is the reproducible proof behind the service-page decision.

For every evaluated meaningful service, store:

- `campaign_id`
- `lead_id`
- `service_name`
- `status`
- `service_offered_evidence`
- `dedicated_page_url` when one exists
- `validation_method`
- `notes`
- `validated_at`

### `lead_contacts`

This owns decision-maker and direct-email evidence.

Store:

- person name
- role
- email
- owner / decision-maker flags
- direct-email flag
- publicly-verified flag
- evidence source
- verification time
- notes

### Outreach draft

The outreach draft must be recoverable with the lead; do not leave the only copy inside a chat session.

Preferred persistence target is a dedicated `lead_outreach_drafts` record keyed by `campaign_id + lead_id`, containing at least:

```text
campaign_id
lead_id
selected_service
contact_id or decision-maker identity
subject
body
created_at
updated_at
```

If that table is not yet present in the live D1 schema, temporarily store a clearly delimited structured outreach-draft block in `campaign_leads.notes`. Do not mark the lead fully persisted until the subject and body are recoverable from D1.

## Canonical campaign statuses

Use the production status names below in D1:

```text
Ready for Validation
Needs Review
Not Relevant
Disqualified
Gap Confirmed - Owner Missing
Gap Confirmed - Direct Email Missing
Qualified
```

Older runner wording maps as follows:

```text
Review  -> Needs Review
Reject  -> Disqualified
Not Qualified — No Direct Decision-Maker Email
        -> Gap Confirmed - Direct Email Missing
```

`Qualified` means outreach-ready. It does **not** mean contacted.

Actual outreach/contact lifecycle is separate and belongs in `outreach_suppression`.

## Write-after-each-lead rule

A lead is not considered finished until its final state and material evidence are persisted.

After every finalized lead:

1. Update `campaign_leads.status` and `qualified`.
2. Save service evidence in `service_gap_evidence`.
3. If contact research was reached, save decision-maker/email evidence in `lead_contacts`.
4. If an outreach email was written, persist its subject/body with the lead.
5. Save a concise `qualification_reason` and reviewer note.
6. Only then move to the next `Ready for Validation` lead.

This makes processing idempotent: returning to the same lead later should immediately show whether it is untouched, partially processed, finalized, or awaiting review.

---

## Non-Negotiable Rules

1. Work only with services the firm **explicitly says it handles**.
2. Do not infer a practice area from attorney background, credentials, or general capability.
3. Never use search-engine results alone to prove that a dedicated page does not exist.
4. Do not hunt for tiny subservice gaps when a substantial main-service page already exists.
5. Do not imply that only the selected service deserves a dedicated page.
6. Client experience comes first. Google and AI are secondary supporting benefits.
7. Do not make ranking guarantees or indexing-time promises.
8. If an important validation point is unclear, use **Needs Review**, not Qualified.
9. **Email research happens last, only after the service-page opportunity has passed validation.**
10. A lead cannot become Qualified without a **direct public decision-maker email**.
11. Generic inboxes are not acceptable: no `info@`, `contact@`, `office@`, `reception@`, `admin@`, `support@`, `hello@`, `team@`, `intake@`, or equivalent role inboxes.
12. Never guess, synthesize, or infer an email address from a naming pattern. Use only a publicly available address you can actually source.
13. Prefer the decision maker’s personal professional email. A named business email for that individual is also acceptable if public and attributable to them.
14. Record evidence for every material claim.
15. Never overwrite old evidence silently when the live site changed; record the new observation and validation time.

---

# Workflow

## Step 0 — Load the Lead

Select the next lead from D1, not from memory or an old report.

For each lead, load:

- Firm name
- Firm domain
- Place ID / lead ID
- Known city/state if available
- `campaign_leads.status`
- `qualified`
- prior campaign notes
- any existing `service_gap_evidence`
- any existing `lead_contacts`
- homepage-link evidence when available

If status is already final, skip it unless explicitly queued for re-review.

If status is `Needs Review`, only work it when the current session explicitly includes review-queue work.

Prior notes are context, not proof. Re-check the live website for material conclusions.

---

## Step 1 — Understand the Firm Before Looking for a Gap

Inspect the actual website.

At minimum check:

- Homepage
- Main navigation
- Services / Practice Areas page
- Relevant service sections
- Footer links
- “Learn More” / “Read More” / service buttons
- Attorney / About pages if they mention practice focus
- Internal links
- Sitemap when useful

Search-engine results may be used to discover possible pages, but the website itself is the source of truth for whether a focused service destination exists.

Capture:

- Main services explicitly offered
- Where each service appears
- Whether major services share one broad page
- Whether some services already have dedicated pages
- Any service buttons that lead back to a general page
- Any structural pattern that helps explain the opportunity

---

## Step 2 — Identify Meaningful Main-Service Opportunities

A strong gap usually looks like this:

> The firm clearly offers several important legal services, but one or more main services are explained only inside the homepage, a general Services page, a broad Practice Areas page, or a one-page website.

A page counts as dedicated when the page itself is overwhelmingly about that service, even if the URL is generic.

Strong opportunities include:

- A major service is only a section on a general Practice Areas page.
- A major service appears on the homepage but has no focused destination.
- A “Learn More” button for the service leads to a general page.
- Two major services have dedicated pages but another equally important service does not.
- A service already has useful content that could naturally become a focused client journey.
- A service serves a materially different type of client from the rest of the shared page.

Reject micro-gaps. Do not qualify primarily on Child Support when a substantial Family Law page exists, Green Cards when a substantial Immigration page exists, Wills when a substantial Estate Planning page exists, or equivalent subservice cases.

---

## Step 3 — Think in Client Conversations

Before choosing a mockup service, answer:

> Who is the person looking for this service, and what are they likely trying to understand when they arrive?

Keep this grounded and practical. Different legal matters can justify different message, information hierarchy, imagery, layout, CTA, tone and visual mood while remaining inside the firm’s overall brand.

Do not write amateur psychology.

---

## Step 4 — Choose the Best First Mockup Service

The chosen service is the **first example**, not necessarily the only service that could benefit from a focused page.

Choose the service that makes the clearest, strongest, easiest case.

Good reasons:

- It already has useful content.
- Its client journey is clearly different from the other services.
- Other major services already have dedicated pages but this one does not.
- It is central to the firm’s positioning.
- A relevant attorney credential makes the service especially interesting.
- A “Learn More” button exists but does not lead to a focused destination.
- It is visually or structurally easy to demonstrate as a standalone client experience.

---

## Step 5 — Write and Persist the Internal Validation Note Before the Email

Do not write outreach copy until these notes are complete and the service evidence is ready to persist.

Record:

```text
Service chosen for mockup:
Evidence:
Why this is a good example:
Email angle:
Validation status:
Pages checked:
Exact service wording used by the firm:
Why the existing destination is not reasonably dedicated:
Why this is a meaningful main service:
Why the client conversation is materially different:
```

For every service evaluated, save the appropriate `service_gap_evidence` row rather than collapsing the whole firm to one binary gap flag.

---

## Step 6 — Validation Gate

Before proceeding to decision-maker/email research, all of these must be true:

1. Service is explicitly offered — **Yes**.
2. Current website was inspected for a dedicated page — **Yes**.
3. A reasonable person would consider the existing destination dedicated to that service — **No**.
4. The target is a meaningful main service rather than a micro-subservice — **Yes**.
5. The opportunity can be explained without pretending the selected service is the only one that deserves a page — **Yes**.
6. There is a genuine personalized observation from the live site — **Yes**.
7. The client-experience case can be explained before Google/AI — **Yes**.
8. Ranking/indexing guarantees can be avoided — **Yes**.

If an important answer is unclear:

```text
status = Needs Review
qualified = 0
```

Do not start email hunting for a `Needs Review` lead unless explicitly instructed.

If no meaningful gap survives validation, persist the appropriate service evidence and set the campaign state to `Disqualified` or `Not Relevant` as appropriate. Stop before contact enrichment.

---

# Step 7 — Identify the Decision Maker

Only after at least one service passes the gap gate.

Typical priority:

1. Owner / Founder
2. Managing Partner
3. Named Partner
4. Managing Attorney
5. Solo Attorney / Principal
6. Other clearly senior decision maker

Use official About, Team, Attorneys, Leadership, footer/contact information and credible public professional sources.

Record and persist:

- Full name
- Title
- Evidence URL/source
- Why this person is the likely decision maker

If a real decision maker cannot be established:

```text
status = Gap Confirmed - Owner Missing
qualified = 0
```

Do not invent a buyer.

---

# Step 8 — Find a Direct Public Decision-Maker Email

This happens **last**.

Search order:

1. Official website / bio / contact assets
2. Public vCard or official PDF
3. State/local bar profile
4. Public professional profile
5. Public association/conference bio or other credible source clearly attributable to the person

Accept only a direct publicly evidenced address belonging to the selected decision maker.

Do not accept generic inboxes, forms without a direct email, guessed patterns, leaked/private databases, assistant/reception/intake addresses, or another employee’s email.

Save:

- Decision maker name
- Title
- Email
- Source URL/source
- Source type
- Exact evidence note showing the address belongs to that person

If the gap is confirmed but no acceptable direct public email is found:

```text
status = Gap Confirmed - Direct Email Missing
qualified = 0
```

---

# Step 9 — Write and Persist the Email

Only after the lead is otherwise outreach-ready.

Target length: **130–160 words**. A little longer is allowed only when personalization genuinely earns it.

Order:

1. **Personalized observation** proving the site was inspected.
2. **Broader insight** that different services often serve people in very different situations.
3. **Why dedicated pages make sense** — the right conversation for each client instead of asking one general page to do everything.
4. **Three short benefits** — client relevance first, then focused Google crawl/index context and clearer AI context. No ranking promises.
5. **Why this service is the first mockup example** — never imply it is the only structural opportunity.
6. **Soft CTA** — no call-booking request and no hard sell.

Default CTA:

> I’m putting together a quick mockup to show you what I mean. I’ll send it over in the next couple of days.
>
> If you’d rather I didn’t, just let me know.

The subject should sound like a person referring to something they noticed, not an SEO pitch.

Persist the final subject/body with the lead before marking the record fully complete.

---

# Step 10 — Final Lead Record

Every completed lead must be reproducible from D1 without needing this chat.

Minimum final record:

```text
Firm
Domain / lead ID
Main services explicitly offered
Pages checked
Selected mockup service
Service evidence
Why it is a good example
Email angle
Decision maker
Decision-maker title/evidence
Direct public email
Email source
Subject
Email body
Canonical campaign status
Qualified flag
Qualification reason
Reviewer notes
Validation time
```

Canonical outcomes:

```text
Needs Review
Not Relevant
Disqualified
Gap Confirmed - Owner Missing
Gap Confirmed - Direct Email Missing
Qualified
```

---

# Quality-Control Checklist

A lead can be **Qualified** only when all are true:

- [ ] Service is explicitly offered.
- [ ] Live website was independently inspected.
- [ ] Search results were not used alone to prove absence.
- [ ] No reasonable dedicated page exists for the selected main service.
- [ ] Selected service is meaningful, not a micro-subservice.
- [ ] The opportunity is framed as different client conversations, not “one missing URL.”
- [ ] Selected service is clearly positioned as the first example.
- [ ] Client experience is explained before Google/AI.
- [ ] No SEO ranking/indexing guarantees are made.
- [ ] First email sentence is based on a genuine observation.
- [ ] Decision maker is identified and evidenced.
- [ ] A direct public email for that exact decision maker exists.
- [ ] Email is not generic.
- [ ] Email was not guessed.
- [ ] Source for the email is saved.
- [ ] Outreach email is concise and personalized.
- [ ] Service evidence is persisted.
- [ ] Contact evidence is persisted.
- [ ] Subject/body are persisted with the lead.
- [ ] `campaign_leads` final state is saved before moving on.

---

# Anti-Patterns

Immediately correct or reject work that:

- Says “service X is in a menu and `/service-x` is missing, therefore gap.”
- Uses Google/search snippets alone to say a page does not exist.
- Targets a tiny subservice while a strong parent practice page exists.
- Says or implies only one service deserves its own page.
- Starts with SEO instead of client experience.
- Writes the email before evidence notes.
- Starts searching for email before the website opportunity passes validation.
- Accepts generic/reception/intake/admin inboxes.
- Guesses an email address based on a domain pattern.
- Uses generic praise as personalization.
- Pushes for a call in the first email.
- Makes ranking or indexing guarantees.
- Treats an old artifact/report as more authoritative than the current D1 state.
- Re-runs a finalized lead without an explicit reason.
- Finishes a lead in chat but fails to persist its state/evidence.

---

# Session Rules

At the start of each session:

1. Read `validation runner last update.md` for context.
2. Query D1 for the current campaign state.
3. Use D1 to determine the actual next `Ready for Validation` lead.
4. Skip leads already finalized in D1 even if the handoff file is stale.
5. Preserve previous evidence and status.
6. If the live site changed materially, record the change instead of silently overwriting the old conclusion.

At the end of each session:

1. Confirm every finalized lead was persisted to D1.
2. Update `validation runner last update.md`.
3. Record counts and exact stopping point.
4. Record unresolved `Needs Review` leads.
5. Record recurring patterns or new edge cases.
6. Record SOP/rule changes.
7. Record the exact next action.
8. Never leave the handoff vague.

If the handoff and D1 disagree, **D1 wins**. Document the discrepancy in the handoff.

---

# Core Philosophy

> Different legal services bring different clients with different questions, emotions, priorities and expectations. Dedicated service pages let each service have the right conversation with the client looking for it.

A dedicated page is not valuable only because it has a separate URL. It can have its own message, structure, imagery, emphasis, CTA and tone while staying inside the firm’s overall brand.

The selected service is the **best first demonstration** of that structural idea.

The lead is not outreach-ready until there is a **direct public email for the actual decision maker**.

The session is not complete until the lead’s state and evidence are **recoverable from D1**.
