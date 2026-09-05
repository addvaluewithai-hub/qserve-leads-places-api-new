# V8 Daily 2K Discovery Plan

Status captured 2026-09-05.

## Batch 1 checkpoint
- Batch ID: `lawyers-us:v8-batch-01-of-09`
- Target: 2,000 total domains for Batch 1 (including adopted V7 discoveries).
- Result from the completed artifact: **2,000 / 2,000 collected; remaining 0; status completed**.
- V8 added 1,133 domains during its production run; the rest were adopted from the earlier V7 Batch-1 work.
- Stop reason: `target_reached`.
- Tracked Google usage at completion: Aggregate 512, Place Details Pro 2,079, Grounding Lite 3,170, Place Details Enterprise 0.

## Do not run another batch on 2026-09-05
No Batch 2 trigger should be created today. Ignore validator workflows and do not touch `main`.

## D1 incident
A later same-Batch-1 status/resume attempt failed before discovery because Cloudflare D1 returned error 7500: the account exceeded the **free-tier daily row-read limit**. Cloudflare's error says to wait until midnight UTC for the daily reset.

The urgent optimization before the next production batch is to reduce D1 row-read amplification:
- Do not call `batch_state()` / `COUNT(*)` per accepted lead; keep counters in memory and persist/check them only at coarse checkpoints.
- Load global seen Place IDs/domains once per run and maintain the sets in memory.
- Avoid repeated SELECT-before-INSERT verification where unique indexes / `INSERT OR IGNORE` can enforce identity safely.
- Reduce `tile_stats()` / full aggregate scans to periodic checkpoints rather than every tile.
- Use indexed/bulk lookups and incremental compact counters for resumability.
- Keep page/tile-level persistence so cancellation remains resumable, but avoid read-heavy status recomputation.

## Daily execution rule starting 2026-09-06
1. Confirm no discovery workflow is already active. Ignore validators.
2. Confirm D1 daily quota is available; if unavailable, start nothing and report the block.
3. Confirm Google zero-paid guards are safe. If remaining free quota cannot be safely established or a guard is exhausted, start nothing.
4. Ensure the D1 read-amplification patch is applied and compile/smoke passes before the next production batch.
5. If the current numbered 2K batch is partial, resume that exact batch only.
6. If it is complete and campaign expansion is below +18,000 net-new domains, start the next numbered batch for +2,000 net-new domains using global Place-ID/domain dedupe.
7. Never auto-chain a second 2K batch on the same day.
8. Stop permanently after the +18,000 campaign expansion goal is reached.

Architecture remains:
`Places Aggregate COUNT -> recursive split -> Place IDs -> global Place-ID dedupe -> Place Details Pro context -> Maps Grounding Lite official domain -> global domain dedupe -> Ready for Crawl Evidence`.
