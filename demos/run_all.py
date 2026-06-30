"""Run every adsbwatch demo scenario end to end.

    python demos/run_all.py

Each scenario is independent and offline: it parses a bundled sample ADS-B feed
(or the committed OpenSky snapshot) and runs the real engine, so they can be run
in any order or on their own. Exits 0 when all scenarios complete.
"""
import importlib
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

SCENARIOS = [
    "01_anomaly_scan",
    "02_callsign_spoofing",
    "03_force_protection",
    "04_intel_export",
    "05_live_feed_offline",
]


def main() -> int:
    for name in SCENARIOS:
        mod = importlib.import_module(name)
        mod.main()
    print("\n" + "=" * 72)
    print(f"  All {len(SCENARIOS)} demo scenarios completed.")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
