# Agent 2 Runbook — Validate Gap, Enrich Owner Email, and Qualify

Status: **production operating procedure**

Last updated: **2026-09-02**

## Mission

Agent 2 converts a high-quality working-set business into either:

```text
Qualified outreach-ready lead
```

or a conservative non-qualified state with evidence.

Agent 2 owns three logically ordered jobs for each lead:

1. validate whether a real service-page gap exists,
2. only if a gap exists, identify the owner/decision maker and find a direct public email for that person,
3. assign the final campaign qualification state.

The order matters. **Do not spend time enriching contact data before a gap is confirmed.**

---

## Read these files first

Before working a lead, read:

- `README.md`
- `docs/FINAL_LEAD_ENGINE_ARCHITECTURE.md`
- `docs/AGENT_1_DISCOVERY_CAMPAIGN_RUNBOOK.md`
- this file

For lawyers, remember that discovery is generic. The campaign is not necessarily a Family Law campaign, Probate campaign, etc. One firm can offer many services and can have multiple independent gaps.

---

## Required input from Agent 1

For every lead, Agent 2 should have:

```text
campaign_id
Place ID
business name
address/source market
rating
review count
official website
normalized domain
Google Maps grounding source
homepage crawl status
homepage_links[] with URL + anchor text
```

If homepage crawl failed or returned suspiciously no useful links, that is not a rejection. It means the website double-check is mandatory and should receive extra attention.

---

# Core qualification rule

A business becomes **Qualified** only when all of these are true:

```text
1. Real service offered by the firm
2. No dedicated exact-service page exists after double-check
3. Owner / decision maker identified
4. Direct public business email for that exact owner / decision maker found
```

In compact form:

```text
CONFIRMED GAP
+ OWNER IDENTIFIED
+ DIRECT PUBLIC OWNER EMAIL
= QUALIFIED
```

Google rating/review quality alone never makes a lead Qualified.

---

# Phase 1 — Inspect Crawl4AI homepage links

Start with `homepage_links.csv/json` for the lead.

Crawl4AI is evidence, not the final judge.

Inspect URL paths and anchor text to understand:

- services/practice areas the firm appears to offer,
- obvious dedicated service pages,
- generic service hubs,
- misleading similarly named pages.

## Exact-service rule

For each candidate service independently:

### Dedicated exact page exists

Examples:

```text
/family-law
/probate
/estate-planning
/immigration
/business-law
/adoption
/power-of-attorney
```

If the page is genuinely dedicated to the exact service:

```text
that service gap = Disqualified
```

### Generic pages are allowed

These do **not** automatically disqualify a service gap:

```text
/services
/practice-areas
/what-we-do
/legal-services
```

Likewise, a dedicated page for another service does not disqualify the target service.

Example:

```text
target = Probate
site has /estate-planning
site has no /probate
```

`/estate-planning` alone does not prove Probate has a dedicated page.

### Buttons/cards only matter by destination

A homepage button saying `Probate` is not itself the reason for disqualification. Inspect where it goes.

If it goes to a generic `/services` page, the dedicated Probate page has not yet been proven.

If it goes to `/probate`, the Probate gap is disqualified.

---

# Phase 2 — Mandatory website double-check

**Never declare a gap from homepage links alone.**

Even when Crawl4AI finds no exact-service URL, Agent 2 must independently inspect/search the actual website before confirming a gap.

Use the official website and open-web/site-specific search as needed.

The double-check should answer two separate questions:

```text
A. Does the firm genuinely offer this service?
B. Does a dedicated internal page for this exact service exist anywhere on the site?
```

Recommended evidence sources:

1. official homepage,
2. official Services / Practice Areas hub,
3. official attorney bio/about pages if they list actual practice areas,
4. site navigation,
5. public search restricted to the official domain when needed.

Search absence alone is not proof. Use multiple signals when necessary.

---

# Phase 3 — Classify each service opportunity

Each service should receive its own result.

## `Gap Confirmed`

Use only when:

```text
service is genuinely offered
AND
no dedicated exact-service internal page is found after double-check
```

## `Disqualified`

Use when:

```text
a dedicated exact-service internal page exists
```

This disqualifies the gap for that service, **not necessarily the whole firm**.

A firm can be:

```text
Family Law → Disqualified
Probate → Gap Confirmed
Estate Planning → Disqualified
Business Law → Gap Confirmed
```

## `Not Relevant`

Use when the firm does not actually offer the service.

Do not call a service gap Qualified just because Google discovery happened to match a misleading query or category.

## `Needs Review`

Use when evidence is ambiguous, contradictory, the site is broken, or you cannot confidently determine whether the service is offered or whether a dedicated page exists.

Never convert ambiguity into a positive gap.

---

# Phase 4 — Stop early when there is no confirmed gap

If the business has **zero confirmed gaps** after website validation:

```text
do not perform owner/email enrichment
qualified = 0
```

Use the best matching overall campaign state, for example:

```text
Disqualified — no usable service gap
Not Relevant
Needs Review
```

This saves time and keeps email research focused only on real opportunities.

---

# Phase 5 — Identify the actual owner / decision maker

Only start this phase when at least one `Gap Confirmed` service exists.

For a law firm, acceptable decision makers usually include:

- founder,
- owner,
- founding attorney,
- managing partner when clearly the business decision maker,
- solo attorney who owns the practice.

Preference order:

```text
Founder/Owner > Managing Partner > clearly empowered principal
```

The contact must be a person who can reasonably make a website/marketing/service-page decision.

Do not use:

- receptionist,
- intake coordinator,
- assistant,
- paralegal,
- office manager unless the user explicitly changes the rule,
- generic staff member.

### Evidence for ownership

Prefer:

1. official firm About/Team/Bio page,
2. official state bar profile,
3. reputable public professional profile,
4. other public evidence that clearly links the person to ownership/leadership.

Record both:

```text
owner_name
owner_evidence_url/source
```

If ownership cannot be identified confidently:

```text
status = Gap Confirmed - Owner Missing
qualified = 0
```

---

# Phase 6 — Find a DIRECT PUBLIC email for that exact owner

The email must be publicly available and belong to the identified owner/decision maker.

Search order:

1. official website,
2. owner bio/contact page,
3. official state bar or professional profile,
4. reputable public web source clearly associating that email with the owner.

## Acceptable

Examples:

```text
seth@sethroselaw.com
calvin@ptlawlv.com
brad@firmdomain.com
owner.name@firmdomain.com
```

A non-domain email can still be accepted only if it is publicly listed as the owner's actual business contact and the identity is clear. Firm-domain direct emails are preferred.

## NOT acceptable

Reject generic mailboxes such as:

```text
info@
contact@
hello@
office@
support@
reception@
intake@
admin@
team@
legal@
marketing@
appointments@
```

Also reject an email that belongs to:

- receptionist,
- intake team,
- assistant,
- unrelated attorney,
- general office contact.

The rule is not merely “non-generic email.” The email must belong to **the owner/decision maker selected for the lead**.

## Never guess an email

Do not infer:

```text
firstname@domain.com
```

from a naming pattern unless that exact email is publicly evidenced.

No guessed/pattern-generated email can qualify a lead.

Record:

```text
owner_email
email_evidence_url/source
email_publicly_verified = true/false
```

If only a generic/reception email exists:

```text
status = Gap Confirmed - Direct Email Missing
qualified = 0
```

Do not substitute the generic email.

---

# Phase 7 — Final qualification

A lead may be marked `Qualified` only when the complete evidence chain exists.

Required final fields:

```text
campaign_id
lead_id / Place ID
company_name
website
website_domain
rating
review_count
confirmed_gap_services[]
gap_evidence[]
owner_name
owner_role
owner_evidence
owner_email
email_evidence
qualification_status
qualification_reason
validated_at
```

### Final `Qualified` test

```text
at least one confirmed service gap
AND
owner/decision maker identified
AND
direct public email for that exact person verified
```

Then:

```text
qualified = 1
status = Qualified
```

Recommended qualification reason:

```text
confirmed_service_gap + verified_owner + direct_public_owner_email
```

---

# Recommended overall campaign states

Use conservative, explicit states:

```text
Ready for Validation
Needs Review
Not Relevant
Disqualified
Gap Confirmed - Owner Missing
Gap Confirmed - Direct Email Missing
Qualified
```

`Gap Confirmed` by itself is an intermediate evidence state, not outreach-ready qualification.

---

# Evidence discipline

For every decision, preserve enough evidence for another agent/person to reproduce it.

For a confirmed gap, record:

```text
service_name
service_offered_evidence
homepage_link_evidence_checked
double_check_method
dedicated_page_found = false
notes
```

For a disqualified gap, record the exact dedicated URL:

```text
service_name
dedicated_page_url
anchor/title evidence
```

For an owner/email qualification, record the public source that proves the association.

Do not store unsupported conclusions such as:

```text
"looks like a gap"
"probably owner"
"email pattern seems right"
```

---

# Recommended D1 handling

Canonical business identity remains in `leads`.

Campaign-specific qualification remains in `campaign_leads`.

At minimum update conceptually:

```text
campaign_leads.qualified
campaign_leads.status
campaign_leads.qualification_reason
campaign_leads.notes
```

The current schema does not yet have dedicated columns/tables for all gap, owner, and email evidence. Until that schema is expanded, preserve structured evidence in authoritative campaign artifacts and/or structured notes without losing source URLs.

Do not put owner/email evidence into unrelated review-signal fields.

A future schema improvement should introduce first-class tables/fields for:

```text
service_gap_evidence
lead_contacts
contact_evidence
validation_events
```

---

# Processing algorithm

For each lead:

```text
LOAD lead + homepage links
        ↓
Inspect homepage URLs/anchors
        ↓
Identify candidate services
        ↓
Mandatory website double-check
        ↓
For each service:
  dedicated exact page? → Disqualified for that service
  service not offered?  → Not Relevant for that service
  ambiguous?            → Needs Review
  offered + no page?     → Gap Confirmed
        ↓
Any confirmed gap?
  NO → STOP; do not enrich email
  YES
        ↓
Identify owner / decision maker
        ↓
Find direct public email for that exact person
        ↓
Direct owner email found?
  NO → Gap Confirmed - Direct Email Missing
  YES
        ↓
QUALIFIED
```

---

## Agent 2 must NEVER do these things

- Do not qualify from Crawl4AI links alone.
- Do not assume search absence proves no page exists.
- Do not call a service a gap if the firm does not actually offer it.
- Do not disqualify the entire firm because one service has a dedicated page.
- Do not research email before confirming at least one real gap.
- Do not accept `info@`, reception, intake, or other generic emails.
- Do not accept another employee's direct email when the selected decision maker is the owner.
- Do not guess email patterns.
- Do not turn ambiguous evidence into Qualified.

---

## Agent 2 final checklist

Before setting `Qualified`, confirm:

```text
[ ] Official website identity is correct
[ ] Crawl4AI homepage links reviewed
[ ] Website independently double-checked
[ ] Service is genuinely offered
[ ] No dedicated exact-service page exists
[ ] At least one service gap is confirmed
[ ] Owner/decision maker identity is evidenced
[ ] Email belongs to that exact owner/decision maker
[ ] Email is publicly evidenced
[ ] Email is not generic/reception/intake
[ ] Email was not guessed
[ ] Gap evidence is saved
[ ] Owner/email evidence is saved
[ ] qualified = 1 only after every box above is true
```
