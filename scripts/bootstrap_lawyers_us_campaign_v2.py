#!/usr/bin/env python3
from __future__ import annotations

# Cloudflare D1 currently allows at most 100 bound parameters per query.
# zip_coverage uses 9 bound values per row, so 10 rows stays safely below the limit.
import zip_manager
zip_manager.ZIP_UPSERT_BATCH = 10

import bootstrap_lawyers_us_campaign as core


if __name__ == "__main__":
    core.main()
