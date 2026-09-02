# ZIP V3 next-1000 retry 2 — 2026-09-02

This retry uses the parameter-safe batched historical bootstrap (`bootstrap_lawyers_us_campaign_v3.py`) before the ZIP-managed next-1000 builder. It is intentionally one-time and issue-triggered because the connected GitHub tool does not expose workflow_dispatch directly in this session.

Default territory behavior for an unspecified "get the next 1,000" request:

1. Use the campaign market plan.
2. Prefer queued ZIPs before revisits.
3. Current phase priority starts with TX, then FL, GA, NC, TN, AZ, NV, CO.
4. Within a state, preferred cities are ordered explicitly in `market_plans/lawyers-us-zips.json`; remaining ZIPs follow after preferred-city ZIPs.
5. ZIP rows come from pgeocode/GeoNames postal-code data; acceptance still requires Google addressComponents postal_code to equal the target ZIP.
6. Global Place-ID/domain/outreach suppression applies across all campaigns.
