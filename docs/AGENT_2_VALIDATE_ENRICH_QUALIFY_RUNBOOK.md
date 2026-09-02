# Agent 2 Runbook — Validate Gap, Enrich Owner Email, Qualify, Protect Outreach

Status: **production operating procedure — V2**

Last updated: **2026-09-02**

## Mission

Agent 2 takes a `Ready for Validation` business and decides whether it becomes an outreach-ready lead.

For each business, Agent 2 performs these steps in order:

```text
homepage-link review
→ mandatory independent website double-check
→ confirm real service gap(s)
→ if a gap exists: identify owner/decision maker
→ find direct public email for that exact person
→ Qualified
```

Do not spend time on owner/email enrichment before at least one real gap is confirmed.

---

## Required input from Agent 1

For V2, Agent 2 should receive:

```text
campaign_id
Place ID
public website final URL
registrable website domain
homepage title
source ZIP
homepage crawl status
homepage_links[] with URL + anchor text
```

Agent 2 does **not** need permanent Google rating/review-count data. The business already passed Agent 1's transient quality screen.

If the homepage crawl failed or returned suspiciously zero useful links, do not reject automatically. Treat it as a mandatory manual/open-web review case.

---

# Core final qualification rule

A business becomes `Qualified` only when all are true:

```text
1. At least one real service is genuinely offered
2. That exact service has no dedicated internal page after double-check
3. Owner / real decision maker is identified
4. Direct public email for that exact person is verified
```

Compact form:

```text
CONFIRMED GAP
+
OWNER / DECISION MAKER
+
DIRECT PUBLIC EMAIL FOR THAT PERSON
=
QUALIFIED
```

Discovery quality alone never creates a Qualified lead.

---

# Phase 1 — Inspect homepage evidence

Start with Agent 1's Crawl4AI evidence:

```text
homepage_link_evidence
```

Review URL paths and anchor text for:

- services/practice areas apparently offered,
- exact dedicated service pages,
- umbrella service/practice-area hubs,
- similar names that could be misleading,
- attorney/about/team pages that may reveal real practice areas.

Crawl4AI is evidence, not the final judge.

---

# Phase 2 — Exact-service page rule

Qualification is service-level, not firm-level.

For each candidate service independently:

## Dedicated exact-service page exists

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

When the URL/page is genuinely dedicated to that exact service:

```text
service opportunity = Disqualified
```

This does **not** automatically disqualify every other service at the firm.

## General umbrella pages are allowed

These are not sufficient by themselves to disqualify a specific service gap:

```text
/services
/practice-areas
/what-we-do
/legal-services
```

Example:

```text
target service = Probate
site has /estate-planning
site has no /probate page
```

`/estate-planning` does not prove Probate has a dedicated page.

## Buttons/cards matter by destination

A homepage card labelled `Probate` that links to `/services` does not prove a dedicated Probate page.

A card that links to `/probate` does.

---

# Phase 3 — Mandatory independent website double-check

**Never confirm a gap from homepage links alone.**

Before `Gap Confirmed`, independently inspect the public website/open web and answer two separate questions:

```text
A. Does the firm genuinely offer this service?
B. Does a dedicated internal page for this exact service exist anywhere on the site?
```

Use, as needed:

1. official homepage,
2. official Services / Practice Areas hub,
3. attorney/team bios,
4. About pages,
5. site navigation,
6. public search restricted to the official domain.

Search absence alone is not proof.

Ambiguity is not a positive result.

---

# Phase 4 — Store service evidence

Use first-class table:

```text
service_gap_evidence
```

For every evaluated service, record:

```text
campaign_id
lead_id
service_name
status
service_offered_evidence
dedicated_page_url
validation_method
notes
validated_at
```

Allowed service-level states:

### `Gap Confirmed`

```text
service genuinely offered
AND
no dedicated exact-service page found after double-check
```

### `Disqualified`

```text
dedicated exact-service page exists
```

Store the exact page URL.

### `Not Relevant`

```text
firm does not actually offer the service
```

### `Needs Review`

Use when evidence is contradictory, ambiguous, inaccessible, or incomplete.

Never turn ambiguity into a gap.

---

# Phase 5 — Stop early if no gap

If the firm has zero `Gap Confirmed` services:

```text
qualified = 0
```

Do not research owner email.

Use the best overall campaign state:

```text
Disqualified
Not Relevant
Needs Review
```

This saves research time and prevents contact enrichment for businesses we cannot pitch on a real gap.

---

# Phase 6 — Identify the owner / decision maker

Only continue when at least one confirmed gap exists.

Preferred law-firm decision makers:

```text
Founder / Owner
> Managing Partner
> clearly empowered principal
```

For a solo practice, the solo attorney is usually the owner/decision maker when public evidence supports it.

Do not use as the final decision maker:

- receptionist,
- intake coordinator,
- assistant,
- paralegal,
- generic staff member,
- unrelated attorney,
- office manager unless the business rule is explicitly changed.

Evidence preference:

1. official About/Team/Bio page,
2. official state bar profile,
3. reputable public professional source,
4. other public source that clearly proves leadership/ownership.

Store contact identity/evidence in:

```text
lead_contacts
```

If a real decision maker cannot be established:

```text
status = Gap Confirmed - Owner Missing
qualified = 0
```

---

# Phase 7 — Find DIRECT PUBLIC email for that exact person

Search only after a confirmed gap and owner/decision maker exist.

Search order:

1. official website,
2. owner bio/contact page,
3. official state bar/professional profile,
4. reputable public source clearly associating the exact email with the exact person.

## Acceptable

A direct, publicly evidenced email belonging to the selected owner/decision maker.

Examples:

```text
seth@firm.com
owner.name@firm.com
```

A non-firm-domain address can be accepted only when public evidence clearly establishes that it is the person's business contact.

## Not acceptable

Reject generic/shared addresses such as:

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

Also reject:

- receptionist email,
- intake team email,
- assistant email,
- unrelated employee email,
- another attorney's email when the chosen decision maker is somebody else.

## Never guess

Do not infer an address from a pattern such as:

```text
firstname@domain.com
```

unless that exact address is publicly evidenced.

No guessed/pattern-generated email can qualify a lead.

Store the contact in `lead_contacts` with, at minimum:

```text
person_name
role
email
is_owner
is_decision_maker
is_direct_email
is_publicly_verified
evidence_source
verified_at
```

If a gap is confirmed but no acceptable email exists:

```text
status = Gap Confirmed - Direct Email Missing
qualified = 0
```

---

# Phase 8 — Final qualification

A lead becomes `Qualified` only when:

```text
at least one service_gap_evidence.status = Gap Confirmed
AND
lead_contacts contains the real owner/decision maker
AND
that same contact has a direct publicly verified email
```

Then:

```text
campaign_leads.qualified = 1
campaign_leads.status = Qualified
campaign_leads.qualification_reason = confirmed_service_gap + verified_owner + direct_public_owner_email
```

`Qualified` means outreach-ready.

It does **not** mean outreach has already happened.

---

# Phase 9 — Outreach is a separate event

This distinction is mandatory:

```text
Qualified != Contacted
```

Only after a message/email is actually sent should the business be globally suppressed.

Immediately after actual outreach, update:

```text
outreach_suppression
```

Command:

```bash
python scripts/mark_business_contacted.py \
  --lead-id <PLACE_ID> \
  --campaign <CAMPAIGN_ID> \
  --email <DIRECT_OWNER_EMAIL> \
  --status Contacted
```

Default business rule:

```text
contacted once
→ globally blocked from being treated as a new outreach opportunity
```

This block applies across campaigns.

If the person replies or status changes, update the same canonical business lifecycle:

```text
Replied
Interested
Not Interested
Do Not Contact
Bounced
Re-engage Later
```

Never create a second campaign copy merely to contact the same business again.

---

# Recommended campaign states

```text
Ready for Validation
Needs Review
Not Relevant
Disqualified
Gap Confirmed - Owner Missing
Gap Confirmed - Direct Email Missing
Qualified
```

Contact/outreach state belongs separately in `outreach_suppression` / outreach lifecycle data.

---

# Evidence discipline

Every important conclusion should be reproducible by another agent/person.

## Gap evidence

Store:

```text
service_name
service_offered_evidence
dedicated_page_url or explicit no-page finding
validation_method
source URL(s)/notes
validated_at
```

## Owner/email evidence

Store:

```text
person name
role/ownership evidence
email
direct/public verification flags
evidence source
verification time
```

Do not store unsupported conclusions such as:

```text
probably a gap
probably the owner
email format looks right
```

---

## Agent 2 must NEVER

- qualify from Crawl4AI homepage links alone,
- assume search absence proves no page exists,
- call a service a gap when the firm does not genuinely offer it,
- disqualify the entire firm because one service has a page,
- research email before confirming a real gap,
- use generic/reception/intake email as final contact,
- use another employee's direct email when it does not belong to the selected decision maker,
- guess email patterns,
- convert ambiguous evidence into Qualified,
- treat `Qualified` as `Contacted`,
- send outreach and forget to create/update global suppression.

---

## Final checklist before `Qualified`

```text
[ ] Public official website identity is correct
[ ] Homepage links reviewed
[ ] Website independently double-checked
[ ] Service genuinely offered
[ ] No dedicated exact-service page exists for at least one service
[ ] Gap evidence stored in service_gap_evidence
[ ] Owner/decision maker is publicly evidenced
[ ] Direct email belongs to that exact person
[ ] Email is publicly evidenced
[ ] Email is not generic/reception/intake
[ ] Email was not guessed
[ ] Contact evidence stored in lead_contacts
[ ] campaign_leads.qualified = 1 only after every requirement above
```

After actual outreach:

```text
[ ] outreach_suppression updated immediately
```
