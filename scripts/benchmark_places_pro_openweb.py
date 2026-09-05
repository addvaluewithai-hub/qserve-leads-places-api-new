#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

import requests
from bs4 import BeautifulSoup

SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"
OUT = Path("out/places-pro-openweb-benchmark")

# Deliberately small: this benchmark must not become a production discovery run.
MARKETS = [
    "Phoenix, AZ",
    "Tampa, FL",
    "Charlotte, NC",
    "Nashville, TN",
    "Denver, CO",
]
PAGE_SIZE = 10
MIN_RATING = 4.0

PRO_MASK = ",".join([
    "places.id",
    "places.displayName",
    "places.formattedAddress",
    "places.businessStatus",
])
ENTERPRISE_MASK = PRO_MASK + ",places.websiteUri,places.rating,places.userRatingCount"

BLOCKED_HOST_PARTS = {
    "google.com", "g.page", "facebook.com", "instagram.com", "linkedin.com", "x.com", "twitter.com",
    "yelp.com", "avvo.com", "findlaw.com", "justia.com", "lawyers.com", "lawinfo.com",
    "martindale.com", "superlawyers.com", "yellowpages.com", "mapquest.com", "bbb.org",
    "chamberofcommerce.com", "expertise.com", "thumbtack.com", "alignable.com",
}
STOPWORDS = {
    "law", "lawyer", "lawyers", "attorney", "attorneys", "firm", "group", "office", "offices",
    "the", "and", "of", "pc", "pllc", "llc", "pa", "ltd", "inc", "legal", "services",
}
UA = "Mozilla/5.0 (compatible; QServeBenchmark/1.0; +https://github.com/addvaluewithai-hub/qserve-leads-places-api-new)"
SESSION = requests.Session()
SESSION.headers.update({"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"})


def host(url: str | None) -> str | None:
    if not url:
        return None
    try:
        value = (urlparse(url).hostname or "").lower().strip(".")
        return value[4:] if value.startswith("www.") else value or None
    except Exception:
        return None


def canonical_domain(url: str | None) -> str | None:
    h = host(url)
    if not h:
        return None
    # Good enough for US law-firm sites and transparent for manual inspection.
    # Keep the full host except common www prefix so we never accidentally merge unrelated domains.
    return h


def blocked(domain: str | None) -> bool:
    if not domain:
        return True
    return any(domain == b or domain.endswith("." + b) for b in BLOCKED_HOST_PARTS)


def firm_tokens(name: str) -> list[str]:
    tokens = re.findall(r"[a-z0-9]+", (name or "").lower())
    return [t for t in tokens if len(t) >= 3 and t not in STOPWORDS]


def unwrap_ddg(url: str) -> str:
    if not url:
        return url
    parsed = urlparse(url)
    if "duckduckgo.com" in (parsed.hostname or ""):
        qs = parse_qs(parsed.query)
        if qs.get("uddg"):
            return unquote(qs["uddg"][0])
    if url.startswith("//"):
        return "https:" + url
    return url


def search_duckduckgo(query: str) -> list[dict]:
    response = SESSION.get("https://html.duckduckgo.com/html/", params={"q": query}, timeout=20)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    rows = []
    for result in soup.select(".result")[:8]:
        a = result.select_one("a.result__a")
        if not a:
            continue
        href = unwrap_ddg(a.get("href") or "")
        snippet_node = result.select_one(".result__snippet")
        rows.append({
            "provider": "duckduckgo",
            "url": href,
            "title": a.get_text(" ", strip=True),
            "snippet": snippet_node.get_text(" ", strip=True) if snippet_node else "",
        })
    return rows


def search_bing(query: str) -> list[dict]:
    response = SESSION.get("https://www.bing.com/search", params={"q": query, "count": 8}, timeout=20)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    rows = []
    for result in soup.select("li.b_algo")[:8]:
        a = result.select_one("h2 a")
        if not a:
            continue
        snippet_node = result.select_one(".b_caption p")
        rows.append({
            "provider": "bing",
            "url": a.get("href") or "",
            "title": a.get_text(" ", strip=True),
            "snippet": snippet_node.get_text(" ", strip=True) if snippet_node else "",
        })
    return rows


def web_search(query: str) -> tuple[list[dict], str | None]:
    errors = []
    for func in (search_duckduckgo, search_bing):
        try:
            rows = func(query)
            if rows:
                return rows, None
            errors.append(f"{func.__name__}: no results")
        except Exception as exc:
            errors.append(f"{func.__name__}: {type(exc).__name__}: {exc}")
    return [], " | ".join(errors)


def score_candidate(name: str, row: dict) -> float:
    domain = canonical_domain(row.get("url"))
    if blocked(domain):
        return -100.0
    tokens = firm_tokens(name)
    haystack = " ".join([domain or "", row.get("title") or "", row.get("snippet") or ""]).lower()
    domain_text = (domain or "").replace("-", " ").replace(".", " ")
    score = 0.0
    for token in tokens:
        if token in domain_text:
            score += 3.0
        elif token in haystack:
            score += 1.0
    if "official" in haystack:
        score += 0.5
    if "law" in domain_text or "legal" in domain_text:
        score += 0.5
    return score


def verify_url(url: str) -> dict:
    try:
        response = SESSION.get(url, timeout=15, allow_redirects=True, stream=True)
        final_url = response.url
        status = response.status_code
        response.close()
        domain = canonical_domain(final_url)
        return {
            "ok": 200 <= status < 500 and not blocked(domain),
            "status": status,
            "final_url": final_url,
            "domain": domain,
            "error": None,
        }
    except Exception as exc:
        return {"ok": False, "status": None, "final_url": None, "domain": None, "error": f"{type(exc).__name__}: {exc}"}


def resolve_official_site(name: str, address: str) -> dict:
    locality = ", ".join([p.strip() for p in (address or "").split(",")[-3:-1]])
    query = f'"{name}" {locality} official website'
    results, search_error = web_search(query)
    ranked = sorted(
        ({**r, "score": score_candidate(name, r), "domain": canonical_domain(r.get("url"))} for r in results),
        key=lambda r: r["score"],
        reverse=True,
    )
    inspected = []
    for candidate in ranked[:5]:
        if candidate["score"] < 2.0 or blocked(candidate.get("domain")):
            inspected.append({**candidate, "verification": None})
            continue
        verification = verify_url(candidate["url"])
        inspected.append({**candidate, "verification": verification})
        if verification["ok"]:
            return {
                "resolved_url": verification["final_url"],
                "resolved_domain": verification["domain"],
                "search_query": query,
                "search_error": search_error,
                "search_provider": candidate["provider"],
                "resolver_score": candidate["score"],
                "candidates": inspected,
            }
    return {
        "resolved_url": None,
        "resolved_domain": None,
        "search_query": query,
        "search_error": search_error,
        "search_provider": None,
        "resolver_score": None,
        "candidates": inspected,
    }


def places_search(key: str, market: str, field_mask: str) -> tuple[int, dict]:
    body = {
        "textQuery": f"lawyer in {market}",
        "includedType": "lawyer",
        "strictTypeFiltering": True,
        "minRating": MIN_RATING,
        "pageSize": PAGE_SIZE,
        "regionCode": "US",
        "languageCode": "en",
    }
    headers = {
        "X-Goog-Api-Key": key,
        "X-Goog-FieldMask": field_mask,
        "Content-Type": "application/json",
    }
    response = SESSION.post(SEARCH_URL, headers=headers, json=body, timeout=45)
    try:
        payload = response.json()
    except Exception:
        payload = {"raw": response.text[:2000]}
    return response.status_code, payload


def place_row(place: dict, market: str) -> dict:
    display = place.get("displayName") or {}
    return {
        "place_id": place.get("id"),
        "name": display.get("text") or "",
        "address": place.get("formattedAddress") or "",
        "business_status": place.get("businessStatus"),
        "market": market,
        "enterprise_website": place.get("websiteUri"),
        "enterprise_domain": canonical_domain(place.get("websiteUri")),
        "enterprise_rating": place.get("rating"),
        "enterprise_review_count": place.get("userRatingCount"),
    }


def write_csv(path: Path, rows: list[dict]) -> None:
    fields = [
        "place_id", "name", "address", "market", "business_status",
        "enterprise_website", "enterprise_domain", "enterprise_rating", "enterprise_review_count",
        "resolved_url", "resolved_domain", "domain_match", "search_provider", "resolver_score", "search_error",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    key = os.getenv("GOOGLE_API_KEY")
    if not key:
        raise SystemExit("GOOGLE_API_KEY is missing")

    OUT.mkdir(parents=True, exist_ok=True)
    market_meta = []
    comparisons = []

    for market in MARKETS:
        pro_status, pro_payload = places_search(key, market, PRO_MASK)
        ent_status, ent_payload = places_search(key, market, ENTERPRISE_MASK)
        pro_places = pro_payload.get("places") or [] if pro_status == 200 else []
        ent_places = ent_payload.get("places") or [] if ent_status == 200 else []
        enterprise_by_id = {p.get("id"): p for p in ent_places if p.get("id")}

        meta = {
            "market": market,
            "pro_http_status": pro_status,
            "enterprise_http_status": ent_status,
            "pro_results": len(pro_places),
            "enterprise_results": len(ent_places),
            "same_place_ids": len({p.get("id") for p in pro_places} & set(enterprise_by_id)),
        }
        market_meta.append(meta)
        print(json.dumps(meta))

        for pro_place in pro_places:
            pid = pro_place.get("id")
            if not pid:
                continue
            ent = enterprise_by_id.get(pid) or {}
            row = place_row({**pro_place, **ent}, market)
            if row["business_status"] and row["business_status"] != "OPERATIONAL":
                continue
            resolved = resolve_official_site(row["name"], row["address"])
            row.update({
                "resolved_url": resolved["resolved_url"],
                "resolved_domain": resolved["resolved_domain"],
                "search_provider": resolved["search_provider"],
                "resolver_score": resolved["resolver_score"],
                "search_error": resolved["search_error"],
                "resolver_debug": resolved,
            })
            row["domain_match"] = bool(
                row.get("enterprise_domain")
                and row.get("resolved_domain")
                and row["enterprise_domain"] == row["resolved_domain"]
            )
            comparisons.append(row)
            print(
                f"RESOLVE {market} | {row['name']} | "
                f"truth={row.get('enterprise_domain')} resolved={row.get('resolved_domain')} match={row['domain_match']}"
            )
            time.sleep(0.2)

    truth_rows = [r for r in comparisons if r.get("enterprise_domain")]
    resolved_rows = [r for r in comparisons if r.get("resolved_domain")]
    matched_rows = [r for r in comparisons if r.get("domain_match")]
    wrong_rows = [r for r in comparisons if r.get("enterprise_domain") and r.get("resolved_domain") and not r.get("domain_match")]
    unresolved_truth = [r for r in comparisons if r.get("enterprise_domain") and not r.get("resolved_domain")]

    summary = {
        "experiment": "Places Text Search Pro + open-web official-site resolver vs Enterprise websiteUri reference",
        "branch_safety": "read-only benchmark: no D1 writes, no production cohort writes, no Crawl4AI",
        "markets": MARKETS,
        "page_size": PAGE_SIZE,
        "min_rating_request_filter": MIN_RATING,
        "google_requests": {
            "text_search_pro": len(MARKETS),
            "text_search_enterprise_reference": len(MARKETS),
            "place_details": 0,
            "nearby_search": 0,
        },
        "results": {
            "pro_candidates_compared": len(comparisons),
            "enterprise_reference_websites_available": len(truth_rows),
            "open_web_domains_resolved": len(resolved_rows),
            "exact_domain_matches": len(matched_rows),
            "resolved_but_wrong_vs_enterprise": len(wrong_rows),
            "enterprise_had_website_but_resolver_unresolved": len(unresolved_truth),
            "resolver_recall_against_enterprise_website": round(len(matched_rows) / len(truth_rows), 4) if truth_rows else None,
            "resolver_precision_when_truth_available_and_resolved": round(len(matched_rows) / (len(matched_rows) + len(wrong_rows)), 4) if (matched_rows or wrong_rows) else None,
        },
        "decision_rule": {
            "strong_go": "precision >= 0.95 and recall >= 0.80",
            "hybrid": "precision >= 0.95 and recall < 0.80; use Enterprise only as fallback for unresolved candidates",
            "no_go": "precision < 0.95; resolver needs improvement before mass discovery",
        },
        "important_note": "Enterprise calls in this benchmark are reference-only so we can measure the resolver. Production design should avoid them except where explicitly justified.",
    }

    if truth_rows:
        precision = summary["results"]["resolver_precision_when_truth_available_and_resolved"] or 0
        recall = summary["results"]["resolver_recall_against_enterprise_website"] or 0
        if precision >= 0.95 and recall >= 0.80:
            summary["recommendation"] = "strong_go"
        elif precision >= 0.95:
            summary["recommendation"] = "hybrid"
        else:
            summary["recommendation"] = "no_go"
    else:
        summary["recommendation"] = "inconclusive"

    (OUT / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT / "market_meta.json").write_text(json.dumps(market_meta, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT / "comparisons.json").write_text(json.dumps(comparisons, ensure_ascii=False, indent=2), encoding="utf-8")
    write_csv(OUT / "comparisons.csv", comparisons)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
