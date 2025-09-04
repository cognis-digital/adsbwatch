"""Command-line interface for ADSBWATCH.

Usage:
    python -m adsbwatch scan FEED.csv [--format table|json]
    python -m adsbwatch --version

Exit codes:
    0  analysis ran, no anomalies found
    1  usage / parse error
    2  analysis ran, anomalies found (the tool's notion of a 'finding')
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Optional

from . import TOOL_NAME, TOOL_VERSION
from .core import parse_csv, analyze, AnalysisResult


def _fmt_ts(ts: float) -> str:
    from datetime import datetime, timezone
    try:
        return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except (OverflowError, OSError, ValueError):
        return str(ts)


def _render_table(result: AnalysisResult) -> str:
    lines = []
    lines.append(f"ADSBWATCH report  observations={result.observations} "
                 f"aircraft={result.aircraft} anomalies={len(result.anomalies)}")
    lines.append("-" * 72)
    if not result.anomalies:
        lines.append("No anomalies detected.")
        return "\n".join(lines)
    header = f"{'SEVERITY':<9} {'KIND':<17} {'ICAO':<7} {'CALLSIGN':<14} TIME"
    lines.append(header)
    for a in result.anomalies:
        lines.append(f"{a.severity:<9} {a.kind:<17} {a.icao:<7} "
                     f"{(a.callsign or '-'):<14} {_fmt_ts(a.timestamp)}")
        lines.append(f"    {a.detail}")
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog=TOOL_NAME,
        description="Defensive OSINT analysis of an ADS-B feed for anomalies "
                    "(emergency squawks, callsign spoofing, loiter patterns).",
    )
    p.add_argument("--version", action="version",
                   version=f"{TOOL_NAME} {TOOL_VERSION}")
    sub = p.add_subparsers(dest="command")

    scan = sub.add_parser("scan", help="Scan an ADS-B CSV feed for anomalies.")
    scan.add_argument("feed", help="Path to ADS-B observation CSV file.")
    scan.add_argument("--format", choices=("table", "json"), default="table",
                      help="Output format (default: table).")
    scan.add_argument("--loiter-radius", type=float, default=5.0,
                      metavar="NM",
                      help="Max track radius for loiter detection (default 5 NM).")
    scan.add_argument("--loiter-turn", type=float, default=270.0,
                      metavar="DEG",
                      help="Min cumulative turn for loiter (default 270 deg).")
    scan.add_argument("--loiter-points", type=int, default=6,
                      metavar="N",
                      help="Min track points for loiter (default 6).")
    return p


def main(argv: Optional[list] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command != "scan":
        parser.print_help()
        return 1

    try:
        observations = parse_csv(args.feed)
    except FileNotFoundError:
        print(f"error: feed not found: {args.feed}", file=sys.stderr)
        return 1
    except (ValueError, OSError) as e:
        print(f"error: failed to parse feed: {e}", file=sys.stderr)
        return 1

    result = analyze(
        observations,
        loiter_min_points=args.loiter_points,
        loiter_radius_nm=args.loiter_radius,
        loiter_min_turn_deg=args.loiter_turn,
    )

    if args.format == "json":
        print(json.dumps(result.to_dict(), indent=2))
    else:
        print(_render_table(result))

    # Non-zero when anomalies are present so the tool can drive alerting.
    return 2 if result.anomalies else 0


if __name__ == "__main__":
    raise SystemExit(main())
