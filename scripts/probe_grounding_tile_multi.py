#!/usr/bin/env python3
import json, os, re
from urllib.parse import urlparse
import requests

URL="https://mapstools.googleapis.com/mcp"
URL_RE=re.compile(r"https?://[^\s<>()\[\]{}]+",re.I)

def dom(u):
    try:
        h=(urlparse(u).hostname or "").lower().strip('.')
        return h[4:] if h.startswith('www.') else h
    except Exception:
        return None

def main():
    key=os.environ['GOOGLE_API_KEY']
    excluded=[
      "DM Cantor",
      "Community Legal Services",
      "Kelly Law Team Phoenix",
      "Outreach Legal",
      "Curry Pearson & Wooten PLC",
    ]
    q=("Return 5 MORE law firms in downtown Phoenix, Arizona, different from these excluded firms: "
       + "; ".join(excluded)
       + ". Include the official website for every law firm you return. Do not return any excluded firm.")
    body={
      "jsonrpc":"2.0","id":"tile-phoenix-next5","method":"tools/call",
      "params":{"name":"search_places","arguments":{
        "textQuery":q,
        "locationBias":{"circle":{"center":{"latitude":33.4484,"longitude":-112.0740},"radiusMeters":1750}},
        "languageCode":"en","regionCode":"US"
      }}
    }
    r=requests.post(URL,headers={"X-Goog-Api-Key":key,"Content-Type":"application/json","Accept":"application/json, text/event-stream"},json=body,timeout=120)
    print(json.dumps({"http":r.status_code,"grounding_requests":1,"excluded":excluded},indent=2))
    if r.status_code!=200:
        print(r.text[:5000]); return
    p=r.json(); s=((p.get('result') or {}).get('structuredContent') or {})
    places=s.get('places') or []; summary=s.get('summary') or ''
    ds=[]
    for u in URL_RE.findall(summary):
        d=dom(u.rstrip(".,;:!?\"'"))
        if d and 'google.' not in d and d not in ds: ds.append(d)
    print(json.dumps({
      "places_returned":len(places),
      "place_ids":[x.get('id') for x in places if x.get('id')],
      "domains_found":ds,
      "domain_count":len(ds),
      "summary":summary
    },indent=2))
if __name__=='__main__': main()
