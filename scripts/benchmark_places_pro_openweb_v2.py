#!/usr/bin/env python3
from __future__ import annotations

import base64
import csv
import json
import os
import re
import time
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

import requests
from bs4 import BeautifulSoup

SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"
GROUNDING_URL = "https://mapstools.googleapis.com/mcp"
OUT = Path("out/places-pro-openweb-benchmark-v2")

MARKETS = ["Phoenix, AZ", "Tampa, FL", "Charlotte, NC", "Nashville, TN", "Denver, CO"]
PAGE_SIZE = 10
MIN_RATING = 4.0
PRO_MASK = ",".join([
    "places.id", "places.displayName", "places.formattedAddress", "places.businessStatus"
])
ENTERPRISE_MASK = PRO_MASK + ",places.websiteUri,places.rating,places.userRatingCount"

BLOCKED = {
    "google.com", "bing.com", "duckduckgo.com", "g.page", "facebook.com", "instagram.com",
    "linkedin.com", "x.com", "twitter.com", "youtube.com", "yelp.com", "avvo.com",
    "findlaw.com", "justia.com", "lawyers.com", "lawinfo.com", "martindale.com",
    "superlawyers.com", "yellowpages.com", "mapquest.com", "bbb.org", "wikipedia.org",
    "chamberofcommerce.com", "expertise.com", "thumbtack.com", "alignable.com",
}
STOP = {
    "law", "lawyer", "lawyers", "attorney", "attorneys", "firm", "group", "office", "offices",
    "the", "and", "of", "pc", "pllc", "llc", "pa", "ltd", "inc", "legal", "services",
    "injury", "personal"
}
URL_RE = re.compile(r"https?://[^\s<>()\[\]{}]+", re.I)
SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/140 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
})


def domain(url: str | None) -> str | None:
    if not url:
        return None
    try:
        h = (urlparse(url).hostname or "").lower().strip(".")
        return h[4:] if h.startswith("www.") else (h or None)
    except Exception:
        return None


def is_blocked(d: str | None) -> bool:
    return not d or any(d == x or d.endswith("." + x) for x in BLOCKED)


def tokens(name: str) -> list[str]:
    return [
        t for t in re.findall(r"[a-z0-9]+", (name or "").lower())
        if len(t) >= 3 and t not in STOP
    ]


def decode_bing_url(href: str) -> str:
    if not href:
        return href
    try:
        p = urlparse(href)
        if "bing.com" not in (p.hostname or ""):
            return href
        u = (parse_qs(p.query).get("u") or [None])[0]
        if not u:
            return href
        if u.startswith("a1"):
            raw = u[2:]
            raw += "=" * (-len(raw) % 4)
            decoded = base64.urlsafe_b64decode(raw.encode()).decode("utf-8", "replace")
            if decoded.startswith("http"):
                return decoded
    except Exception:
        pass
    return href


def bing_search(query: str) -> tuple[list[dict], str | None]:
    try:
        r = SESSION.get("https://www.bing.com/search", params={"q": query, "count": 10, "setlang": "en-US"}, timeout=20)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        out = []
        for li in soup.select("li.b_algo")[:10]:
            a = li.select_one("h2 a")
            if not a:
                continue
            target = decode_bing_url(a.get("href") or "")
            sn = li.select_one(".b_caption p")
            out.append({
                "url": target,
                "domain": domain(target),
                "title": a.get_text(" ", strip=True),
                "snippet": sn.get_text(" ", strip=True) if sn else "",
            })
        return out, None
    except Exception as exc:
        return [], f"{type(exc).__name__}: {exc}"


def fetch_site(url: str) -> dict:
    try:
        r = SESSION.get(url, timeout=15, allow_redirects=True)
        text = r.text[:250000] if "text" in (r.headers.get("content-type") or "") else ""
        soup = BeautifulSoup(text, "html.parser") if text else None
        page_text = soup.get_text(" ", strip=True)[:30000].lower() if soup else ""
        title = soup.title.get_text(" ", strip=True).lower() if soup and soup.title else ""
        return {
            "ok": 200 <= r.status_code < 500 and not is_blocked(domain(r.url)),
            "status": r.status_code,
            "url": r.url,
            "domain": domain(r.url),
            "text": (title + " " + page_text)[:35000],
            "error": None,
        }
    except Exception as exc:
        return {"ok": False, "status": None, "url": None, "domain": None, "text": "", "error": f"{type(exc).__name__}: {exc}"}


def candidate_score(name: str, result: dict, page: dict) -> float:
    d = page.get("domain") or result.get("domain") or ""
    if is_blocked(d):
        return -100
    ts = tokens(name)
    dtext = d.replace("-", " ").replace(".", " ")
    hay = " ".join([result.get("title") or "", result.get("snippet") or "", page.get("text") or ""]).lower()
    score = 0.0
    for t in ts:
        if t in dtext:
            score += 3.0
        elif t in hay:
            score += 1.0
    if any(x in hay for x in (" law ", "law firm", "attorney", "legal", "lawyer")):
        score += 1.5
    return score


def resolve_open_web(name: str, market: str) -> dict:
    query = f'"{name}" "{market}" law official website'
    results, err = bing_search(query)
    inspected = []
    best = None
    for result in results[:8]:
        if is_blocked(result.get("domain")):
            continue
        page = fetch_site(result["url"])
        score = candidate_score(name, result, page)
        item = {**result, "final_url": page.get("url"), "final_domain": page.get("domain"), "score": score, "http_status": page.get("status"), "error": page.get("error")}
        inspected.append(item)
        if page.get("ok") and score >= 4.0 and (best is None or score > best["score"]):
            best = item
    return {
        "method": "open_web" if best else None,
        "url": best.get("final_url") if best else None,
        "domain": best.get("final_domain") if best else None,
        "score": best.get("score") if best else None,
        "query": query,
        "error": err,
        "candidates": inspected,
    }


def external_urls(summary: str) -> list[str]:
    seen, out = set(), []
    for raw in URL_RE.findall(summary or ""):
        u = raw.rstrip(".,;:!?\"'")
        d = domain(u)
        if is_blocked(d) or d == "googleusercontent.com" or (d and d.endswith(".googleusercontent.com")):
            continue
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out


def resolve_grounding(key: str, place_id: str, name: str, address: str) -> dict:
    body = {
        "method": "tools/call",
        "params": {
            "name": "search_places",
            "arguments": {
                "textQuery": f"{name}, {address} official website",
                "languageCode": "en",
                "regionCode": "US",
            },
        },
        "jsonrpc": "2.0",
        "id": place_id,
    }
    headers = {"X-Goog-Api-Key": key, "Content-Type": "application/json"}
    try:
        r = SESSION.post(GROUNDING_URL, headers=headers, json=body, timeout=60)
        if r.status_code != 200:
            return {"method": None, "url": None, "domain": None, "identity_match": False, "error": f"HTTP {r.status_code}: {r.text[:500]}", "summary": ""}
        payload = r.json()
        structured = ((payload.get("result") or {}).get("structuredContent") or {})
        summary = structured.get("summary") or ""
        places = structured.get("places") or []
        ids = [p.get("id") for p in places if p.get("id")]
        identity = place_id in ids
        urls = external_urls(summary)
        u = urls[0] if identity and urls else None
        return {"method": "grounding_lite" if u else None, "url": u, "domain": domain(u), "identity_match": identity, "error": None, "summary": summary, "returned_place_ids": ids}
    except Exception as exc:
        return {"method": None, "url": None, "domain": None, "identity_match": False, "error": f"{type(exc).__name__}: {exc}", "summary": ""}


def places_search(key: str, market: str, mask: str) -> tuple[int, dict]:
    body = {
        "textQuery": f"lawyer in {market}",
        "includedType": "lawyer",
        "strictTypeFiltering": True,
        "minRating": MIN_RATING,
        "pageSize": PAGE_SIZE,
        "regionCode": "US",
        "languageCode": "en",
    }
    headers = {"X-Goog-Api-Key": key, "X-Goog-FieldMask": mask, "Content-Type": "application/json"}
    r = SESSION.post(SEARCH_URL, headers=headers, json=body, timeout=45)
    try:
        return r.status_code, r.json()
    except Exception:
        return r.status_code, {"raw": r.text[:1000]}


def display_name(place: dict) -> str:
    return ((place.get("displayName") or {}).get("text") or "")


def write_csv(path: Path, rows: list[dict]) -> None:
    fields = ["place_id", "market", "name", "address", "enterprise_domain", "openweb_domain", "grounding_domain", "final_domain", "resolver_method", "domain_match", "enterprise_rating", "enterprise_review_count"]
    with path.open("w", encoding="utf-8", newline="") as h:
        w = csv.DictWriter(h, fieldnames=fields, extrasaction="ignore")
        w.writeheader(); w.writerows(rows)


def main() -> None:
    key = os.getenv("GOOGLE_API_KEY")
    if not key:
        raise SystemExit("GOOGLE_API_KEY missing")
    OUT.mkdir(parents=True, exist_ok=True)

    rows, markets = [], []
    grounding_calls = 0
    for market in MARKETS:
        ps, pp = places_search(key, market, PRO_MASK)
        es, ep = places_search(key, market, ENTERPRISE_MASK)
        pro = pp.get("places") or [] if ps == 200 else []
        ent = ep.get("places") or [] if es == 200 else []
        byid = {p.get("id"): p for p in ent if p.get("id")}
        same = len({p.get("id") for p in pro if p.get("id")} & set(byid))
        markets.append({"market": market, "pro_status": ps, "enterprise_status": es, "pro_results": len(pro), "enterprise_results": len(ent), "same_place_ids": same})
        print(f"MARKET {market}: pro={ps}/{len(pro)} enterprise={es}/{len(ent)} same_ids={same}")

        for p in pro:
            pid = p.get("id")
            if not pid:
                continue
            e = byid.get(pid) or {}
            name = display_name(p) or display_name(e)
            address = p.get("formattedAddress") or e.get("formattedAddress") or ""
            truth_url = e.get("websiteUri")
            truth_domain = domain(truth_url)
            ow = resolve_open_web(name, market)
            g = {"method": None, "url": None, "domain": None, "identity_match": False, "error": None, "summary": ""}
            if not ow.get("domain"):
                grounding_calls += 1
                g = resolve_grounding(key, pid, name, address)
            final_domain = ow.get("domain") or g.get("domain")
            method = ow.get("method") or g.get("method")
            match = bool(truth_domain and final_domain and truth_domain == final_domain)
            row = {
                "place_id": pid, "market": market, "name": name, "address": address,
                "enterprise_url": truth_url, "enterprise_domain": truth_domain,
                "enterprise_rating": e.get("rating"), "enterprise_review_count": e.get("userRatingCount"),
                "openweb_url": ow.get("url"), "openweb_domain": ow.get("domain"), "openweb_debug": ow,
                "grounding_url": g.get("url"), "grounding_domain": g.get("domain"), "grounding_identity_match": g.get("identity_match"), "grounding_error": g.get("error"), "grounding_summary": g.get("summary"),
                "final_domain": final_domain, "resolver_method": method, "domain_match": match,
            }
            rows.append(row)
            print(f"RESOLVE {name}: truth={truth_domain} open={ow.get('domain')} ground={g.get('domain')} final={final_domain} method={method} match={match}")
            time.sleep(0.1)

    truth = [r for r in rows if r.get("enterprise_domain")]
    open_resolved = [r for r in rows if r.get("openweb_domain")]
    open_matches = [r for r in open_resolved if r.get("enterprise_domain") == r.get("openweb_domain")]
    ground_resolved = [r for r in rows if r.get("grounding_domain")]
    ground_matches = [r for r in ground_resolved if r.get("enterprise_domain") == r.get("grounding_domain")]
    final_resolved = [r for r in rows if r.get("final_domain")]
    final_matches = [r for r in final_resolved if r.get("domain_match")]
    wrong = [r for r in final_resolved if r.get("enterprise_domain") and not r.get("domain_match")]

    def ratio(a: int, b: int): return round(a / b, 4) if b else None
    summary = {
        "experiment": "Text Search Pro candidate discovery + open-web resolver + Grounding Lite fallback vs Enterprise websiteUri reference",
        "branch_safety": "read-only; no D1 writes; no production cohort writes; no Crawl4AI",
        "google_requests": {"text_search_pro": len(MARKETS), "text_search_enterprise_reference": len(MARKETS), "maps_grounding_lite_fallback": grounding_calls},
        "candidate_discovery": {"candidates": len(rows), "all_market_place_id_parity": all(m["same_place_ids"] == m["pro_results"] == m["enterprise_results"] for m in markets)},
        "open_web_only": {"resolved": len(open_resolved), "exact_matches": len(open_matches), "precision": ratio(len(open_matches), len(open_resolved)), "recall_vs_truth": ratio(len(open_matches), len(truth))},
        "grounding_fallback": {"resolved": len(ground_resolved), "exact_matches": len(ground_matches), "precision": ratio(len(ground_matches), len(ground_resolved))},
        "combined": {"truth_websites": len(truth), "resolved": len(final_resolved), "exact_matches": len(final_matches), "wrong": len(wrong), "precision": ratio(len(final_matches), len(final_resolved)), "recall_vs_truth": ratio(len(final_matches), len(truth))},
        "markets": markets,
    }
    precision = summary["combined"]["precision"] or 0
    recall = summary["combined"]["recall_vs_truth"] or 0
    summary["recommendation"] = "strong_go" if precision >= .95 and recall >= .8 else ("hybrid" if precision >= .95 and recall > 0 else "no_go")

    (OUT / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    (OUT / "comparisons.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT / "market_meta.json").write_text(json.dumps(markets, indent=2), encoding="utf-8")
    write_csv(OUT / "comparisons.csv", rows)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
