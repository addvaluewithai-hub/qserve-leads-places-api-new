# Default territory policy for “Get the next 1,000”

When no location is specified, Agent 1 does not ask a follow-up question. It uses the campaign market plan and D1 ZIP coverage state.

Current default order:

- Search queued ZIPs before revisits.
- State phase 1 priority: TX, FL, GA, NC, TN, AZ, NV, CO.
- Within each state, preferred-city ZIPs are searched first in the order listed in `market_plans/lawyers-us-zips.json`.
- Remaining ZIPs in that state follow afterward.
- If the user specifies a state, metro, city, or ZIP set, that explicit scope overrides the default order.

ZIP source:

- `pgeocode.Nominatim("us")`
- pgeocode uses GeoNames postal-code data (with its documented mirror fallback).
- ZIP centroid and place-name data are management/search-view helpers only.
- A Google result counts toward a target ZIP only when returned `addressComponents` contains the exact same 5-digit postal code.

Business uniqueness:

- Place ID and canonical domain are globally deduplicated.
- Businesses already contacted are globally suppressed from new outreach campaigns unless explicitly marked for re-engagement.
