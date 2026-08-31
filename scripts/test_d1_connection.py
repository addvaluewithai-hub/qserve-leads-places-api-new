#!/usr/bin/env python3
"""Smoke test Cloudflare D1 credentials from GitHub Actions.

This script uses the Cloudflare D1 HTTP API directly so it does not depend on
wrangler project configuration. It verifies that the configured API token can:
1. reach the database,
2. execute a read query,
3. create/write a tiny smoke-test table,
4. read the written row back.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any

REQUIRED_ENV = [
    "CLOUDFLARE_ACCOUNT_ID",
    "CLOUDFLARE_API_TOKEN",
    "D1_DATABASE_ID",
    "D1_DATABASE_NAME",
]


def require_env() -> dict[str, str]:
    values: dict[str, str] = {}
    missing: list[str] = []
    for name in REQUIRED_ENV:
        value = os.getenv(name)
        if not value:
            missing.append(name)
        else:
            values[name] = value
    if missing:
        print(f"Missing required secrets: {', '.join(missing)}", file=sys.stderr)
        raise SystemExit(2)
    return values


def d1_query(env: dict[str, str], sql: str, params: list[Any] | None = None) -> dict[str, Any]:
    url = (
        "https://api.cloudflare.com/client/v4/accounts/"
        f"{env['CLOUDFLARE_ACCOUNT_ID']}/d1/database/{env['D1_DATABASE_ID']}/query"
    )
    body = json.dumps({"sql": sql, "params": params or []}).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {env['CLOUDFLARE_API_TOKEN']}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        print(f"Cloudflare API HTTP {exc.code} for SQL: {sql}", file=sys.stderr)
        print(raw, file=sys.stderr)
        raise


def assert_success(payload: dict[str, Any], label: str) -> None:
    if not payload.get("success"):
        print(f"{label} failed:", file=sys.stderr)
        print(json.dumps(payload, indent=2), file=sys.stderr)
        raise SystemExit(1)


def rows_from(payload: dict[str, Any]) -> list[dict[str, Any]]:
    result = payload.get("result") or []
    if not result:
        return []
    return result[0].get("results") or []


def main() -> int:
    env = require_env()
    print(f"Testing Cloudflare D1 database: {env['D1_DATABASE_NAME']}")
    print(f"Database ID prefix: {env['D1_DATABASE_ID'][:8]}...")

    read_payload = d1_query(env, "SELECT 1 AS ok;")
    assert_success(read_payload, "SELECT 1")
    read_rows = rows_from(read_payload)
    print("Read test rows:", json.dumps(read_rows, ensure_ascii=False))
    if not read_rows or read_rows[0].get("ok") != 1:
        print("Unexpected SELECT 1 response.", file=sys.stderr)
        return 1

    create_sql = """
    CREATE TABLE IF NOT EXISTS _d1_smoke_test (
      key TEXT PRIMARY KEY,
      value TEXT NOT NULL,
      updated_at TEXT NOT NULL
    );
    """
    create_payload = d1_query(env, create_sql)
    assert_success(create_payload, "CREATE TABLE")
    print("Smoke table exists.")

    now = datetime.now(timezone.utc).isoformat()
    insert_payload = d1_query(
        env,
        """
        INSERT INTO _d1_smoke_test (key, value, updated_at)
        VALUES (?1, ?2, ?3)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at;
        """,
        ["github_actions", "d1_write_ok", now],
    )
    assert_success(insert_payload, "UPSERT smoke row")
    print("Write test completed.")

    verify_payload = d1_query(
        env,
        "SELECT key, value, updated_at FROM _d1_smoke_test WHERE key = ?1;",
        ["github_actions"],
    )
    assert_success(verify_payload, "VERIFY smoke row")
    verify_rows = rows_from(verify_payload)
    print("Verify rows:", json.dumps(verify_rows, ensure_ascii=False))
    if not verify_rows or verify_rows[0].get("value") != "d1_write_ok":
        print("Write verification failed.", file=sys.stderr)
        return 1

    print("D1 smoke test passed: read + write are working.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
