#!/usr/bin/env python3
from __future__ import annotations

import json
import os
from pathlib import Path

import requests

MCP_URL = "https://mapstools.googleapis.com/mcp"
OUT = Path("out/maps-grounding-probe")
QUERIES = [
    "Gibbins Law PLLC Tyler Texas official website",
    "Hager Law PLLC Texas official website",
    "Tate Accident Law Sherman Texas official website",
]


def parse_body(response: requests.Response):
    ctype = response.headers.get("content-type", "")
    text = response.text
    if "text/event-stream" in ctype:
        events = []
        for line in text.splitlines():
            if line.startswith("data:"):
                payload = line[5:].strip()
                try:
                    events.append(json.loads(payload))
                except Exception:
                    events.append(payload)
        return {"events": events, "raw_text": text}
    try:
        return response.json()
    except Exception:
        return {"raw_text": text}


def main() -> None:
    key = os.getenv("GOOGLE_API_KEY")
    if not key:
        raise SystemExit("GOOGLE_API_KEY missing")
    OUT.mkdir(parents=True, exist_ok=True)

    headers = {
        "X-Goog-Api-Key": key,
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }
    report = {"mcp_url": MCP_URL, "queries": []}

    for idx, text in enumerate(QUERIES, 1):
        body = {
            "method": "tools/call",
            "params": {
                "name": "search_places",
                "arguments": {
                    "textQuery": text,
                    "languageCode": "en",
                    "regionCode": "US",
                },
            },
            "jsonrpc": "2.0",
            "id": idx,
        }
        try:
            response = requests.post(MCP_URL, headers=headers, json=body, timeout=90)
            report["queries"].append({
                "query": text,
                "http_status": response.status_code,
                "content_type": response.headers.get("content-type"),
                "response": parse_body(response),
            })
        except Exception as exc:
            report["queries"].append({"query": text, "error": f"{type(exc).__name__}: {exc}"})

    raw = json.dumps(report, ensure_ascii=False, indent=2)
    (OUT / "grounding_probe.json").write_text(raw, encoding="utf-8")
    print(raw[:40000])


if __name__ == "__main__":
    main()
