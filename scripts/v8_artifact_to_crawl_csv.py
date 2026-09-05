#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


def main() -> None:
    ap = argparse.ArgumentParser(description="Convert V8 accepted-this-run JSONL to Crawl4AI working-set CSV")
    ap.add_argument("--input", required=True)
    ap.add_argument("--output", required=True)
    args = ap.parse_args()

    src = Path(args.input)
    dst = Path(args.output)
    rows: list[dict] = []
    seen_domains: set[str] = set()

    with src.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            item = json.loads(line)
            domain = str(item.get("website_domain") or "").strip().lower().strip(".")
            place_id = str(item.get("place_id") or "").strip()
            if not domain or not place_id or domain in seen_domains:
                continue
            seen_domains.add(domain)
            rows.append({
                "place_id": place_id,
                "name": domain,
                "address": "",
                "source_market": str(item.get("state") or ""),
                "rating": "",
                "review_count": "",
                "website_domain": domain,
                "website": f"https://{domain}/",
                "website_verified_open_web": "",
            })

    dst.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "place_id", "name", "address", "source_market", "rating", "review_count",
        "website_domain", "website", "website_verified_open_web",
    ]
    with dst.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

    print(json.dumps({"input_rows": len(rows), "output": str(dst)}, indent=2))


if __name__ == "__main__":
    main()
