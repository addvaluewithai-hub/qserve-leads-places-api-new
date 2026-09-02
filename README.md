# Multi-Campaign Lead Engine + CRM

A reusable lead-discovery, website-validation, enrichment, and outreach system built around Google Places API (New), Maps Grounding Lite, Crawl4AI, GitHub Actions, Cloudflare Pages, and Cloudflare D1.

The repository supports multiple verticals. The most mature production workflow is the **large-scale lawyer service-gap pipeline**.

---

## Start here — lawyer production workflow

Read these in order:

1. `docs/FINAL_LEAD_ENGINE_ARCHITECTURE.md` — architecture/source-of-truth.
2. `docs/MARKET_COVERAGE_MANAGEMENT.md` — how we decide where to search next and track territory coverage.
3. `docs/AGENT_1_DISCOVERY_CAMPAIGN_RUNBOOK.md` — how Agent 1 creates the next net-new working set and collects homepage links.
4. `docs/AGENT_2_VALIDATE_ENRICH_QUALIFY_RUNBOOK.md` — how Agent 2 confirms the real service gap, finds the owner/direct public email, and performs final qualification.

Supporting benchmark/history docs:

- `docs/BENCHMARK_10_REQUESTS_2026-09-02.md`
- `docs/BUILD_1000_LAWYERS_2026-09-02.md`
- `docs/HOMEPAGE_BATCH_0_100_REVIEW_2026-09-02.md`
- `docs/FIRST_4_OUTREACH_READY_LEADS_2026-09-02.md`

---

# Current lawyer architecture

```text
Agent 1

Managed market queue
market_plans/lawyers-us.json
+ D1 market_coverage/history
        ↓
Google Places Text Search Pro
minimal identity fields only
        ↓
Place ID + name + address + business status
        ↓
Maps Grounding Lite
name + address → website + rating + review count
        ↓
Place-ID identity match
+ 4.7 rating / 20+ review gate
+ existing Place-ID/domain exclusion
+ domain dedupe
        ↓
NET-NEW unique law-firm domains
        ↓
D1 campaign membership
qualified = 0
status = Ready for Validation
        ↓
Crawl4AI homepage only
        ↓
visible same-domain homepage/header/footer/nav links
        ↓
Agent 2

inspect Crawl4AI evidence
        ↓
MANDATORY website double-check
        ↓
real service offered + no dedicated exact-service page
        ↓
Confirmed Gap
        ↓
identify owner / decision maker
        ↓
find DIRECT PUBLIC email for that exact person
        ↓
Qualified
```

A Google-quality business is **not Qualified** at discovery time.

---

# Two-agent operating model

## Agent 1 — Discovery + market management + campaign build + homepage collection

Runbook:

```text
docs/AGENT_1_DISCOVERY_CAMPAIGN_RUNBOOK.md
```

Agent 1 owns:

- next-market selection,
- Google discovery,
- Grounding Lite enrichment,
- quality gate,
- cross-run Place-ID/domain dedupe,
- D1/campaign insertion,
- homepage-only Crawl4AI,
- Agent 2 handoff.

Agent 1 never validates a gap and never searches owner emails.

## Agent 2 — Gap validation + contact enrichment + qualification

Runbook:

```text
docs/AGENT_2_VALIDATE_ENRICH_QUALIFY_RUNBOOK.md
```

Agent 2 works lead-by-lead:

```text
Crawl links
→ website double-check
→ confirm gap
→ identify owner
→ find direct public owner email
→ Qualified
```

If no gap exists, stop before contact enrichment.

---

# Market / location management

We do not manage coverage with notes like "Texas done".

Static plan:

```text
market_plans/lawyers-us.json
```

Dynamic D1 state:

```text
market_coverage
market_run_history
```

Current market statuses:

```text
queued
partial
covered_once
exhausted
cooling
```

The first validated 1,000-domain build used 92 markets and stopped at **New Haven, CT**. It stopped before the remaining primary queue including the original Texas primary metros. Texas is therefore not considered exhausted.

See current coverage / next markets:

```bash
python scripts/market_manager.py status --campaign lawyers-us --next 25
```

Show only next markets:

```bash
python scripts/market_manager.py next --campaign lawyers-us --next 25
```

Full rules:

```text
docs/MARKET_COVERAGE_MANAGEMENT.md
```

---

# Bootstrap the historical first 1,000

Before running "next 1,000", seed the validated first 1,000 into D1 once so cross-run dedupe is authoritative.

```bash
python scripts/bootstrap_lawyers_us_campaign.py \
  --campaign lawyers-us \
  --input-dir <first-1000-artifact-directory>
```

This makes zero Google calls.

GitHub workflow:

```text
.github/workflows/bootstrap-lawyers-us-campaign.yml
```

---

# Build the next 1,000 net-new lawyers

After bootstrap:

```bash
export GOOGLE_API_KEY=...
export CLOUDFLARE_ACCOUNT_ID=...
export CLOUDFLARE_API_TOKEN=...
export D1_DATABASE_ID=...

python scripts/build_next_1000_lawyers.py \
  --campaign lawyers-us \
  --target 1000
```

The builder automatically:

1. loads existing campaign Place IDs/domains from D1,
2. reads next eligible markets from the managed queue,
3. performs minimal Text Search Pro discovery,
4. excludes old Place IDs before Grounding,
5. resolves website/rating/review count through Grounding Lite,
6. applies quality and identity gates,
7. excludes existing/duplicate domains,
8. records market yield/history after every market,
9. continues until the target net-new domain count is reached,
10. inserts accepted working-set leads into D1 as `Ready for Validation`, `qualified=0`.

GitHub workflow:

```text
.github/workflows/build-next-1000-lawyers.yml
```

All live discovery workflows are **manual-dispatch only**.

---

# Google discovery economics — lawyers

Current scalable production discovery requests only:

```text
places.id
places.displayName
places.formattedAddress
places.businessStatus
```

Search request:

```text
textQuery = lawyer in <market>
includedType = lawyer
strictTypeFiltering = true
minRating = 4.7
pageSize = 20
```

Grounding Lite then supplies:

```text
official website
rating
review count
Google Maps source
```

The normal lawyer path does not request:

```text
reviews[]
Place Details Enterprise
```

Historical first-1,000 benchmark:

```text
92 Text Search Pro requests
1,252 Maps Grounding Lite calls
0 Place Details Enterprise calls
```

Always verify current Google pricing/free caps before financial reporting.

---

# Crawl4AI role

Crawl4AI is intentionally a **dumb homepage collector**.

For each lead:

1. load the homepage once,
2. render normal header/nav/footer,
3. collect all visible same-domain links,
4. save URL + anchor text,
5. retry once if needed,
6. stop.

It must not:

- deep crawl,
- recursively follow links,
- classify service pages,
- decide Qualified/Disqualified,
- search for emails.

Validated scaled collector:

```text
scripts/crawl_working_set_homepages_parallel.py
```

Recommended validated worker count:

```text
4 workers
```

Homepage evidence outputs include:

```text
homepage_links.csv
homepage_links.json
homepage_fetch_summary.csv/json
homepage_links_summary.json
```

---

# Exact service-gap rule

Qualification is service-level, not firm-level.

Allowed:

```text
/services
/practice-areas
```

A general umbrella page does not automatically disqualify a service gap.

For a specific service:

```text
service genuinely offered
+
no dedicated exact-service page/URL after mandatory double-check
=
Confirmed Gap
```

If an exact dedicated page exists, that **specific gap** is disqualified. Other services at the same firm may still contain gaps.

If the firm does not actually offer the service:

```text
Not Relevant
```

Missing homepage-link evidence alone is never enough to qualify a gap.

---

# Direct-email rule

A final outreach-ready lead requires a public direct email for the actual owner / relevant decision maker.

Accepted example:

```text
owner.name@firm.com
```

Not accepted as final contact:

```text
info@
contact@
hello@
office@
support@
reception@
intake@
admin@
```

Also not accepted:

- receptionist email,
- assistant email,
- unrelated attorney email,
- guessed email pattern,
- fabricated address.

Final qualification requires:

```text
real confirmed service gap
+
owner/decision maker identified
+
direct public email for that exact person
=
Qualified
```

If the gap is confirmed but no acceptable direct email is found, preserve the lead as a contact-missing/non-qualified state rather than inventing data.

---

# D1 data model

Core tables:

```text
leads
campaigns
campaign_runs
campaign_leads
lead_signals
lead_domains
market_coverage
market_run_history
```

Responsibilities:

```text
leads              canonical business
lead_domains       normalized canonical domain registry
campaigns          campaign config
campaign_runs      run-level history
campaign_leads     campaign-specific state / qualification
lead_signals       optional legacy/general signals
market_coverage    aggregate territory state/yield
market_run_history per-market pass audit history
```

One business can participate in multiple campaigns without mixing campaign-specific qualification state.

---

# Included campaign configs

```text
campaigns/lawyers-us.json  current scalable national lawyer workflow
campaigns/lawyers-tx.json  older Texas-focused lawyer config / legacy path
campaigns/dentists-tx.json
campaigns/cafes-eg.json
```

Do not use the expensive legacy lawyer discovery field masks for a new large-scale lawyer build when the `lawyers-us` workflow fits the task.

---

# Required GitHub secrets

```text
GOOGLE_API_KEY
CLOUDFLARE_ACCOUNT_ID
CLOUDFLARE_API_TOKEN
D1_DATABASE_ID
```

---

# Workflow safety

Normal code pushes must not make live Google/Grounding/Crawl/D1 campaign writes.

Production live workflows are manually triggered.

Relevant workflows:

```text
.github/workflows/bootstrap-lawyers-us-campaign.yml
.github/workflows/build-next-1000-lawyers.yml
.github/workflows/lawyer-market-status.yml
.github/workflows/crawl-lawyers-working-set.yml
```

---

# Short version

For lawyers:

```text
Agent 1:
managed locations
→ next 1,000 net-new domains
→ D1
→ homepage links

Agent 2:
links + website double-check
→ confirmed gap
→ owner
→ direct public owner email
→ Qualified
```

If a future agent is unsure how to proceed, it should read the two runbooks and the market-coverage document before making live requests.
