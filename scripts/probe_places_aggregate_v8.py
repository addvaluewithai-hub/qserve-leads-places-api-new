#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
from urllib.parse import urlparse

import requests

AGG_URL = "https://areainsights.googleapis.com/v1:computeInsights"
GROUNDING_URL = "https://mapstools.googleapis.com/mcp"
URL_RE = re.compile(r"https?://[^\s<>()\[\]{}]+", re.I)
BLOCKED = {"google.com","facebook.com","instagram.com","linkedin.com","x.com","twitter.com","yelp.com","avvo.com","findlaw.com","justia.com","lawyers.com","lawinfo.com","martindale.com","superlawyers.com"}

TESTS = [
    ("Miami", 25.7617, -80.1918, 3500),
    ("Phoenix", 33.4484, -112.0740, 3500),
    ("Denver", 39.7392, -104.9903, 3500),
]


def host(url: str | None) -> str | None:
    if not url:
        return None
    h = (urlparse(url).hostname or "").lower().strip(".")
    return h[4:] if h.startswith("www.") else (h or None)


def good_url(url: str) -> bool:
    h = host(url)
    return bool(h) and not any(h == b or h.endswith("." + b) for b in BLOCKED)


def extract_urls(text: str) -> list[str]:
    out=[]
    for raw in URL_RE.findall(text or ""):
        u=raw.rstrip(".,;:!?\"'")
        if good_url(u) and u not in out:
            out.append(u)
    return out


def agg_body(lat: float, lng: float, radius: int, insights: list[str]) -> dict:
    return {
        "insights": insights,
        "filter": {
            "locationFilter": {"circle": {"latLng": {"latitude": lat, "longitude": lng}, "radius": radius}},
            "typeFilter": {"includedTypes": ["lawyer"]},
            "operatingStatus": ["OPERATING_STATUS_OPERATIONAL"],
            "ratingFilter": {"minRating": 4.0, "maxRating": 5.0},
        },
    }


def aggregate(key: str, lat: float, lng: float, radius: int, insights: list[str]) -> dict:
    r = requests.post(
        AGG_URL,
        headers={"X-Goog-Api-Key": key, "Content-Type": "application/json"},
        json=agg_body(lat, lng, radius, insights),
        timeout=60,
    )
    try:
        payload = r.json() if r.content else {}
    except Exception:
        payload = {"raw": r.text[:1000]}
    return {"http": r.status_code, "payload": payload}


def parse_ids(payload: dict) -> list[str]:
    ids=[]
    for x in payload.get("placeInsights") or []:
        p=str(x.get("place") or "")
        if p.startswith("places/"):
            p=p.split("/",1)[1]
        if p and p not in ids:
            ids.append(p)
    return ids


def grounding(key: str, place_id: str) -> dict:
    body = {
        "method": "tools/call",
        "params": {"name": "search_places", "arguments": {"textQuery": f"Place ID {place_id} official website", "languageCode": "en", "regionCode": "US"}},
        "jsonrpc": "2.0",
        "id": place_id,
    }
    r = requests.post(GROUNDING_URL, headers={"X-Goog-Api-Key": key, "Content-Type": "application/json"}, json=body, timeout=90)
    if r.status_code != 200:
        return {"http": r.status_code, "ok": False, "error": r.text[:500]}
    p = r.json()
    structured = ((p.get("result") or {}).get("structuredContent") or {})
    ids = [x.get("id") for x in (structured.get("places") or []) if x.get("id")]
    urls = extract_urls(structured.get("summary") or "")
    return {"http": 200, "ok": place_id in ids and bool(urls), "returned_ids": ids, "urls": urls[:3]}


def main() -> None:
    key=os.getenv("GOOGLE_API_KEY")
    if not key:
        raise SystemExit("GOOGLE_API_KEY missing")
    report=[]
    for name,lat,lng,start_radius in TESTS:
        radius=start_radius
        count_calls=0
        count=None
        count_error=None
        while radius >= 250:
            a=aggregate(key,lat,lng,radius,["INSIGHT_COUNT"])
            count_calls += 1
            if a["http"] != 200:
                count_error=a["payload"]
                break
            count=int((a["payload"] or {}).get("count") or 0)
            if count <= 100:
                break
            radius=max(250,int(radius/2))
        ids=[]
        places_http=None
        places_error=None
        if count is not None and 0 < count <= 100:
            p=aggregate(key,lat,lng,radius,["INSIGHT_PLACES"])
            places_http=p["http"]
            if p["http"] == 200:
                ids=parse_ids(p["payload"] or {})
            else:
                places_error=p["payload"]
        row={
            "market":name,
            "count_http": 200 if count is not None and count_error is None else None,
            "count_calls":count_calls,
            "final_radius_m":radius,
            "count":count,
            "places_http":places_http,
            "place_ids_returned":len(ids),
            "grounding":[],
        }
        if count_error:
            row["count_error"]=count_error
        if places_error:
            row["places_error"]=places_error
        for pid in ids[:2]:
            row["grounding"].append({"place_id":pid,**grounding(key,pid)})
        report.append(row)
        print(json.dumps(row,ensure_ascii=False),flush=True)
    print(json.dumps({"report":report},indent=2))
    if any(r.get("count") is None or r.get("places_http") != 200 or not r.get("place_ids_returned") for r in report):
        raise SystemExit("Aggregate count->places smoke failed")
    tested=[g for r in report for g in r["grounding"]]
    if not tested or not all(g.get("ok") for g in tested):
        raise SystemExit("Place-ID Grounding smoke failed")

if __name__ == "__main__":
    main()
