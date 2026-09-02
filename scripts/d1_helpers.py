#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_FILE = ROOT / "schema.sql"


def env_required(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise SystemExit(f"{name} is required")
    return value


def canonical_domain(url: str | None) -> str | None:
    if not url:
        return None
    try:
        value = url if "://" in url else f"https://{url}"
        host = (urlparse(value).hostname or "").lower().strip(".")
        return host[4:] if host.startswith("www.") else (host or None)
    except Exception:
        return None


def make_query_client():
    account_id = env_required("CLOUDFLARE_ACCOUNT_ID")
    token = env_required("CLOUDFLARE_API_TOKEN")
    database_id = env_required("D1_DATABASE_ID")
    api_url = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/d1/database/{database_id}/query"

    def query(sql: str, params=None):
        body = {"sql": sql}
        if params is not None:
            body["params"] = params
        request = urllib.request.Request(
            api_url,
            data=json.dumps(body).encode("utf-8"),
            method="POST",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=90) as response:
            payload = json.loads(response.read().decode("utf-8"))
        if not payload.get("success"):
            raise RuntimeError(payload)
        result_sets = payload.get("result") or []
        for result in result_sets:
            if result.get("success") is False:
                raise RuntimeError(result)
        return result_sets

    return query


def result_rows(result_sets) -> list[dict]:
    rows: list[dict] = []
    for result in result_sets or []:
        rows.extend(result.get("results") or [])
    return rows


def apply_schema(query) -> None:
    schema = SCHEMA_FILE.read_text(encoding="utf-8")
    for statement in [part.strip() for part in schema.split(";") if part.strip()]:
        query(statement)
