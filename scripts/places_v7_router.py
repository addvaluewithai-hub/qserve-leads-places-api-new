#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.parse import urlparse

import requests

SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"
GROUNDING_URL = "https://mapstools.googleapis.com/mcp"

SKU_TEXT_PRO = "places_text_search_pro"
SKU_GROUNDING_LITE = "maps_grounding_lite"
SKU_TEXT_ENTERPRISE = "places_text_search_enterprise"

PRO_FIELD_MASK = ",".join([
    "places.id",
    "places.displayName",
    "places.formattedAddress",
    "places.businessStatus",
    "nextPageToken",
])
ENTERPRISE_FIELD_MASK = PRO_FIELD_MASK + ",places.websiteUri"

BLOCKED_HOSTS = {
    "google.com", "facebook.com", "instagram.com", "linkedin.com",
    "x.com", "twitter.com", "yelp.com", "avvo.com", "findlaw.com",
    "justia.com", "lawyers.com", "lawinfo.com", "martindale.com",
    "superlawyers.com", "yellowpages.com", "mapquest.com", "bbb.org",
}
URL_RE = re.compile(r"https?://[^\s<>()\[\]{}]+", re.I)


def month_key() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m")


def domain(url: str | None) -> str | None:
    if not url:
        return None
    try:
        host = (urlparse(url).hostname or "").lower().strip(".")
        if host.startswith("www."):
            host = host[4:]
        return host or None
    except Exception:
        return None


def blocked(host: str | None) -> bool:
    if not host:
        return True
    return any(host == b or host.endswith("." + b) for b in BLOCKED_HOSTS)


def external_urls(text: str) -> list[str]:
    out, seen = [], set()
    for raw in URL_RE.findall(text or ""):
        url = raw.rstrip(".,;:!?\"'")
        host = domain(url)
        if blocked(host) or (host and host.endswith("googleusercontent.com")):
            continue
        if url not in seen:
            seen.add(url)
            out.append(url)
    return out


def display_name(place: dict) -> str:
    return ((place.get("displayName") or {}).get("text") or "").strip()


@dataclass
class Budget:
    sku: str
    cap: int
    used: int = 0

    @property
    def remaining(self) -> int:
        return max(0, self.cap - self.used)

    def can_spend(self, n: int = 1) -> bool:
        return self.used + n <= self.cap

    def spend(self, n: int = 1) -> None:
        if not self.can_spend(n):
            raise RuntimeError(f"zero-paid guard blocked {self.sku}: {self.used}+{n}>{self.cap}")
        self.used += n


class UsageLedger:
    """D1-compatible ledger wrapper; query=None gives an in-memory dry-run ledger."""

    def __init__(self, query=None, campaign_id: str = "lawyers-us", run_id: str | None = None):
        self.query = query
        self.campaign_id = campaign_id
        self.run_id = run_id or f"v7-{uuid.uuid4()}"
        self.memory: dict[str, int] = {}

    def used_this_month(self, sku: str) -> int:
        if self.query is None:
            return int(self.memory.get(sku, 0))
        from d1_helpers import result_rows
        rows = result_rows(self.query(
            """
            SELECT COALESCE(SUM(request_count),0) AS n
            FROM api_usage_ledger
            WHERE campaign_id=? AND sku=? AND usage_month=?
            """,
            [self.campaign_id, sku, month_key()],
        ))
        return int((rows[0] if rows else {}).get("n") or 0)

    def record(self, sku: str, context: str) -> None:
        if self.query is None:
            self.memory[sku] = self.memory.get(sku, 0) + 1
            return
        self.query(
            """
            INSERT INTO api_usage_ledger
              (id,campaign_id,run_id,sku,usage_month,request_count,context,created_at)
            VALUES (?,?,?,?,?,1,?,CURRENT_TIMESTAMP)
            """,
            [str(uuid.uuid4()), self.campaign_id, self.run_id, sku, month_key(), context[:1200]],
        )


class PlacesV7Router:
    """
    Zero-paid routing:
      1) Text Search Pro + minRating=4.0.
      2) Resolve official site with Maps Grounding Lite, requiring same Place ID.
      3) When Grounding cannot be spent (or a page has unresolved candidates),
         re-issue that same page as Text Search Enterprise and use websiteUri.
      4) Never cross configured internal free-tier guards.
    """

    def __init__(
        self,
        api_key: str,
        *,
        ledger: UsageLedger,
        pro_cap: int = 4800,
        grounding_cap: int = 9500,
        enterprise_cap: int = 900,
        timeout: int = 60,
    ):
        self.api_key = api_key
        self.ledger = ledger
        self.timeout = timeout
        self.session = requests.Session()

        self.pro = Budget(SKU_TEXT_PRO, pro_cap, ledger.used_this_month(SKU_TEXT_PRO))
        self.ground = Budget(SKU_GROUNDING_LITE, grounding_cap, ledger.used_this_month(SKU_GROUNDING_LITE))
        self.enterprise = Budget(
            SKU_TEXT_ENTERPRISE, enterprise_cap, ledger.used_this_month(SKU_TEXT_ENTERPRISE)
        )

    def budget_snapshot(self) -> dict:
        def snap(b: Budget):
            return {"sku": b.sku, "cap": b.cap, "used": b.used, "remaining": b.remaining}
        return {"pro": snap(self.pro), "grounding": snap(self.ground), "enterprise": snap(self.enterprise)}

    def _post_places(self, body: dict, field_mask: str, budget: Budget, context: str) -> dict:
        if not budget.can_spend():
            raise RuntimeError(f"{budget.sku} free-tier guard exhausted")
        headers = {
            "X-Goog-Api-Key": self.api_key,
            "Content-Type": "application/json",
            "X-Goog-FieldMask": field_mask,
        }
        budget.spend()
        self.ledger.record(budget.sku, context)
        response = self.session.post(SEARCH_URL, headers=headers, json=body, timeout=self.timeout)
        if response.status_code != 200:
            raise RuntimeError(f"{budget.sku} HTTP {response.status_code}: {response.text[:800]}")
        return response.json()

    def _ground_one(self, place: dict) -> dict:
        if not self.ground.can_spend():
            return {"ok": False, "reason": "grounding_budget_exhausted"}

        place_id = place.get("id")
        name = display_name(place)
        address = place.get("formattedAddress") or ""
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
        headers = {"X-Goog-Api-Key": self.api_key, "Content-Type": "application/json"}

        self.ground.spend()
        self.ledger.record(SKU_GROUNDING_LITE, f"place_id={place_id};resolve=official_website")
        try:
            response = self.session.post(GROUNDING_URL, headers=headers, json=body, timeout=self.timeout)
            if response.status_code != 200:
                return {"ok": False, "reason": f"HTTP {response.status_code}"}
            payload = response.json()
            structured = ((payload.get("result") or {}).get("structuredContent") or {})
            summary = structured.get("summary") or ""
            places = structured.get("places") or []
            ids = [p.get("id") for p in places if p.get("id")]
            if place_id not in ids:
                return {"ok": False, "reason": "place_id_identity_mismatch", "returned_place_ids": ids}
            urls = external_urls(summary)
            if not urls:
                return {"ok": False, "reason": "no_external_website", "returned_place_ids": ids}
            return {
                "ok": True,
                "method": "maps_grounding_lite",
                "url": urls[0],
                "domain": domain(urls[0]),
                "returned_place_ids": ids,
            }
        except Exception as exc:
            return {"ok": False, "reason": f"{type(exc).__name__}: {exc}"}

    @staticmethod
    def search_body(
        *,
        text_query: str,
        included_type: str = "lawyer",
        min_rating: float = 4.0,
        page_size: int = 20,
        page_token: str | None = None,
        location_restriction: dict | None = None,
    ) -> dict:
        body = {
            "textQuery": text_query,
            "includedType": included_type,
            "strictTypeFiltering": True,
            "minRating": float(min_rating),
            "pageSize": int(page_size),
            "regionCode": "US",
            "languageCode": "en",
        }
        if page_token:
            body["pageToken"] = page_token
        if location_restriction:
            body["locationRestriction"] = location_restriction
        return body

    def search_and_resolve_page(self, body: dict, context: str) -> dict:
        if not self.ground.can_spend():
            enterprise_payload = self._post_places(
                body, ENTERPRISE_FIELD_MASK, self.enterprise, context + ";mode=enterprise_direct"
            )
            rows = []
            for place in enterprise_payload.get("places") or []:
                if place.get("businessStatus") != "OPERATIONAL":
                    continue
                url = place.get("websiteUri")
                host = domain(url)
                if not place.get("id") or not url or blocked(host):
                    continue
                rows.append({
                    "place_id": place["id"],
                    "name": display_name(place),
                    "address": place.get("formattedAddress") or "",
                    "business_status": place.get("businessStatus"),
                    "website": url,
                    "website_domain": host,
                    "resolution_method": "text_search_enterprise_fallback",
                })
            return {
                "search_mode": "enterprise_direct",
                "places": rows,
                "next_page_token": enterprise_payload.get("nextPageToken"),
            }

        pro_payload = self._post_places(body, PRO_FIELD_MASK, self.pro, context + ";mode=pro")
        pro_places = [
            p for p in (pro_payload.get("places") or [])
            if p.get("id") and p.get("businessStatus") == "OPERATIONAL"
        ]

        rows = []
        unresolved_ids: set[str] = set()
        for place in pro_places:
            grounded = self._ground_one(place)
            if grounded.get("ok") and grounded.get("domain") and not blocked(grounded.get("domain")):
                rows.append({
                    "place_id": place["id"],
                    "name": display_name(place),
                    "address": place.get("formattedAddress") or "",
                    "business_status": place.get("businessStatus"),
                    "website": grounded["url"],
                    "website_domain": grounded["domain"],
                    "resolution_method": "maps_grounding_lite",
                })
            else:
                unresolved_ids.add(str(place["id"]))

        if unresolved_ids:
            if not self.enterprise.can_spend():
                return {
                    "search_mode": "pro_grounding_partial",
                    "places": rows,
                    "unresolved_place_ids": sorted(unresolved_ids),
                    "next_page_token": pro_payload.get("nextPageToken"),
                    "zero_paid_stop": "enterprise_budget_exhausted",
                }
            enterprise_payload = self._post_places(
                body, ENTERPRISE_FIELD_MASK, self.enterprise, context + ";mode=enterprise_page_fallback"
            )
            by_id = {p.get("id"): p for p in (enterprise_payload.get("places") or []) if p.get("id")}
            still_unresolved = []
            for pid in sorted(unresolved_ids):
                place = by_id.get(pid) or {}
                url = place.get("websiteUri")
                host = domain(url)
                if not url or blocked(host):
                    still_unresolved.append(pid)
                    continue
                rows.append({
                    "place_id": pid,
                    "name": display_name(place),
                    "address": place.get("formattedAddress") or "",
                    "business_status": place.get("businessStatus"),
                    "website": url,
                    "website_domain": host,
                    "resolution_method": "text_search_enterprise_page_fallback",
                })
            unresolved_ids = set(still_unresolved)

        return {
            "search_mode": "pro_grounding_then_enterprise_if_needed",
            "places": rows,
            "unresolved_place_ids": sorted(unresolved_ids),
            "next_page_token": pro_payload.get("nextPageToken"),
        }
