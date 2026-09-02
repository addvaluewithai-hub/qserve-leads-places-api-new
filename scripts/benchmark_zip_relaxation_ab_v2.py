#!/usr/bin/env python3
from __future__ import annotations

"""Compatibility wrapper for the read-only ZIP relaxation A/B benchmark."""

import benchmark_zip_relaxation_ab as benchmark
import zip_manager


def load_plan_compat(value):
    if isinstance(value, dict):
        return zip_manager.load_plan(value)
    return zip_manager.load_plan({"market_plan": str(value)})


benchmark.load_plan = load_plan_compat


if __name__ == "__main__":
    benchmark.main()
