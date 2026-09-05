#!/usr/bin/env python3
from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import math
import os
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import requests
import tldextract

import zip_manager
from d1_helpers import ROOT, apply_schema, make_query_client, result_rows

AGG_URL = "https://areainsights.googleapis.com/v1:computeInsights"
GROUNDING_URL = "https://mapstools.googleapis.com/mcp"
DETAILS_URL = "https://places.googleapis.com/v1/places/{place_id}"
SKU_AGG = "places_aggregate"
SKU_GROUND = "maps_grounding_lite"
SKU_DETAILS_ENT = "places_place_details_enterprise"
URL_RE = re.compile(r"https?://[^\s<>()\[\]{}]+", re.I)
TLD_EXTRACT = tldextract.TLDExtract(suffix_list_urls=None)
BLOCKED = {
    "google.com", "googleusercontent.com", "facebook.com", "instagram.com", "linkedin.com",
    "x.com", "twitter.com", "youtube.com", "tiktok.com", "yelp.com", "avvo.com",
    "findlaw.com", "justia.com", "lawyers.com", "lawinfo.com", "martindale.com",
    "martindale-hubbell.com", "superlawyers.com", "yellowpages.com", "mapquest.com",
    "bbb.org", "chamberofcommerce.com", "alignable.com", "linktr.ee", "bio.site",
    "beacons.ai", "business.site",
}
HOST_IDENTITY_BASES = {
    "wixsite.com", "wordpress.com", "weebly.com", "godaddysites.com",
    "square.site", "webflow.io", "mystrikingly.com", "site123.me",
}
V7_PROVIDERS = {
    "places_text_search_pro_min_rating4_plus_maps_grounding_lite",
    "places_text_search_enterprise_fallback_min_rating4",
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def month_key() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m")


def host(value: str | None) -> str | None:
    if not value:
        return None
    try:
        v = value if "://" in value else f"https://{value}"
        h = (urlparse(v).hostname or "").lower().strip(".")
        return h[4:] if h.startswith("www.") else (h or None)
    except Exception:
        return None


def business_domain(value: str | None) -> str | None:
    h = host(value)
    if not h:
        return None
    parts = TLD_EXTRACT(h)
    base = f"{parts.domain}.{parts.suffix}".lower() if parts.domain and parts.suffix else h
    if base in HOST_IDENTITY_BASES and h != base:
        return h
    return base


def blocked_domain(value: str | None) -> bool:
    d = business_domain(value)
    if not d:
        return True
    return d in BLOCKED or any(d.endswith("." + b) for b in BLOCKED)


def external_urls(text: str) -> list[str]:
    out: list[str] = []
    for raw in URL_RE.findall(text or ""):
        u = raw.rstrip(".,;:!?\"'")
        if not blocked_domain(u) and u not in out:
            out.append(u)
    return out


def normalize_place_id(value: str | None) -> str | None:
    if not value:
        return None
    v = str(value).strip()
    return v.split("/", 1)[1] if v.startswith("places/") else v


def display_name(value) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        return str(value.get("text") or "").strip()
    return ""


@dataclass
class Budget:
    sku: str
    cap: int
    used: int

    @property
    def remaining(self) -> int:
        return max(0, self.cap - self.used)


class Ledger:
    def __init__(self, query, campaign_id: str, run_id: str):
        self.query = query
        self.campaign_id = campaign_id
        self.run_id = run_id

    def used(self, sku: str) -> int:
        rows = result_rows(self.query(
            """SELECT COALESCE(SUM(request_count),0) AS n FROM api_usage_ledger
               WHERE campaign_id=? AND sku=? AND usage_month=?""",
            [self.campaign_id, sku, month_key()],
        ))
        return int((rows[0] if rows else {}).get("n") or 0)

    def reserve(self, budget: Budget, n: int, context: str) -> None:
        n = int(n)
        if n <= 0:
            return
        if n > budget.remaining:
            raise RuntimeError(f"zero-paid guard blocked {budget.sku}: need={n}, remaining={budget.remaining}")
        self.query(
            """INSERT INTO api_usage_ledger
               (id,campaign_id,run_id,sku,usage_month,request_count,context,created_at)
               VALUES (?,?,?,?,?,?,?,CURRENT_TIMESTAMP)""",
            [str(uuid.uuid4()), self.campaign_id, self.run_id, budget.sku, month_key(), n, context[:1200]],
        )
        budget.used += n


def ensure_v8_schema(query) -> None:
    query("""
        CREATE TABLE IF NOT EXISTS discovery_batches_v8 (
          id TEXT PRIMARY KEY,
          campaign_id TEXT NOT NULL,
          target_domains INTEGER NOT NULL,
          status TEXT NOT NULL DEFAULT 'active',
          canary_attempts INTEGER NOT NULL DEFAULT 0,
          canary_successes INTEGER NOT NULL DEFAULT 0,
          canary_passed INTEGER NOT NULL DEFAULT 0,
          created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
          completed_at TEXT,
          updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
          notes TEXT NOT NULL DEFAULT ''
        )
    """)
    query("""
        CREATE TABLE IF NOT EXISTS discovery_batch_leads_v8 (
          batch_id TEXT NOT NULL,
          lead_id TEXT NOT NULL,
          website_domain TEXT NOT NULL,
          source_state TEXT,
          source_tile TEXT,
          resolution_method TEXT NOT NULL,
          added_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
          PRIMARY KEY (batch_id, lead_id),
          UNIQUE(batch_id, website_domain)
        )
    """)
    query("""
        CREATE TABLE IF NOT EXISTS aggregate_tiles_v8 (
          id TEXT PRIMARY KEY,
          batch_id TEXT NOT NULL,
          state_code TEXT NOT NULL,
          state_order INTEGER NOT NULL,
          depth INTEGER NOT NULL,
          south REAL NOT NULL,
          west REAL NOT NULL,
          north REAL NOT NULL,
          east REAL NOT NULL,
          status TEXT NOT NULL DEFAULT 'queued',
          place_count INTEGER,
          place_ids_returned INTEGER NOT NULL DEFAULT 0,
          fresh_place_ids INTEGER NOT NULL DEFAULT 0,
          net_new_domains INTEGER NOT NULL DEFAULT 0,
          last_error TEXT NOT NULL DEFAULT '',
          updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """)
    query("CREATE INDEX IF NOT EXISTS idx_aggregate_tiles_v8_queue ON aggregate_tiles_v8(batch_id,status,depth,state_order)")
    query("""
        CREATE TABLE IF NOT EXISTS discovery_domain_reservations_v8 (
          website_domain TEXT PRIMARY KEY,
          lead_id TEXT NOT NULL,
          batch_id TEXT NOT NULL,
          source_state TEXT,
          source_tile TEXT,
          resolution_method TEXT NOT NULL,
          lead_name TEXT NOT NULL DEFAULT '',
          reserved_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """)
    query("""
        CREATE TABLE IF NOT EXISTS unresolved_place_ids_v8 (
          place_id TEXT PRIMARY KEY,
          batch_id TEXT NOT NULL,
          source_state TEXT,
          source_tile TEXT,
          reason TEXT NOT NULL,
          attempts INTEGER NOT NULL DEFAULT 1,
          updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """)


def ensure_batch(query, campaign_id: str, batch_id: str, target: int) -> dict:
    query(
        """INSERT OR IGNORE INTO discovery_batches_v8
           (id,campaign_id,target_domains,status,notes) VALUES (?,?,?,'active',?)""",
        [batch_id, campaign_id, int(target), "V8 Aggregate batch; adopts V7 pre-cancel discoveries for batch 1."],
    )
    placeholders = ",".join("?" for _ in V7_PROVIDERS)
    query(
        f"""
        INSERT OR IGNORE INTO discovery_batch_leads_v8
          (batch_id,lead_id,website_domain,source_state,source_tile,resolution_method)
        SELECT ?, s.lead_id, ld.website_domain,
               COALESCE(cl.source_area,''), COALESCE(cl.source_area,''), 'migrated_v7'
        FROM lead_discovery_screening s
        JOIN lead_domains ld ON ld.lead_id=s.lead_id
        LEFT JOIN campaign_leads cl ON cl.campaign_id=s.campaign_id AND cl.lead_id=s.lead_id
        WHERE s.campaign_id=? AND s.provider IN ({placeholders})
        """,
        [batch_id, campaign_id, *sorted(V7_PROVIDERS)],
    )
    return batch_state(query, batch_id)


def batch_state(query, batch_id: str) -> dict:
    rows = result_rows(query(
        """SELECT id,campaign_id,target_domains,status,canary_attempts,canary_successes,canary_passed
           FROM discovery_batches_v8 WHERE id=?""",
        [batch_id],
    ))
    if not rows:
        raise RuntimeError("V8 batch missing")
    row = dict(rows[0])
    c = result_rows(query("SELECT COUNT(*) AS n FROM discovery_batch_leads_v8 WHERE batch_id=?", [batch_id]))
    row["collected_domains"] = int((c[0] if c else {}).get("n") or 0)
    row["remaining_domains"] = max(0, int(row["target_domains"]) - row["collected_domains"])
    if row["remaining_domains"] == 0 and row.get("status") != "completed":
        query("UPDATE discovery_batches_v8 SET status='completed',completed_at=COALESCE(completed_at,CURRENT_TIMESTAMP),updated_at=CURRENT_TIMESTAMP WHERE id=?", [batch_id])
        row["status"] = "completed"
    return row


def state_order(plan: dict) -> list[str]:
    out=[]
    for phase in plan.get("phases") or []:
        for s in phase.get("states") or []:
            code=str(s.get("state") or "").upper().strip()
            if code and code not in out:
                out.append(code)
    return out


def state_bboxes(plan: dict, padding: float) -> list[tuple[str,int,float,float,float,float]]:
    universe = zip_manager.load_zip_universe(plan)
    order = state_order(plan)
    grouped: dict[str,list[dict]] = {s:[] for s in order}
    for row in universe:
        state=str(row.get("state_code") or "").upper()
        if state in grouped:
            grouped[state].append(row)
    roots=[]
    for idx,state in enumerate(order):
        rows=grouped.get(state) or []
        if not rows:
            continue
        lats=[float(r["latitude"]) for r in rows]
        lons=[float(r["longitude"]) for r in rows]
        south=max(-89.9,min(lats)-padding); north=min(89.9,max(lats)+padding)
        west=max(-179.9,min(lons)-padding); east=min(179.9,max(lons)+padding)
        roots.append((state,idx,south,west,north,east))
    return roots


def tile_id(batch_id: str, state: str, depth: int, s: float, w: float, n: float, e: float) -> str:
    raw=f"{batch_id}|{state}|{depth}|{s:.7f}|{w:.7f}|{n:.7f}|{e:.7f}"
    return hashlib.sha1(raw.encode()).hexdigest()


def seed_roots(query, batch_id: str, plan: dict, padding: float) -> int:
    added=0
    for state,order,s,w,n,e in state_bboxes(plan,padding):
        tid=tile_id(batch_id,state,0,s,w,n,e)
        before=result_rows(query("SELECT 1 AS x FROM aggregate_tiles_v8 WHERE id=?",[tid]))
        query(
            """INSERT OR IGNORE INTO aggregate_tiles_v8
               (id,batch_id,state_code,state_order,depth,south,west,north,east,status)
               VALUES (?,?,?,?,?,?,?,?,?,'queued')""",
            [tid,batch_id,state,order,0,s,w,n,e],
        )
        if not before:
            added+=1
    return added


def bbox_area_m2(tile: dict) -> float:
    mid=(float(tile["south"])+float(tile["north"]))/2.0
    h=max(0.0,float(tile["north"])-float(tile["south"]))*111_000.0
    w=max(0.0,float(tile["east"])-float(tile["west"]))*111_000.0*max(0.15,math.cos(math.radians(mid)))
    return h*w


def split_tile(query, tile: dict, reason: str) -> None:
    s,w,n,e=map(float,[tile["south"],tile["west"],tile["north"],tile["east"]])
    mid_lat=(s+n)/2.0; mid_lon=(w+e)/2.0
    mid=(s+n)/2.0
    h=(n-s)*111.0; wd=(e-w)*111.0*max(0.15,math.cos(math.radians(mid)))
    if wd >= h:
        boxes=[(s,w,n,mid_lon),(s,mid_lon,n,e)]
    else:
        boxes=[(s,w,mid_lat,e),(mid_lat,w,n,e)]
    depth=int(tile["depth"])+1
    for cs,cw,cn,ce in boxes:
        tid=tile_id(tile["batch_id"],tile["state_code"],depth,cs,cw,cn,ce)
        query(
            """INSERT OR IGNORE INTO aggregate_tiles_v8
               (id,batch_id,state_code,state_order,depth,south,west,north,east,status)
               VALUES (?,?,?,?,?,?,?,?,?,'queued')""",
            [tid,tile["batch_id"],tile["state_code"],int(tile["state_order"]),depth,cs,cw,cn,ce],
        )
    query("UPDATE aggregate_tiles_v8 SET status='split',last_error=?,updated_at=CURRENT_TIMESTAMP WHERE id=?",[reason[:1200],tile["id"]])


def next_tile(query, batch_id: str) -> dict | None:
    rows=result_rows(query(
        """SELECT * FROM aggregate_tiles_v8 WHERE batch_id=? AND status='queued'
           ORDER BY depth ASC,state_order ASC,id ASC LIMIT 1""",
        [batch_id],
    ))
    return dict(rows[0]) if rows else None


def polygon_body(tile: dict, insights: list[str]) -> dict:
    s,w,n,e=map(float,[tile["south"],tile["west"],tile["north"],tile["east"]])
    coords=[
        {"latitude":s,"longitude":w},
        {"latitude":s,"longitude":e},
        {"latitude":n,"longitude":e},
        {"latitude":n,"longitude":w},
        {"latitude":s,"longitude":w},
    ]
    return {
        "insights": insights,
        "filter": {
            "locationFilter": {"customArea": {"polygon": {"coordinates": coords}}},
            "typeFilter": {"includedTypes": ["lawyer"]},
            "operatingStatus": ["OPERATING_STATUS_OPERATIONAL"],
            "ratingFilter": {"minRating": 4.0, "maxRating": 5.0},
        },
    }


def aggregate_call(key: str, ledger: Ledger, budget: Budget, tile: dict, insights: list[str]) -> tuple[int,list[str],dict]:
    ledger.reserve(budget,1,f"tile={tile['id']};state={tile['state_code']};depth={tile['depth']};insights={','.join(insights)}")
    r=requests.post(AGG_URL,headers={"X-Goog-Api-Key":key,"Content-Type":"application/json"},json=polygon_body(tile,insights),timeout=60)
    try:
        payload=r.json() if r.content else {}
    except Exception:
        payload={"raw":r.text[:1200]}
    if r.status_code != 200:
        raise RuntimeError(f"Aggregate HTTP {r.status_code}: {json.dumps(payload)[:1500]}")
    count=int(payload.get("count") or 0)
    ids=[]
    for item in payload.get("placeInsights") or []:
        pid=normalize_place_id(item.get("place"))
        if pid and pid not in ids:
            ids.append(pid)
    return count,ids,payload


def global_seen(query) -> tuple[set[str],set[str]]:
    ids={str(r["id"]) for r in result_rows(query("SELECT id FROM leads")) if r.get("id")}
    domains=set()
    for r in result_rows(query("SELECT lead_id,website_domain FROM lead_domains")):
        if r.get("lead_id"):
            ids.add(str(r["lead_id"]))
        d=business_domain(r.get("website_domain"))
        if d:
            domains.add(d)
    for r in result_rows(query("SELECT lead_id,website_domain FROM outreach_suppression WHERE suppressed=1 AND (reengage_after IS NULL OR reengage_after>CURRENT_TIMESTAMP)")):
        if r.get("lead_id"):
            ids.add(str(r["lead_id"]))
        d=business_domain(r.get("website_domain"))
        if d:
            domains.add(d)
    return ids,domains


def grounding_one(key: str, pid: str) -> dict:
    body={
        "method":"tools/call",
        "params":{"name":"search_places","arguments":{"textQuery":f"Place ID {pid} official website","languageCode":"en","regionCode":"US"}},
        "jsonrpc":"2.0","id":pid,
    }
    try:
        r=requests.post(GROUNDING_URL,headers={"X-Goog-Api-Key":key,"Content-Type":"application/json"},json=body,timeout=90)
        if r.status_code != 200:
            return {"place_id":pid,"ok":False,"reason":f"HTTP {r.status_code}"}
        payload=r.json(); structured=((payload.get("result") or {}).get("structuredContent") or {})
        places=structured.get("places") or []
        ids=[normalize_place_id(p.get("id") or p.get("place")) for p in places]
        if pid not in ids:
            return {"place_id":pid,"ok":False,"reason":"place_id_identity_mismatch","returned_ids":[x for x in ids if x]}
        urls=external_urls(structured.get("summary") or "")
        same=next((p for p in places if normalize_place_id(p.get("id") or p.get("place"))==pid),{})
        direct=same.get("websiteUri") or same.get("website")
        if direct and not blocked_domain(direct):
            urls=[direct,*[u for u in urls if business_domain(u)!=business_domain(direct)]]
        if not urls:
            return {"place_id":pid,"ok":False,"reason":"no_external_website"}
        name=display_name(same.get("displayName")) or str(same.get("name") or "").strip()
        return {"place_id":pid,"ok":True,"url":urls[0],"domain":business_domain(urls[0]),"name":name,"method":"maps_grounding_lite"}
    except Exception as exc:
        return {"place_id":pid,"ok":False,"reason":f"{type(exc).__name__}: {exc}"}


def details_one(key: str, pid: str) -> dict:
    try:
        r=requests.get(
            DETAILS_URL.format(place_id=pid),
            headers={"X-Goog-Api-Key":key,"X-Goog-FieldMask":"id,displayName,businessStatus,websiteUri"},
            timeout=60,
        )
        if r.status_code != 200:
            return {"place_id":pid,"ok":False,"reason":f"HTTP {r.status_code}"}
        p=r.json(); url=p.get("websiteUri")
        if p.get("businessStatus") not in {None,"OPERATIONAL"}:
            return {"place_id":pid,"ok":False,"reason":"not_operational"}
        if not url or blocked_domain(url):
            return {"place_id":pid,"ok":False,"reason":"missing_or_blocked_website"}
        return {"place_id":pid,"ok":True,"url":url,"domain":business_domain(url),"name":display_name(p.get("displayName")),"method":"place_details_enterprise_fallback"}
    except Exception as exc:
        return {"place_id":pid,"ok":False,"reason":f"{type(exc).__name__}: {exc}"}


def parallel(fn, key: str, ids: list[str], workers: int) -> list[dict]:
    if not ids:
        return []
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(max(1,workers),len(ids))) as ex:
        return list(ex.map(lambda pid: fn(key,pid),ids))


def reserve_domain(query,batch_id:str,pid:str,domain:str,state:str,tile_id_value:str,method:str,name:str) -> bool:
    existing=result_rows(query("SELECT lead_id FROM lead_domains WHERE website_domain=? LIMIT 1",[domain]))
    if existing and str(existing[0].get("lead_id")) != pid:
        return False
    query(
        """INSERT OR IGNORE INTO discovery_domain_reservations_v8
           (website_domain,lead_id,batch_id,source_state,source_tile,resolution_method,lead_name)
           VALUES (?,?,?,?,?,?,?)""",
        [domain,pid,batch_id,state,tile_id_value,method,name or ""],
    )
    owner=result_rows(query("SELECT lead_id FROM discovery_domain_reservations_v8 WHERE website_domain=?",[domain]))
    return bool(owner) and str(owner[0].get("lead_id"))==pid


def persist_resolved(query,campaign:dict,batch_id:str,state:str,tile_id_value:str,row:dict) -> bool:
    pid=str(row["place_id"]); d=business_domain(row.get("domain") or row.get("url")); method=str(row.get("method") or "")
    if not d or blocked_domain(d):
        return False
    name=(row.get("name") or d).strip()
    if not reserve_domain(query,batch_id,pid,d,state,tile_id_value,method,name):
        return False
    site=f"https://{d}/"; batch=f"{campaign['id']}:{batch_id}"
    notes="V8 discovery: Places Aggregate lawyer + operational + rating>=4.0; no review-count gate. Official domain resolved after global Place-ID dedupe. Crawl4AI deferred to evidence stage."
    query(
        """INSERT OR IGNORE INTO leads
           (id,name,business_status,website,source_label,source_query,source_type,source_area,status,notes,first_source_batch,latest_source_batch)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        [pid,name,"OPERATIONAL",site,campaign.get("name") or campaign["id"],"lawyer",campaign.get("vertical") or "legal",state,"Ready for Crawl Evidence",notes,batch,batch],
    )
    query(
        """INSERT OR IGNORE INTO campaign_leads
           (campaign_id,lead_id,qualified,quality_score,qualification_reason,source_area,source_query,source_term,status,last_run_id)
           VALUES (?,?,0,0,'working_set_ready_for_crawl_evidence',?,'lawyer',?,'Ready for Crawl Evidence',?)""",
        [campaign["id"],pid,state,f"aggregate:{state}",batch_id],
    )
    query(
        """INSERT OR IGNORE INTO lead_discovery_screening
           (campaign_id,lead_id,provider,source_zip,quality_gate_passed,screened_at,notes)
           VALUES (?,?,?,NULL,1,?,?)""",
        [campaign["id"],pid,"places_aggregate_rating4_plus_"+method,now_iso(),"V8 Aggregate filter: lawyer, operational, minRating 4.0; no review-count gate."],
    )
    query("INSERT OR IGNORE INTO lead_domains (lead_id,website_domain,verified,source) VALUES (?,?,0,?)",[pid,d,method+"_seed"])
    verify=result_rows(query("SELECT website_domain FROM lead_domains WHERE lead_id=?",[pid]))
    if not verify or business_domain(verify[0].get("website_domain")) != d:
        return False
    query(
        """INSERT OR IGNORE INTO discovery_batch_leads_v8
           (batch_id,lead_id,website_domain,source_state,source_tile,resolution_method)
           VALUES (?,?,?,?,?,?)""",
        [batch_id,pid,d,state,tile_id_value,method],
    )
    return True


def repair_reservations(query,campaign:dict,batch_id:str) -> int:
    rows=result_rows(query(
        """SELECT r.* FROM discovery_domain_reservations_v8 r
           LEFT JOIN discovery_batch_leads_v8 b ON b.batch_id=r.batch_id AND b.lead_id=r.lead_id
           WHERE r.batch_id=? AND b.lead_id IS NULL""",
        [batch_id],
    ))
    repaired=0
    for r in rows:
        fake={"place_id":r["lead_id"],"domain":r["website_domain"],"name":r.get("lead_name") or r["website_domain"],"method":r["resolution_method"]}
        if persist_resolved(query,campaign,batch_id,r.get("source_state") or "",r.get("source_tile") or "",fake):
            repaired+=1
    return repaired


def record_unresolved(query,batch_id:str,state:str,tile_id_value:str,row:dict) -> None:
    query(
        """INSERT INTO unresolved_place_ids_v8 (place_id,batch_id,source_state,source_tile,reason,attempts,updated_at)
           VALUES (?,?,?,?,?,1,CURRENT_TIMESTAMP)
           ON CONFLICT(place_id) DO UPDATE SET reason=excluded.reason,attempts=attempts+1,updated_at=CURRENT_TIMESTAMP""",
        [row["place_id"],batch_id,state,tile_id_value,str(row.get("reason") or "unresolved")[:1200]],
    )


def tile_stats(query,batch_id:str) -> dict:
    rows=result_rows(query("SELECT status,COUNT(*) AS n,SUM(COALESCE(place_count,0)) AS places,SUM(fresh_place_ids) AS fresh,SUM(net_new_domains) AS new_domains FROM aggregate_tiles_v8 WHERE batch_id=? GROUP BY status",[batch_id]))
    return {str(r["status"]):r for r in rows}


def write_checkpoint(out_dir:Path,query,batch_id:str,budgets:dict,run_accepted:list[dict],last_tile:dict|None,stop_reason:str|None=None) -> None:
    out_dir.mkdir(parents=True,exist_ok=True)
    state=batch_state(query,batch_id)
    payload={
        "batch":state,
        "budgets":{k:{"sku":b.sku,"cap":b.cap,"used":b.used,"remaining":b.remaining} for k,b in budgets.items()},
        "tile_status":tile_stats(query,batch_id),
        "run_accepted":len(run_accepted),
        "last_tile":last_tile,
        "stop_reason":stop_reason,
        "updated_at":now_iso(),
    }
    (out_dir/"checkpoint.json").write_text(json.dumps(payload,indent=2),encoding="utf-8")
    with (out_dir/"accepted-this-run.jsonl").open("w",encoding="utf-8") as f:
        for r in run_accepted:
            f.write(json.dumps(r,ensure_ascii=False)+"\n")


def update_canary(query,batch_id:str,results:list[dict],attempt_target:int,min_successes:int) -> tuple[bool,bool]:
    state=batch_state(query,batch_id)
    if int(state.get("canary_passed") or 0):
        return True,False
    remaining=max(0,attempt_target-int(state.get("canary_attempts") or 0))
    sample=results[:remaining]
    if sample:
        successes=sum(1 for r in sample if r.get("ok"))
        query("UPDATE discovery_batches_v8 SET canary_attempts=canary_attempts+?,canary_successes=canary_successes+?,updated_at=CURRENT_TIMESTAMP WHERE id=?",[len(sample),successes,batch_id])
    state=batch_state(query,batch_id)
    attempts=int(state.get("canary_attempts") or 0); successes=int(state.get("canary_successes") or 0)
    if attempts >= attempt_target:
        if successes >= min_successes:
            query("UPDATE discovery_batches_v8 SET canary_passed=1,updated_at=CURRENT_TIMESTAMP WHERE id=?",[batch_id])
            return True,False
        return False,True
    return False,False


def main() -> None:
    ap=argparse.ArgumentParser(description="V8: Places Aggregate recursive US lawyer discovery -> Grounding Lite -> Place Details Enterprise fallback")
    ap.add_argument("--campaign",default="lawyers-us")
    ap.add_argument("--batch-id",default="lawyers-us:v8-batch-01-of-09")
    ap.add_argument("--target",type=int,default=2000)
    ap.add_argument("--out-dir",default="out/lawyers-us-v8-batch1-2000")
    ap.add_argument("--workers",type=int,default=8)
    args=ap.parse_args()

    key=os.getenv("GOOGLE_API_KEY")
    if not key:
        raise SystemExit("GOOGLE_API_KEY required")
    campaign=zip_manager.load_campaign(args.campaign); plan=zip_manager.load_plan(campaign); google=campaign.get("google") or {}
    query=make_query_client(); apply_schema(query); ensure_v8_schema(query)
    batch=ensure_batch(query,campaign["id"],args.batch_id,args.target)
    repaired=repair_reservations(query,campaign,args.batch_id)
    batch=batch_state(query,args.batch_id)
    print(json.dumps({"batch_start":batch,"repaired_reservations":repaired},indent=2),flush=True)
    if batch["remaining_domains"] <= 0:
        print("Batch already complete; no API calls required.")
        return

    run_id=f"v8-{uuid.uuid4()}"; ledger=Ledger(query,campaign["id"],run_id)
    budgets={
        "aggregate":Budget(SKU_AGG,int(google.get("monthly_places_aggregate_request_budget") or 4800),ledger.used(SKU_AGG)),
        "grounding":Budget(SKU_GROUND,int(google.get("monthly_grounding_lite_request_budget") or 9500),ledger.used(SKU_GROUND)),
        "details":Budget(SKU_DETAILS_ENT,int(google.get("monthly_place_details_enterprise_request_budget") or 900),ledger.used(SKU_DETAILS_ENT)),
    }
    padding=float(google.get("aggregate_state_bbox_padding_degrees") or 0.12)
    roots=seed_roots(query,args.batch_id,plan,padding)
    print(json.dumps({"root_tiles_added":roots,"budgets":{k:b.__dict__|{"remaining":b.remaining} for k,b in budgets.items()}},indent=2),flush=True)

    existing_ids,existing_domains=global_seen(query)
    run_accepted=[]; out_dir=ROOT/args.out_dir; stop_reason=None; last_tile=None
    canary_attempt_target=int(google.get("grounding_place_id_canary_attempts") or 10)
    canary_min_success=int(google.get("grounding_place_id_canary_min_successes") or 8)

    while True:
        batch=batch_state(query,args.batch_id)
        if batch["remaining_domains"] <= 0:
            stop_reason="target_reached"; break
        if budgets["aggregate"].remaining <= 0:
            stop_reason="aggregate_free_guard_exhausted"; break
        tile=next_tile(query,args.batch_id)
        if not tile:
            stop_reason="aggregate_tile_queue_exhausted"; break
        last_tile={k:tile.get(k) for k in ["id","state_code","depth","south","west","north","east"]}

        if bbox_area_m2(tile) > 1.8e12:
            split_tile(query,tile,"pre_split_area_guard")
            write_checkpoint(out_dir,query,args.batch_id,budgets,run_accepted,last_tile)
            continue

        try:
            count,ids,_=aggregate_call(key,ledger,budgets["aggregate"],tile,["INSIGHT_COUNT","INSIGHT_PLACES"])
            if 0 < count <= 100 and not ids and budgets["aggregate"].remaining > 0:
                _,ids,_=aggregate_call(key,ledger,budgets["aggregate"],tile,["INSIGHT_PLACES"])
        except Exception as exc:
            msg=f"{type(exc).__name__}: {exc}"
            query("UPDATE aggregate_tiles_v8 SET status='failed',last_error=?,updated_at=CURRENT_TIMESTAMP WHERE id=?",[msg[:1200],tile["id"]])
            write_checkpoint(out_dir,query,args.batch_id,budgets,run_accepted,last_tile,"aggregate_error")
            if "SERVICE_DISABLED" in msg or "PERMISSION_DENIED" in msg or "403" in msg:
                stop_reason="aggregate_service_unavailable"; break
            continue

        if count <= 0:
            query("UPDATE aggregate_tiles_v8 SET status='empty',place_count=0,place_ids_returned=0,updated_at=CURRENT_TIMESTAMP WHERE id=?",[tile["id"]])
            write_checkpoint(out_dir,query,args.batch_id,budgets,run_accepted,last_tile)
            continue
        if count > 100:
            query("UPDATE aggregate_tiles_v8 SET place_count=?,place_ids_returned=?,updated_at=CURRENT_TIMESTAMP WHERE id=?",[count,len(ids),tile["id"]])
            split_tile(query,tile,f"count={count}>100")
            write_checkpoint(out_dir,query,args.batch_id,budgets,run_accepted,last_tile)
            continue
        if not ids:
            query("UPDATE aggregate_tiles_v8 SET status='failed',place_count=?,last_error='count<=100 but no place IDs returned',updated_at=CURRENT_TIMESTAMP WHERE id=?",[count,tile["id"]])
            write_checkpoint(out_dir,query,args.batch_id,budgets,run_accepted,last_tile)
            continue

        fresh=[pid for pid in ids if pid not in existing_ids]
        query("UPDATE aggregate_tiles_v8 SET place_count=?,place_ids_returned=?,fresh_place_ids=?,updated_at=CURRENT_TIMESTAMP WHERE id=?",[count,len(ids),len(fresh),tile["id"]])
        if not fresh:
            query("UPDATE aggregate_tiles_v8 SET status='leaf_complete',updated_at=CURRENT_TIMESTAMP WHERE id=?",[tile["id"]])
            write_checkpoint(out_dir,query,args.batch_id,budgets,run_accepted,last_tile)
            continue

        needed=int(batch_state(query,args.batch_id)["remaining_domains"])
        candidates=fresh[:min(len(fresh),needed+20)]
        resolved=[]

        if budgets["grounding"].remaining > 0 and candidates:
            n=min(len(candidates),budgets["grounding"].remaining)
            ground_ids=candidates[:n]
            ledger.reserve(budgets["grounding"],n,f"tile={tile['id']};state={tile['state_code']};place_id_resolution")
            ground_results=parallel(grounding_one,key,ground_ids,args.workers)
            _,canary_failed=update_canary(query,args.batch_id,ground_results,canary_attempt_target,canary_min_success)
            for r in ground_results:
                if r.get("ok") and r.get("domain") and not blocked_domain(r.get("domain")):
                    resolved.append(r)
                else:
                    record_unresolved(query,args.batch_id,tile["state_code"],tile["id"],r)
            if canary_failed:
                stop_reason="grounding_place_id_canary_failed"
                write_checkpoint(out_dir,query,args.batch_id,budgets,run_accepted,last_tile,stop_reason)
                break
            candidates=candidates[n:]

        if candidates and budgets["grounding"].remaining <= 0 and budgets["details"].remaining > 0:
            n=min(len(candidates),budgets["details"].remaining)
            detail_ids=candidates[:n]
            ledger.reserve(budgets["details"],n,f"tile={tile['id']};state={tile['state_code']};after_grounding_exhausted")
            detail_results=parallel(details_one,key,detail_ids,args.workers)
            for r in detail_results:
                if r.get("ok") and r.get("domain") and not blocked_domain(r.get("domain")):
                    resolved.append(r)
                else:
                    record_unresolved(query,args.batch_id,tile["state_code"],tile["id"],r)

        new_here=0
        for r in resolved:
            batch_now=batch_state(query,args.batch_id)
            if batch_now["remaining_domains"] <= 0:
                break
            pid=str(r["place_id"]); d=business_domain(r.get("domain"))
            if pid in existing_ids or not d or d in existing_domains:
                continue
            if persist_resolved(query,campaign,args.batch_id,tile["state_code"],tile["id"],r):
                existing_ids.add(pid); existing_domains.add(d); new_here+=1
                item={"place_id":pid,"website_domain":d,"state":tile["state_code"],"tile":tile["id"],"resolution_method":r.get("method")}
                run_accepted.append(item)
                print(json.dumps({"accepted":item,"batch_collected":batch_state(query,args.batch_id)["collected_domains"]}),flush=True)

        query("UPDATE aggregate_tiles_v8 SET status='leaf_complete',net_new_domains=?,updated_at=CURRENT_TIMESTAMP WHERE id=?",[new_here,tile["id"]])
        write_checkpoint(out_dir,query,args.batch_id,budgets,run_accepted,last_tile)
        log_payload={
            "tile":last_tile,
            "count":count,
            "ids":len(ids),
            "fresh_ids":len(fresh),
            "new_domains":new_here,
            "batch":batch_state(query,args.batch_id),
            "budgets":{k:b.remaining for k,b in budgets.items()},
        }
        print(json.dumps(log_payload),flush=True)

        if budgets["grounding"].remaining <= 0 and budgets["details"].remaining <= 0 and batch_state(query,args.batch_id)["remaining_domains"] > 0:
            stop_reason="domain_resolution_free_guards_exhausted"; break

    final=batch_state(query,args.batch_id)
    if final["remaining_domains"] <= 0:
        query("UPDATE discovery_batches_v8 SET status='completed',completed_at=COALESCE(completed_at,CURRENT_TIMESTAMP),updated_at=CURRENT_TIMESTAMP WHERE id=?",[args.batch_id])
    else:
        query("UPDATE discovery_batches_v8 SET status='partial',updated_at=CURRENT_TIMESTAMP WHERE id=?",[args.batch_id])
    write_checkpoint(out_dir,query,args.batch_id,budgets,run_accepted,last_tile,stop_reason)
    summary={"batch":batch_state(query,args.batch_id),"run_accepted":len(run_accepted),"stop_reason":stop_reason,"budgets":{k:{"used":b.used,"cap":b.cap,"remaining":b.remaining} for k,b in budgets.items()},"tile_status":tile_stats(query,args.batch_id),"completed_at":now_iso()}
    (out_dir/"summary.json").write_text(json.dumps(summary,indent=2),encoding="utf-8")
    print(json.dumps(summary,indent=2),flush=True)
    if stop_reason not in {"target_reached",None} and final["remaining_domains"]>0:
        raise SystemExit(f"V8 partial stop: {stop_reason}; remaining={final['remaining_domains']}")


if __name__ == "__main__":
    main()
