#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import csv
import json
from datetime import datetime, timezone
from pathlib import Path

from crawl4ai import AsyncWebCrawler

from crawl_working_set_homepages import fetch_one, load_csv, write_csv


async def run(args) -> None:
    input_path = Path(args.input)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    rows = load_csv(input_path)
    start = max(0, int(args.start))
    limit = max(1, int(args.limit))
    selected = rows[start:start + limit]
    worker_count = min(max(1, int(args.workers)), max(1, len(selected)))

    queue: asyncio.Queue[tuple[int, dict]] = asyncio.Queue()
    for offset, lead in enumerate(selected):
        queue.put_nowait((start + offset, lead))

    summaries: list[dict] = []
    link_rows: list[dict] = []

    async def worker(worker_id: int) -> None:
        async with AsyncWebCrawler() as crawler:
            while True:
                try:
                    source_index, lead = queue.get_nowait()
                except asyncio.QueueEmpty:
                    return
                try:
                    print(f"[worker {worker_id}] #{source_index} {lead.get('name')} - {lead.get('website')}")
                    summary, links = await fetch_one(crawler, lead, source_index)
                    summaries.append(summary)
                    for link in links:
                        link_rows.append({
                            "source_index": source_index,
                            "place_id": lead.get("place_id"),
                            "name": lead.get("name"),
                            "address": lead.get("address"),
                            "source_market": lead.get("source_market"),
                            "rating": lead.get("rating"),
                            "review_count": lead.get("review_count"),
                            "website_domain": lead.get("website_domain"),
                            "homepage": summary.get("homepage"),
                            "final_url": summary.get("final_url"),
                            "url": link["url"],
                            "anchor_text": link["anchor_text"],
                        })
                    print(
                        f"[worker {worker_id}] #{source_index} status={summary['crawl_status']} "
                        f"attempts={summary['attempts']} links={summary['internal_links_found']}"
                    )
                finally:
                    queue.task_done()

    await asyncio.gather(*(worker(i + 1) for i in range(worker_count)))

    summaries.sort(key=lambda row: int(row["source_index"]))
    link_rows.sort(key=lambda row: (int(row["source_index"]), row["url"]))

    links_by_index: dict[int, list[dict]] = {}
    for row in link_rows:
        links_by_index.setdefault(int(row["source_index"]), []).append({
            "url": row["url"],
            "anchor_text": row["anchor_text"],
        })

    payload = []
    for summary in summaries:
        item = dict(summary)
        item["links"] = links_by_index.get(int(summary["source_index"]), [])
        payload.append(item)

    write_csv(out_dir / "homepage_links.csv", link_rows, [
        "source_index", "place_id", "name", "address", "source_market", "rating", "review_count",
        "website_domain", "homepage", "final_url", "url", "anchor_text",
    ])
    write_csv(out_dir / "homepage_fetch_summary.csv", summaries, [
        "source_index", "place_id", "name", "address", "source_market", "rating", "review_count",
        "website_domain", "homepage", "prior_open_web_verified", "crawl_status", "homepage_status_code",
        "homepage_title", "final_url", "internal_links_found", "attempts", "error", "fetched_at",
    ])
    (out_dir / "homepage_links.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    aggregate = {
        "input": str(input_path),
        "batch_start": start,
        "batch_limit": limit,
        "workers": worker_count,
        "leads_available": len(rows),
        "leads_attempted": len(summaries),
        "homepage_fetch_completed": sum(1 for r in summaries if r.get("crawl_status") == "completed"),
        "homepage_fetch_failed": sum(1 for r in summaries if r.get("crawl_status") == "failed"),
        "homepage_fetch_skipped": sum(1 for r in summaries if r.get("crawl_status") == "skipped"),
        "homepages_retried": sum(1 for r in summaries if int(r.get("attempts") or 0) > 1),
        "completed_with_zero_internal_links": sum(
            1 for r in summaries
            if r.get("crawl_status") == "completed" and int(r.get("internal_links_found") or 0) == 0
        ),
        "total_internal_homepage_links": len(link_rows),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    (out_dir / "homepage_links_summary.json").write_text(json.dumps(aggregate, indent=2), encoding="utf-8")
    print(json.dumps(aggregate, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description="Parallel homepage-only link collection for a CSV working set")
    parser.add_argument("--input", required=True)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--start", type=int, default=0)
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
