#!/usr/bin/env python3
import json
import os
import re
from urllib.parse import urlparse

import requests

GROUNDING_URL = "https://mapstools.googleapis.com/mcp"
URL_RE = re.compile(r"https?://[^\s<>()\[\]{}]+", re.I)

BUSINESSES = [
    {"name": "The Law Offices Of Alcock & Associates", "location": "Phoenix, AZ", "expected_domain": "alcocklaw.com"},
    {"name": "The Valley Law Group", "location": "Phoenix, AZ", "expected_domain": "thevalleylawgroup.com"},
    {"name": "Colburn Hintze Maletta", "location": "Phoenix, AZ", "expected_domain": "chmlaw.com"},
    {"name": "DM Cantor", "location": "Phoenix, AZ", "expected_domain": "dmcantor.com"},
    {"name": "Fernandez Law Group", "location": "Tampa, FL", "expected_domain": "thefernandezlawgroup.com"},
    {"name": "RHINO Lawyers", "location": "Tampa, FL", "expected_domain": "rhinolawyers.com"},
    {"name": "MattLaw", "location": "Tampa, FL", "expected_domain": "mattlaw.com"},
    {"name": "Jetton & Meredith", "location": "Charlotte, NC", "expected_domain": "jettonmeredithlaw.com"},
    {"name": "Freeman & Fuson", "location": "Nashville, TN", "expected_domain": "freemanfuson.com"},
    {"name": "Jacob Martinez", "location": "Denver, CO", "expected_domain": "denvercriminaldefense.com"},
]


def domain(url: str):
    try:
        h = (urlparse(url).hostname or "").lower().strip(".")
        return h[4:] if h.startswith("www.") else h
    except Exception:
        return ""


def main():
    key = os.getenv("GOOGLE_API_KEY")
    if not key:
        raise SystemExit("GOOGLE_API_KEY missing")

    lines = [
        "Find the official website for EACH of these 10 US law firms. Treat them as 10 separate businesses and return as many exact matching places as possible. Do not substitute similarly named businesses."
    ]
    for i, b in enumerate(BUSINESSES, 1):
        lines.append(f"{i}. {b['name']} — {b['location']}")
    text_query = "\n".join(lines)

    body = {
        "method": "tools/call",
        "params": {
            "name": "search_places",
            "arguments": {
                "textQuery": text_query,
                "languageCode": "en",
                "regionCode": "US"
            }
        },
        "jsonrpc": "2.0",
        "id": "grounding-multi10-one-request"
    }

    r = requests.post(
        GROUNDING_URL,
        headers={"X-Goog-Api-Key": key, "Content-Type": "application/json"},
        json=body,
        timeout=120,
    )
    print(json.dumps({"http": r.status_code, "request_count": 1, "business_count": 10}, ensure_ascii=False))
    if r.status_code != 200:
        print(r.text[:5000])
        raise SystemExit(1)

    payload = r.json()
    structured = ((payload.get("result") or {}).get("structuredContent") or {})
    summary = structured.get("summary") or ""
    places = structured.get("places") or []
    urls = URL_RE.findall(summary)
    domains = sorted({domain(u.rstrip(".,;:!?\"'")) for u in urls if domain(u.rstrip(".,;:!?\"'"))})

    expected = [b["expected_domain"] for b in BUSINESSES]
    matched = [d for d in expected if d in domains]

    report = {
        "single_grounding_request": True,
        "businesses_asked": 10,
        "places_returned": len(places),
        "place_ids_returned": [p.get("id") for p in places if p.get("id")],
        "domains_found_in_summary": domains,
        "expected_domains_matched": matched,
        "expected_match_count": len(matched),
        "expected_domains": expected,
        "summary": summary,
        "places": places,
    }
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
