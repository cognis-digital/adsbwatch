"""Shared helpers for the adsbwatch demo scenarios.

Every scenario is OFFLINE and uses the REAL adsbwatch API: it parses a bundled
sample ADS-B CSV, runs the anomaly engine, and (where relevant) the
decision-support / intel-export / live-feed layers. No network access.
"""
from __future__ import annotations

import os
import sys

# allow `python demos/NN_name.py` from anywhere
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEMO_DIR = os.path.join(REPO_ROOT, "demos")

# The bundled sample feeds shipped with the repo (committed fixtures).
FEED_CSV = os.path.join(DEMO_DIR, "01-basic", "feed.csv")
SENSORS_CSV = os.path.join(DEMO_DIR, "01-basic", "sensors.csv")
# Offline OpenSky snapshot used for the live-feed demo (no network).
FEEDS_CACHE = os.path.join(REPO_ROOT, "tests", "fixtures", "feeds_cache")

SEV_ICON = {"critical": "[CRIT]", "high": "[HIGH]", "medium": "[MED ]", "low": "[LOW ]"}


def rule(title: str) -> None:
    print("\n" + "=" * 72)
    print(f"  {title}")
    print("=" * 72)


def sub(title: str) -> None:
    print("\n" + "-" * 72)
    print(f"  {title}")
    print("-" * 72)


def fmt_ts(ts: float) -> str:
    from datetime import datetime, timezone
    try:
        return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ")
    except (OverflowError, OSError, ValueError):
        return str(ts)


def load_feed(path: str = FEED_CSV):
    """Parse a sample ADS-B CSV into Observation rows (real parser, offline)."""
    from adsbwatch.core import parse_csv
    return parse_csv(path)
