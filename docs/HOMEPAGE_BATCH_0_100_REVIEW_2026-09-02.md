# Homepage Batch 0–99 Review

Date: **2026-09-02**

This report documents the first production-style homepage-only crawl and the first manual/ChatGPT review pass over the 1,000-lawyer working set.

## Crawl design

Input: the previously built `lawyers-1000-working-set` artifact.

No Google Places discovery or Maps Grounding calls were repeated for this phase.

Crawl behavior:

```text
verified working-set website
→ load homepage only
→ render header/nav/footer/homepage
→ collect same-domain internal links visible on that homepage
→ stop
```

No deep crawl and no automated qualification logic.

The successful comparison run used **4 parallel Crawl4AI workers**. Parallelism changes only throughput; each worker still loads one homepage and collects links without following them.

## Crawl results — first 100

```text
Leads attempted:                     100
Homepage fetch completed:             98
Homepage fetch failed:                 2
Homepages retried:                      3
Completed with zero internal links:     1
Internal homepage links collected:  4,783
```

The two failed homepages remain `Needs Review`; crawl failure is not a qualification decision.

## What the first pass proved

The homepage collector is useful as a cheap architecture filter, but **absence of a service link on the homepage is not proof that no dedicated service page exists**.

Two examples from this batch demonstrate why the required second check matters:

### Dan Newlin Injury Attorneys

Crawl4AI exposed only a few homepage utility links in this run, creating an apparent no-service-page signal. The independent web double-check found dedicated practice URLs including pages under `/areas-of-practice/auto-accidents/` and a dedicated `/car-accident-glp/` page.

Result: **not a verified gap candidate from the apparent homepage absence**.

### Mortellaro Law

Crawl4AI completed the homepage with zero extracted internal links in this run. The independent web check showed a large dedicated navigation architecture for Elder Law, Estate Planning, Wills and Trusts, Power of Attorney, Asset Protection, Probate, Medicaid, VA Benefits and related services.

Result: **not a verified gap candidate from the zero-link crawl**.

These are exactly the cases the double-check step is designed to catch.

## Strong gap candidates verified in the first 100

The following firms had no obvious dedicated service URLs in the homepage-link collection and were then independently checked on the open web.

### 1. Ben Lynch Law — strong gap candidate

Homepage/website: `benlynchlaw.com`

The homepage itself lists multiple offered practice areas:

- Employment Law
- Personal Injury
- Family Law
- Criminal Law
- Civil Rights

The homepage crawl exposed only the homepage and checkout as same-domain link destinations. The independent web rendering confirms that `PRACTICE AREAS` is presented on the homepage and the services are sections of that page rather than separate service URLs.

Gap candidates include **Family Law**, **Employment Law**, **Personal Injury**, **Criminal Law**, and **Civil Rights**.

Status: **Qualified gap candidate**.

### 2. Seth Rose, Attorney at Law — strong gap candidate

Homepage/website: `sethroselaw.com`

Homepage links expose only general pages such as:

```text
/contact
/mission
/practiceareas
/profile
```

The general Practice Areas page lists:

- DUI / traffic-related criminal defense
- Drug and alcohol offenses
- Personal Injury / Workers Compensation
- Criminal Defense
- Wrongful Death
- Car Accidents
- Nursing Home Litigation
- Medical Malpractice

Independent web results surfaced the same general practice page and non-service pages; the practice-area sections repeat across the site rather than appearing as dedicated service URLs.

Status: **Qualified gap candidate** for multiple services.

### 3. PT Law — strong gap candidate

Homepage/website: `ptlawlv.com`

Homepage navigation exposes a general `/practice-areas` page, not individual service URLs.

The general page contains:

- Personal Injury
- Car Accidents and related injury matters
- Criminal Defense
- Immigration Law
- Traffic Tickets

The open-web double-check confirms these services are consolidated on the general practice page.

Status: **Qualified gap candidate** for multiple services.

### 4. The Icard Law Firm — strong gap candidate

Homepage/website: `icardlawfirm.com`

The homepage crawl exposed only the site's main `index.html` and privacy page. Independent rendering shows the site is effectively a one-page service presentation and lists:

- Criminal Defense
- Traffic Violations
- Felonies / Misdemeanors
- DWI and related criminal matters

The `PRACTICE` navigation points to the same one-page presentation rather than a set of dedicated service pages.

Status: **Qualified gap candidate** for multiple services.

## Remaining first-100 architecture

Among the completed sites, most expose at least one obvious service-specific URL directly from the homepage. That does **not** automatically disqualify the whole firm under the service-level rule.

Correct interpretation:

```text
service offered + dedicated page for that exact service
→ that service gap is Disqualified

another offered service + no dedicated page
→ that other service can still be a Qualified gap
```

Therefore sites with service-specific URLs move to a lower-priority **service comparison** queue rather than being thrown away entirely.

## Next production sequence

1. Crawl the remaining working set in 100-lead batches with 4 workers.
2. For each batch, prioritize sites with no obvious service-specific homepage URLs.
3. Independently double-check those priority candidates on the open web.
4. Record verified service gaps per firm, not just one binary firm-level status.
5. For firms with some dedicated service pages, compare offered services against dedicated-page coverage to find partial gaps.
6. Only after a gap is verified, enrich owner/founder/managing attorney and direct public business email.

## Cost impact

This crawl/review stage repeats **zero Google Places / Maps Grounding requests** because it consumes the saved 1,000-lawyer artifact.
