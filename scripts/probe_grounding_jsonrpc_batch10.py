#!/usr/bin/env python3
import json, os, re
from urllib.parse import urlparse
import requests

URL = "https://mapstools.googleapis.com/mcp"
BUSINESSES = [
    ("The Law Offices Of Alcock & Associates P.C.", "Phoenix, AZ"),
    ("The Valley Law Group", "Phoenix, AZ"),
    ("Chelle Law", "Phoenix, AZ"),
    ("DM Cantor", "Phoenix, AZ"),
    ("Fernandez Law Group", "Tampa, FL"),
    ("RHINO Lawyers", "Tampa, FL"),
    ("MattLaw", "Tampa, FL"),
    ("Jetton & Meredith", "Charlotte, NC"),
    ("Freeman & Fuson", "Nashville, TN"),
    ("The Law Office of Jacob E. Martinez", "Denver, CO"),
]
URL_RE = re.compile(r"https?://[^\s<>()\[\]{}]+", re.I)

def domain(u):
    try:
        h=(urlparse(u).hostname or "").lower()
        return h[4:] if h.startswith("www.") else h
    except Exception:
        return None

def main():
    key=os.environ["GOOGLE_API_KEY"]
    batch=[]
    for i,(name,loc) in enumerate(BUSINESSES,1):
        batch.append({
            "jsonrpc":"2.0","id":i,"method":"tools/call",
            "params":{"name":"search_places","arguments":{
                "textQuery":f"{name}, {loc} official website",
                "languageCode":"en","regionCode":"US"
            }}
        })
    r=requests.post(URL,headers={
        "X-Goog-Api-Key":key,
        "Content-Type":"application/json",
        "Accept":"application/json, text/event-stream"
    },json=batch,timeout=120)
    print(json.dumps({"http":r.status_code,"one_http_post":True,"tool_calls_in_envelope":10,"content_type":r.headers.get("content-type")},indent=2))
    text=r.text
    try:
        payload=r.json()
    except Exception:
        payload=None
    if payload is None:
        print(text[:12000])
        return
    print(json.dumps(payload,indent=2)[:30000])
    if isinstance(payload,list):
        good=0; details=[]
        for item in payload:
            structured=(((item.get("result") or {}).get("structuredContent")) or {}) if isinstance(item,dict) else {}
            places=structured.get("places") or []
            summary=structured.get("summary") or ""
            urls=URL_RE.findall(summary)
            ds=[]
            for u in urls:
                d=domain(u.rstrip(".,;:!?\"'"))
                if d and d not in ds and "google." not in d:
                    ds.append(d)
            if places or ds:
                good+=1
            details.append({"id":item.get("id") if isinstance(item,dict) else None,"places":len(places),"domains":ds[:3]})
        print(json.dumps({"batch_response_count":len(payload),"responses_with_place_or_domain":good,"details":details},indent=2))

if __name__ == "__main__":
    main()
