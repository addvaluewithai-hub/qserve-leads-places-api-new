#!/usr/bin/env python3
from __future__ import annotations

"""Production ZIP V3 wrapper.

Adds Cloudflare D1-safe batching to the hardened V2 builder. D1 currently
supports at most 100 bound parameters per query, so every multi-row insert is
chunked by columns-per-row instead of relying on a fixed row count.
"""

# ZIP queue rows bind 9 values each. Keep materialization under the D1
# 100-bound-parameter limit before importing the hardened builder/core.
import zip_manager
zip_manager.ZIP_UPSERT_BATCH = 10

import build_next_1000_lawyers_zip_v2 as hardened

D1_MAX_BOUND_PARAMS = 100


def safe_multi_insert(
    query,
    prefix: str,
    rows: list[tuple],
    columns_per_row: int,
    suffix: str = "",
    chunk_size: int = 50,
):
    if not rows:
        return
    max_rows_by_params = max(1, D1_MAX_BOUND_PARAMS // max(1, int(columns_per_row)))
    effective_chunk = max(1, min(int(chunk_size), max_rows_by_params))
    placeholder = "(" + ",".join("?" for _ in range(columns_per_row)) + ")"

    for start in range(0, len(rows), effective_chunk):
        chunk = rows[start:start + effective_chunk]
        sql = prefix + ",".join(placeholder for _ in chunk)
        if suffix:
            sql += "\n" + suffix
        params = [value for row in chunk for value in row]
        if len(params) > D1_MAX_BOUND_PARAMS:
            raise RuntimeError(
                f"D1 parameter guard failed: {len(params)} params > {D1_MAX_BOUND_PARAMS}"
            )
        query(sql, params)


# _flush_zip resolves _multi_insert from the V2 module at runtime, so this
# patch applies to leads, campaign membership, screening evidence, homepage
# links and final lead-domain completion markers.
hardened._multi_insert = safe_multi_insert


if __name__ == "__main__":
    hardened.core.main()
