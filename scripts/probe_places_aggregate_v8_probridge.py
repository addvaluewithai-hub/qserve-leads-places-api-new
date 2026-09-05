#!/usr/bin/env python3
from __future__ import annotations

import json
import os

import requests

import build_lawyers_v8_aggregate as v8
from build_lawyers_v8_aggregate_probridge import details_pro_one, grounding_context_one

TESTS = [
    ("Miami", 25.7617, -80.1918, 3500),
    ("Phoenix", 33.4484, -112.0740, 3500),
    ("Denver", 39.7392, -104.9903, 3500),
]


def body(lat: float, lng: float, radius: int, insights: list[str]) -> dict:
    return {
        "insights": insights,
        "filter": {
            "locationFilter": {"circle": {"latLng": {"latitude": lat, "longitude": lng}, "radius": radius}},
            "typeFilter": {"includedTypes": ["lawyer"]},
            "operatingStatus": ["OPERATING_STATUS_OPERATIONAL"],
            "ratingFilter": {"minRating": 4.0, "maxRating": 5.0},
        },
    }


def call_aggregate(key: str, lat: float, lng: float, radius: int, insights: list[str]) -> tuple[int, dict]:
    r = requests.post(
        v8.AGG_URL,
        headers={"X-Goog-Api-Key": key, "Content-Type": "application/json"},
        json=body(lat, lng, radius, insights),
        timeout=60,
    )
    try:
        payload = r.json() if r.content else {}
    except Exception:
        payload = {"raw": r.text[:1000]}
    return r.status_code, payload


def parse_ids(payload: dict) -> list[str]:
    out=[]
    for item in payload.get("placeInsights") or []:
        pid=v8.normalize_place_id(item.get("place"))
        if pid and pid not in out:
            out.append(pid)
    return out


def main() -> None:
    key=os.getenv("GOOGLE_API_KEY")
    if not key:
        raise SystemExit("GOOGLE_API_KEY missing")

    report=[]
    for market,lat,lng,start_radius in TESTS:
        radius=start_radius
        count=None
        count_calls=0
        while radius >= 250:
            status,payload=call_aggregate(key,lat,lng,radius,["INSIGHT_COUNT"])
            count_calls += 1
            if status != 200:
                report.append({"market":market,"count_http":status,"error":payload})
                break
            count=int(payload.get("count") or 0)
            if count <= 100:
                break
            radius=max(250,int(radius/2))
        else:
            report.append({"market":market,"error":"failed_to_reach_leaf"})
            continue

        if report and report[-1].get("market")==market and report[-1].get("error"):
            continue
        if count is None or count <= 0 or count > 100:
            report.append({"market":market,"count":count,"final_radius_m":radius,"error":"invalid_leaf_count"})
            continue

        status,payload=call_aggregate(key,lat,lng,radius,["INSIGHT_PLACES"])
        ids=parse_ids(payload) if status==200 else []
        samples=[]
        for pid in ids[:2]:
            context=details_pro_one(key,pid)
            grounded=grounding_context_one(key,context) if context.get("ok") else {"place_id":pid,"ok":False,"reason":"details_pro_failed"}
            samples.append({"place_id":pid,"context":context,"grounding":grounded})

        row={
            "market":market,
            "count_calls":count_calls,
            "final_radius_m":radius,
            "count":count,
            "places_http":status,
            "place_ids_returned":len(ids),
            "samples":samples,
        }
        report.append(row)
        print(json.dumps(row,ensure_ascii=False),flush=True)

    print(json.dumps({"report":report},indent=2),flush=True)
    valid=[r for r in report if r.get("place_ids_returned")]
    if len(valid) != len(TESTS):
        raise SystemExit("Aggregate leaf smoke failed")
    samples=[s for r in valid for s in r.get("samples") or []]
    if not samples or not all(s.get("context",{}).get("ok") and s.get("grounding",{}).get("ok") for s in samples):
        raise SystemExit("Place Details Pro -> Grounding smoke failed")


if __name__ == "__main__":
    main()
