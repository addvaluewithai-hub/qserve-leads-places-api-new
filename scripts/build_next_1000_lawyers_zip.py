#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import csv
import json
import math
import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import requests
import tldextract
from crawl4ai import AsyncWebCrawler

from crawl_working_set_homepages import fetch_one
from d1_helpers import ROOT, apply_schema, make_query_client, result_rows
from zip_manager import load_campaign, load_plan, next_zips, recover_stale_in_progress, sync_zip_plan

SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"
SKU = "places_text_search_enterprise"
TLD_EXTRACT = tldextract.TLDExtract(suffix_list_urls=None)


def host_domain(url: str | None) -> str | None:
    if not url:
        return None
    try:
        value = url if "://" in url else f"https://{url}"
        host = (urlparse(value).hostname or "").lower().strip(".")
        return host[4:] if host.startswith("www.") else (host or None)
    except Exception:
        return None


def business_domain(url_or_host: str | None) -> str | None:
    host = host_domain(url_or_host)
    if not host:
        return None
    parts = TLD_EXTRACT(host)
    if parts.domain and parts.suffix:
        return f"{parts.domain}.{parts.suffix}".lower()
    return host.lower()


def postal_code_from_components(components: list[dict] | None) -> str | None:
    for component in components or []:
        if "postal_code" not in (component.get("types") or []):
            continue
        value = component.get("longText") or component.get("shortText")
        if value:
            digits = "".join(ch for ch in str(value) if ch.isdigit())
            return digits[:5] if len(digits) >= 5 else None
    return None


def restriction_rectangle(latitude: float, longitude: float, half_span_km: float) -> dict:
    lat_delta = half_span_km / 111.0
    cos_lat = max(0.2, math.cos(math.radians(latitude)))
    lon_delta = half_span_km / (111.0 * cos_lat)
    return {
        "low": {"latitude": max(-90.0, latitude - lat_delta), "longitude": max(-180.0, longitude - lon_delta)},
        "high": {"latitude": min(90.0, latitude + lat_delta), "longitude": min(180.0, longitude + lon_delta)},
    }


def month_key() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m")


def usage_this_month(query, campaign_id: str) -> int:
    rows = result_rows(query(
        """
        SELECT COALESCE(SUM(request_count),0) AS n
        FROM api_usage_ledger
        WHERE campaign_id=? AND sku=? AND usage_month=?
        """,
        [campaign_id, SKU, month_key()],
    ))
    return int((rows[0] if rows else {}).get("n") or 0)


def record_usage(query, campaign_id: str, run_id: str, zip_code: str, page_number: int) -> None:
    query(
        """
        INSERT INTO api_usage_ledger (id,campaign_id,run_id,sku,usage_month,request_count,context,created_at)
        VALUES (?,?,?,?,?,1,?,CURRENT_TIMESTAMP)
        """,
        [str(uuid.uuid4()), campaign_id, run_id, SKU, month_key(), f"zip={zip_code};page={page_number}"],
    )


def global_seen(query) -> tuple[set[str], set[str], set[str]]:
    ids = {str(r["id"]) for r in result_rows(query("SELECT id FROM leads")) if r.get("id")}
    domains: set[str] = set()
    for r in result_rows(query("SELECT website_domain FROM lead_domains")):
        domain = business_domain(r.get("website_domain"))
        if domain:
            domains.add(domain)
    suppressed: set[str] = set()
    for r in result_rows(query(
        """
        SELECT website_domain FROM outreach_suppression
        WHERE suppressed=1 AND (reengage_after IS NULL OR reengage_after > CURRENT_TIMESTAMP)
        """
    )):
        domain = business_domain(r.get("website_domain"))
        if domain:
            suppressed.add(domain)
    return ids, domains, suppressed


def search_zip_page(*, key: str, campaign: dict, zip_row: dict, page_number: int, page_token: str | None) -> tuple[int, dict | None, str | None]:
    google = campaign.get("google") or {}
    zip_code = str(zip_row["zip_code"])
    text_query = str(google.get("query_template") or "lawyer in {zip_code}").format(zip_code=zip_code)
    half_span_km = float(google.get("zip_location_restriction_half_span_km") or 25.0)
    body = {
        "textQuery": text_query,
        "includedType": google.get("included_type") or "lawyer",
        "strictTypeFiltering": bool(google.get("strict_type_filtering", True)),
        "minRating": float(google.get("min_rating_search_filter") or 4.0),
        "pageSize": int(google.get("page_size") or 20),
        "regionCode": google.get("region_code") or "US",
        "languageCode": google.get("language_code") or "en",
        "locationRestriction": {"rectangle": restriction_rectangle(float(zip_row["latitude"]), float(zip_row["longitude"]), half_span_km)},
    }
    if page_token:
        body["pageToken"] = page_token

    headers = {
        "X-Goog-Api-Key": key,
        "Content-Type": "application/json",
        "X-Goog-FieldMask": ",".join(google.get("field_mask") or []),
    }

    last_error = None
    for attempt in range(3):
        try:
            response = requests.post(SEARCH_URL, headers=headers, json=body, timeout=60)
            if response.status_code == 200:
                return 200, response.json(), None
            last_error = f"HTTP {response.status_code}: {response.text[:600]}"
            if response.status_code not in {400, 429, 500, 502, 503, 504}:
                break
        except Exception as exc:
            last_error = f"{type(exc).__name__}: {exc}"
        time.sleep(2.0 * (attempt + 1))
    return 0, None, last_error


def quality_candidates(payload: dict, campaign: dict, target_zip: str) -> tuple[list[dict], dict]:
    quality = campaign.get("quality") or {}
    allowed = set(quality.get("allowed_business_statuses") or ["OPERATIONAL"])
    min_rating = float(quality.get("min_rating") or 4.0)
    min_reviews = int(quality.get("min_reviews") or 20)

    raw_places = payload.get("places") or []
    exact_zip = []
    passed = []

    for place in raw_places:
        postal = postal_code_from_components(place.get("addressComponents"))
        if postal != target_zip:
            continue
        exact_zip.append(place)
        place_id = place.get("id")
        website_seed = place.get("websiteUri")
        rating = place.get("rating")
        review_count = place.get("userRatingCount")
        status = place.get("businessStatus")
        if not place_id or not website_seed:
            continue
        if status not in allowed:
            continue
        if rating is None or float(rating) < min_rating:
            continue
        if review_count is None or int(review_count) < min_reviews:
            continue
        passed.append({
            "place_id": str(place_id),
            "website_seed": str(website_seed),
            "seed_business_domain": business_domain(str(website_seed)),
        })

    return passed, {"raw_places": len(raw_places), "exact_zip_places": len(exact_zip), "quality_passes": len(passed)}


async def crawl_seed_batch(candidates: list[dict], zip_row: dict, workers: int) -> list[dict]:
    if not candidates:
        return []
    queue: asyncio.Queue[tuple[int, dict]] = asyncio.Queue()
    for idx, candidate in enumerate(candidates):
        queue.put_nowait((idx, candidate))
    results: list[dict] = []

    async def worker(worker_id: int) -> None:
        async with AsyncWebCrawler() as crawler:
            while True:
                try:
                    source_index, candidate = queue.get_nowait()
                except asyncio.QueueEmpty:
                    return
                try:
                    transient_lead = {
                        "place_id": candidate["place_id"],
                        "website": candidate["website_seed"],
                        "website_domain": candidate.get("seed_business_domain"),
                        "source_market": zip_row["zip_code"],
                    }
                    summary, links = await fetch_one(crawler, transient_lead, source_index)
                    final_url = summary.get("final_url") or summary.get("homepage")
                    results.append({
                        "place_id": candidate["place_id"],
                        "crawl_status": summary.get("crawl_status"),
                        "homepage_status_code": summary.get("homepage_status_code"),
                        "homepage_title": summary.get("homepage_title"),
                        "final_url": final_url,
                        "final_business_domain": business_domain(final_url),
                        "attempts": summary.get("attempts"),
                        "error": summary.get("error"),
                        "links": links,
                    })
                finally:
                    queue.task_done()

    worker_count = min(max(1, int(workers)), len(candidates))
    await asyncio.gather(*(worker(i + 1) for i in range(worker_count)))
    return results


def crawl_candidates(candidates: list[dict], zip_row: dict, workers: int) -> list[dict]:
    return asyncio.run(crawl_seed_batch(candidates, zip_row, workers))


def mark_zip_in_progress(query, campaign_id: str, zip_code: str, run_id: str) -> None:
    now = datetime.now(timezone.utc).isoformat()
    query("UPDATE zip_coverage SET status='in_progress', last_run_id=?, last_searched_at=?, updated_at=CURRENT_TIMESTAMP WHERE campaign_id=? AND zip_code=?", [run_id, now, campaign_id, zip_code])


def finish_zip(query, *, campaign_id: str, run_id: str, zip_row: dict, status: str, metrics: dict, note: str = "") -> None:
    now = datetime.now(timezone.utc).isoformat()
    query(
        """
        UPDATE zip_coverage
        SET status=?, search_count=search_count+1, page_count=page_count+?, raw_places=raw_places+?,
            exact_zip_places=exact_zip_places+?, quality_passes=quality_passes+?, net_new_domains=net_new_domains+?,
            duplicate_place_ids=duplicate_place_ids+?, duplicate_domains=duplicate_domains+?,
            last_searched_at=?, last_run_id=?, notes=?, updated_at=CURRENT_TIMESTAMP
        WHERE campaign_id=? AND zip_code=?
        """,
        [status, int(metrics.get("page_count") or 0), int(metrics.get("raw_places") or 0), int(metrics.get("exact_zip_places") or 0), int(metrics.get("quality_passes") or 0), int(metrics.get("net_new_domains") or 0), int(metrics.get("duplicate_place_ids") or 0), int(metrics.get("duplicate_domains") or 0), now, run_id, note[:1200], campaign_id, zip_row["zip_code"]],
    )
    query(
        """
        INSERT INTO zip_run_history (
          id,campaign_id,run_id,zip_code,city,state_code,searched_at,status_after,
          page_count,raw_places,exact_zip_places,quality_passes,net_new_domains,
          duplicate_place_ids,duplicate_domains,note
        ) VALUES (?,?,?,?,?,?,CURRENT_TIMESTAMP,?,?,?,?,?,?,?,?,?)
        """,
        [str(uuid.uuid4()), campaign_id, run_id, zip_row["zip_code"], zip_row.get("city"), zip_row.get("state_code"), status, int(metrics.get("page_count") or 0), int(metrics.get("raw_places") or 0), int(metrics.get("exact_zip_places") or 0), int(metrics.get("quality_passes") or 0), int(metrics.get("net_new_domains") or 0), int(metrics.get("duplicate_place_ids") or 0), int(metrics.get("duplicate_domains") or 0), note[:1200]],
    )


def persist_open_web_lead(query, *, campaign: dict, run_id: str, zip_row: dict, crawled: dict) -> dict:
    place_id = crawled["place_id"]
    final_url = crawled["final_url"]
    domain = crawled["final_business_domain"]
    title = (crawled.get("homepage_title") or domain or "Law firm").strip()
    batch = f"{campaign['id']}:{run_id}"
    now = datetime.now(timezone.utc).isoformat()

    query(
        """
        INSERT INTO leads (
          id,name,business_status,website,source_label,source_query,source_type,source_area,
          status,notes,first_source_batch,latest_source_batch
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(id) DO UPDATE SET
          name=excluded.name, website=excluded.website, source_label=excluded.source_label,
          source_query=excluded.source_query, source_type=excluded.source_type, source_area=excluded.source_area,
          status=excluded.status, notes=excluded.notes, latest_source_batch=excluded.latest_source_batch,
          last_seen_at=CURRENT_TIMESTAMP
        """,
        [place_id, title, "OPERATIONAL", final_url, campaign.get("name"), "lawyer", campaign.get("vertical"), zip_row["zip_code"], "Ready for Validation", "Passed transient Google Places screening (rating >= 4.0 and reviews >= 20); exact Google values and websiteUri were not persisted. Website/domain were re-observed from the public site by Crawl4AI.", batch, batch],
    )
    query(
        """
        INSERT INTO lead_domains (lead_id,website_domain,verified,source,updated_at)
        VALUES (?,?,1,'crawl4ai_open_web',CURRENT_TIMESTAMP)
        ON CONFLICT(lead_id) DO UPDATE SET website_domain=excluded.website_domain, verified=1, source=excluded.source, updated_at=CURRENT_TIMESTAMP
        """,
        [place_id, domain],
    )
    query(
        """
        INSERT INTO campaign_leads (
          campaign_id,lead_id,qualified,quality_score,qualification_reason,source_area,source_query,source_term,
          status,first_seen_at,last_seen_at,last_run_id
        ) VALUES (?,?,?,?,?,?,?,?,?,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP,?)
        ON CONFLICT(campaign_id,lead_id) DO UPDATE SET qualified=0, qualification_reason=excluded.qualification_reason,
          source_area=excluded.source_area, source_query=excluded.source_query, source_term=excluded.source_term,
          status=excluded.status, last_seen_at=CURRENT_TIMESTAMP, last_run_id=excluded.last_run_id
        """,
        [campaign["id"], place_id, 0, 0, "working_set_ready_for_validation", zip_row["zip_code"], "lawyer", f"zip:{zip_row['zip_code']}", "Ready for Validation", run_id],
    )
    query(
        """
        INSERT INTO lead_discovery_screening (campaign_id,lead_id,provider,source_zip,quality_gate_passed,screened_at,notes)
        VALUES (?,?,?,?,1,?,?)
        ON CONFLICT(campaign_id,lead_id) DO UPDATE SET provider=excluded.provider, source_zip=excluded.source_zip,
          quality_gate_passed=1, screened_at=excluded.screened_at, notes=excluded.notes
        """,
        [campaign["id"], place_id, "google_places_text_search_enterprise_transient", zip_row["zip_code"], now, "Google non-ID fields used transiently for screening and crawler seeding; only Place ID persisted from Google response."],
    )
    for link in crawled.get("links") or []:
        query(
            """
            INSERT INTO homepage_link_evidence (campaign_id,lead_id,homepage,final_url,url,anchor_text,crawled_at)
            VALUES (?,?,?,?,?,?,?)
            ON CONFLICT(campaign_id,lead_id,url) DO UPDATE SET homepage=excluded.homepage, final_url=excluded.final_url,
              anchor_text=excluded.anchor_text, crawled_at=excluded.crawled_at
            """,
            [campaign["id"], place_id, final_url, final_url, link.get("url"), link.get("anchor_text") or "", now],
        )

    return {
        "place_id": place_id,
        "website": final_url,
        "website_domain": domain,
        "website_title": title,
        "source_zip": zip_row["zip_code"],
        "source_city": zip_row.get("city"),
        "source_state": zip_row.get("state_code"),
        "homepage_status_code": crawled.get("homepage_status_code"),
        "internal_links_found": len(crawled.get("links") or []),
        "campaign_status": "Ready for Validation",
        "qualified": False,
    }


def write_outputs(out_dir: Path, rows: list[dict], summary: dict, zip_log: list[dict], links: list[dict]) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "leads.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    (out_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    (out_dir / "zip_log.json").write_text(json.dumps(zip_log, ensure_ascii=False, indent=2), encoding="utf-8")
    (out_dir / "homepage_links.json").write_text(json.dumps(links, ensure_ascii=False, indent=2), encoding="utf-8")
    lead_fields = ["place_id","website","website_domain","website_title","source_zip","source_city","source_state","homepage_status_code","internal_links_found","campaign_status","qualified"]
    with (out_dir / "leads.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=lead_fields, extrasaction="ignore"); writer.writeheader(); writer.writerows(rows)
    link_fields = ["place_id","source_zip","homepage","url","anchor_text"]
    with (out_dir / "homepage_links.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=link_fields, extrasaction="ignore"); writer.writeheader(); writer.writerows(links)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the next net-new lawyer working set using ZIP coverage + transient Text Search Enterprise + immediate Crawl4AI")
    parser.add_argument("--campaign", default="lawyers-us")
    parser.add_argument("--target", type=int, default=None)
    parser.add_argument("--max-zips", type=int, default=5000)
    parser.add_argument("--max-search-requests", type=int, default=None)
    parser.add_argument("--out-dir", default=None)
    args = parser.parse_args()

    key = os.getenv("GOOGLE_API_KEY")
    if not key:
        raise SystemExit("GOOGLE_API_KEY is required")

    campaign = load_campaign(args.campaign)
    plan = load_plan(campaign)
    target = int(args.target or (campaign.get("working_set") or {}).get("target_net_new_domains_per_run") or 1000)
    out_dir = Path(args.out_dir) if args.out_dir else ROOT / "out" / f"{args.campaign}-next-{target}-zip"

    query = make_query_client()
    apply_schema(query)
    recover_stale_in_progress(query, campaign["id"])
    sync_zip_plan(query, campaign, plan)

    existing_ids, existing_domains, suppressed_domains = global_seen(query)
    historical_expected = int((campaign.get("working_set") or {}).get("historical_seed_expected_domains") or 0)
    if historical_expected and len(existing_ids) < historical_expected:
        raise SystemExit(f"Only {len(existing_ids)} canonical businesses exist in D1 but this campaign expects at least {historical_expected} historical seed businesses. Run the bootstrap workflow before next-1000 discovery.")

    google = campaign.get("google") or {}
    monthly_budget = int(google.get("monthly_enterprise_request_budget") or 900)
    already_used = usage_this_month(query, campaign["id"])
    requested_cap = int(args.max_search_requests) if args.max_search_requests is not None else monthly_budget
    remaining_budget = max(0, min(requested_cap, monthly_budget - already_used))
    if remaining_budget <= 0:
        raise SystemExit(f"No internal Text Search Enterprise budget remains for {month_key()}: used={already_used}, budget={monthly_budget}. This ledger only tracks this repo; verify Google Cloud billing before overriding.")

    zip_rows = next_zips(query, campaign, plan, int(args.max_zips))
    if not zip_rows:
        raise SystemExit("No eligible ZIPs remain. Expand the ZIP plan or wait for revisit windows.")

    run_id = str(uuid.uuid4())
    started = datetime.now(timezone.utc).isoformat()
    query("INSERT INTO campaign_runs (id,campaign_id,started_at,discovered_count,qualified_count,summary_json,status) VALUES (?,?,?,?,?,?,?)", [run_id, campaign["id"], started, 0, 0, "{}", "running"])

    accepted: list[dict] = []
    all_links: list[dict] = []
    zip_log: list[dict] = []
    run_seen_ids: set[str] = set()
    run_seen_domains: set[str] = set()
    search_requests = 0
    workers = int((campaign.get("crawl") or {}).get("default_workers") or 4)
    max_pages = int(google.get("max_pages_per_zip") or 3)
    paginate_raw_floor = int(google.get("paginate_if_first_page_raw_count_at_least") or 20)
    paginate_zip_floor = int(google.get("paginate_if_first_page_exact_zip_count_at_least") or 5)
    stop_reason = "target_reached"

    for zip_index, zip_row in enumerate(zip_rows, 1):
        if len(accepted) >= target:
            break
        if search_requests >= remaining_budget:
            stop_reason = "request_budget_exhausted"; break

        zip_code = str(zip_row["zip_code"])
        mark_zip_in_progress(query, campaign["id"], zip_code, run_id)
        metrics = {"page_count": 0, "raw_places": 0, "exact_zip_places": 0, "quality_passes": 0, "net_new_domains": 0, "duplicate_place_ids": 0, "duplicate_domains": 0}
        page_token = None
        page_number = 1
        zip_error = None
        target_hit_inside_zip = False
        next_token_remaining = False

        while page_number <= max_pages:
            if search_requests >= remaining_budget:
                stop_reason = "request_budget_exhausted"; break

            status_code, payload, error = search_zip_page(key=key, campaign=campaign, zip_row=zip_row, page_number=page_number, page_token=page_token)
            if status_code != 200 or payload is None:
                zip_error = error or "Text Search failed"; break

            search_requests += 1
            record_usage(query, campaign["id"], run_id, zip_code, page_number)
            metrics["page_count"] += 1
            candidates, counts = quality_candidates(payload, campaign, zip_code)
            metrics["raw_places"] += counts["raw_places"]
            metrics["exact_zip_places"] += counts["exact_zip_places"]
            metrics["quality_passes"] += counts["quality_passes"]

            fresh_for_crawl = []
            for candidate in candidates:
                pid = candidate["place_id"]
                seed_domain = candidate.get("seed_business_domain")
                if pid in existing_ids or pid in run_seen_ids:
                    metrics["duplicate_place_ids"] += 1; continue
                run_seen_ids.add(pid)
                if not seed_domain:
                    continue
                if seed_domain in existing_domains or seed_domain in suppressed_domains or seed_domain in run_seen_domains:
                    metrics["duplicate_domains"] += 1; continue
                fresh_for_crawl.append(candidate)

            crawled_rows = crawl_candidates(fresh_for_crawl, zip_row, workers) if fresh_for_crawl else []
            for crawled in crawled_rows:
                if crawled.get("crawl_status") != "completed":
                    continue
                final_domain = crawled.get("final_business_domain")
                final_url = crawled.get("final_url")
                if not final_domain or not final_url:
                    continue
                if final_domain in existing_domains or final_domain in suppressed_domains or final_domain in run_seen_domains:
                    metrics["duplicate_domains"] += 1; continue

                stored = persist_open_web_lead(query, campaign=campaign, run_id=run_id, zip_row=zip_row, crawled=crawled)
                accepted.append(stored)
                metrics["net_new_domains"] += 1
                existing_ids.add(stored["place_id"])
                existing_domains.add(final_domain)
                run_seen_domains.add(final_domain)
                for link in crawled.get("links") or []:
                    all_links.append({"place_id": stored["place_id"], "source_zip": zip_code, "homepage": final_url, "url": link.get("url"), "anchor_text": link.get("anchor_text") or ""})
                if len(accepted) >= target:
                    target_hit_inside_zip = True; break

            next_token = payload.get("nextPageToken")
            next_token_remaining = bool(next_token)
            if target_hit_inside_zip:
                break
            if not next_token:
                break
            if page_number == 1:
                should_paginate = counts["raw_places"] >= paginate_raw_floor and counts["exact_zip_places"] >= paginate_zip_floor
                if not should_paginate:
                    next_token_remaining = False; break
            page_token = next_token
            page_number += 1

        if zip_error:
            zip_status = "failed"; note = zip_error
        elif target_hit_inside_zip or stop_reason == "request_budget_exhausted":
            zip_status = "partial"; note = f"Stopped before fully exhausting ZIP because {stop_reason}."
        elif next_token_remaining and metrics["page_count"] >= max_pages:
            zip_status = "saturated"; note = f"Reached configured max_pages_per_zip={max_pages}."
        else:
            zip_status = "covered"; note = "ZIP pass completed under pagination policy."

        finish_zip(query, campaign_id=campaign["id"], run_id=run_id, zip_row=zip_row, status=zip_status, metrics=metrics, note=note)
        zip_log.append({"zip_code": zip_code, "city": zip_row.get("city"), "state": zip_row.get("state_code"), "status": zip_status, **metrics, "accepted_total_after_zip": len(accepted), "note": note})
        print(f"[{zip_index}/{len(zip_rows)}] {zip_code} {zip_row.get('city')}, {zip_row.get('state_code')} pages={metrics['page_count']} raw={metrics['raw_places']} exact_zip={metrics['exact_zip_places']} quality={metrics['quality_passes']} new={metrics['net_new_domains']} total={len(accepted)}/{target}")
        if target_hit_inside_zip:
            stop_reason = "target_reached"; break
        if stop_reason == "request_budget_exhausted":
            break

    completed = len(accepted) >= target
    if not completed and stop_reason == "target_reached":
        stop_reason = "zip_queue_exhausted"
    completed_at = datetime.now(timezone.utc).isoformat()
    summary = {
        "campaign": campaign["id"], "run_id": run_id, "target_net_new_domains": target,
        "net_new_domains_collected": len(accepted), "minimum_rating_screen": 4.0,
        "minimum_review_count_screen": int((campaign.get("quality") or {}).get("min_reviews") or 20),
        "zip_rows_processed": len(zip_log), "text_search_enterprise_requests_this_run": search_requests,
        "internal_monthly_request_budget": monthly_budget, "repo_ledger_requests_before_run": already_used,
        "repo_ledger_requests_after_run": already_used + search_requests, "stop_reason": stop_reason,
        "google_non_id_fields_persisted": False, "google_place_id_persisted": True,
        "website_and_links_source": "crawl4ai_open_web", "status": "completed" if completed else f"partial_{stop_reason}",
        "started_at": started, "completed_at": completed_at,
        "note": "Google Places non-ID fields were used transiently for screening/crawler seeding and were not written to the lead artifact/D1. The API usage ledger is repo-local and is not a substitute for Google Cloud billing reports."
    }
    write_outputs(out_dir, accepted, summary, zip_log, all_links)
    query("UPDATE campaign_runs SET completed_at=?, discovered_count=?, qualified_count=0, summary_json=?, status=? WHERE id=?", [completed_at, len(accepted), json.dumps(summary, separators=(",", ":")), summary["status"], run_id])
    print(json.dumps(summary, indent=2))
    if not completed:
        remaining = target - len(accepted)
        raise SystemExit(f"Collected and saved {len(accepted)}/{target} net-new businesses. Remaining={remaining}. Stop reason={stop_reason}. Re-run later; global Place-ID/domain dedupe prevents re-counting saved leads.")


if __name__ == "__main__":
    main()
