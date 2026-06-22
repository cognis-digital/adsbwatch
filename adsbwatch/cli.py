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


def _render_assessment(report: dict) -> str:
    lines = [f"ADSBWATCH decision support  incidents={report['incident_count']}",
             f"scope: {report['scope']}",
             f"** human authorization required for any action **",
             "-" * 72]
    if not report["incidents"]:
        lines.append("No incidents to assess.")
        return "\n".join(lines)
    for i, inc in enumerate(report["incidents"], 1):
        corr = inc["correlation"]
        c = len(corr.get("correlated_events", []))
        lines.append(f"[{i}] P{inc['priority']:<4} {inc['severity']:<8} {inc['kind']:<16} "
                     f"{inc['icao']} {inc['callsign'] or '-'}  conf={inc['confidence']}"
                     f"{f'  +{c} corroborating sensor event(s)' if c else ''}")
        lines.append(f"      {inc['detail']}")
        lines.append("      recommended (operator decides):")
        for r in inc["recommendations"]:
            lines.append(f"        - [{r['urgency']}] {r['action']}: {r['text']}")
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
    scan.add_argument("feed", nargs="?", default=None,
                      help="Path to ADS-B observation CSV file (omit with --live).")
    scan.add_argument("--live", action="store_true",
                      help="Ingest live ADS-B from the OpenSky feed instead of a CSV.")
    scan.add_argument("--offline", action="store_true",
                      help="With --live: serve from the cached OpenSky snapshot (air-gap).")
    scan.add_argument("--region", default=None, metavar="LAT0,LON0,LAT1,LON1",
                      help="With --live: clip ingest to a lat/lon bounding box.")
    scan.add_argument("--format", choices=("table", "json", "geojson", "stix"), default="table",
                      help="Output format: table/json, or geojson (mapping) / stix (TIPs).")
    scan.add_argument("--loiter-radius", type=float, default=5.0,
                      metavar="NM",
                      help="Max track radius for loiter detection (default 5 NM).")
    scan.add_argument("--loiter-turn", type=float, default=270.0,
                      metavar="DEG",
                      help="Min cumulative turn for loiter (default 270 deg).")
    scan.add_argument("--loiter-points", type=int, default=6,
                      metavar="N",
                      help="Min track points for loiter (default 6).")

    # Decision SUPPORT (human-in-the-loop): triage + correlate + advisory recommendations.
    # This does NOT command effectors and never acts autonomously - it helps the operator.
    assess = sub.add_parser(
        "assess",
        help="Decision support: triage anomalies, correlate with local sensor logs, and "
             "recommend operator actions (advisory; human-in-the-loop, no effectors).")
    assess.add_argument("feed", help="Path to ADS-B observation CSV file.")
    assess.add_argument("--sensors", default=None,
                        help="Optional local sensor log (CSV/JSON: timestamp,source,type,"
                             "detail[,lat,lon]) to correlate - cameras, RF logs, access control.")
    assess.add_argument("--window", type=float, default=60.0,
                        help="Correlation time window in seconds (default 60).")
    assess.add_argument("--format", choices=("table", "json"), default="table")

    # Data-feed layer: live ADS-B ingestion from the OpenSky Network (catalog feed
    # opensky-states), cached to disk and re-servable offline for air-gap use.
    feeds = sub.add_parser(
        "feeds",
        help="Live ADS-B data-feed layer (OpenSky): list | update | get <id> [--offline].")
    fsub = feeds.add_subparsers(dest="feeds_cmd")
    fsub.add_parser("list", help="List the ADS-B feed(s) wired into adsbwatch.")
    fu = fsub.add_parser("update", help="Fetch + cache the live OpenSky feed.")
    fu.add_argument("feed_id", nargs="?", default="opensky-states")
    fg = fsub.add_parser("get", help="Ingest OpenSky states as scan-ready input.")
    fg.add_argument("feed_id", nargs="?", default="opensky-states")
    fg.add_argument("--offline", action="store_true",
                    help="Serve from the cached snapshot only (air-gap; no network).")
    fg.add_argument("--region", default=None, metavar="LAT0,LON0,LAT1,LON1",
                    help="Clip to a lat/lon bounding box.")
    return p


def _parse_region(spec):
    if not spec:
        return None
    parts = [float(x) for x in spec.split(",")]
    if len(parts) != 4:
        raise ValueError("region must be LAT0,LON0,LAT1,LON1")
    return tuple(parts)


def main(argv: Optional[list] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command not in ("scan", "assess", "feeds"):
        parser.print_help()
        return 1

    if args.command == "feeds":
        from . import feeds as feeds_mod
        if getattr(args, "feeds_cmd", None) is None:
            print("usage: adsbwatch feeds {list|update|get} [<id>] [--offline]",
                  file=sys.stderr)
            return 1
        try:
            args._region = _parse_region(getattr(args, "region", None))
        except ValueError as e:
            print(f"error: {e}", file=sys.stderr)
            return 1
        return feeds_mod.feeds_main(args)

    # scan --live ingests the OpenSky feed directly; otherwise read the CSV.
    if args.command == "scan" and getattr(args, "live", False):
        from . import feeds as feeds_mod
        try:
            region = _parse_region(args.region)
            observations = feeds_mod.fetch_observations(
                offline=args.offline, region=region)
        except FileNotFoundError as e:
            print(f"error: {e}", file=sys.stderr)
            return 1
        except (ValueError, KeyError, ConnectionError) as e:
            print(f"error: live ingest failed: {e}", file=sys.stderr)
            return 1
    else:
        if not args.feed:
            print("error: provide a feed CSV path or use --live", file=sys.stderr)
            return 1
        try:
            observations = parse_csv(args.feed)
        except FileNotFoundError:
            print(f"error: feed not found: {args.feed}", file=sys.stderr)
            return 1
        except (ValueError, OSError) as e:
            print(f"error: failed to parse feed: {e}", file=sys.stderr)
            return 1

    if args.command == "assess":
        from . import decision
        result = analyze(observations)
        sensor_events = []
        if args.sensors:
            try:
                sensor_events = decision.load_sensor_events(args.sensors)
            except (OSError, ValueError) as e:
                print(f"error: failed to read sensors: {e}", file=sys.stderr)
                return 1
        report = decision.assess(result, sensor_events, window_s=args.window)
        if args.format == "json":
            print(json.dumps(report, indent=2))
        else:
            print(_render_assessment(report))
        return 2 if report["incident_count"] else 0

    result = analyze(
        observations,
        loiter_min_points=args.loiter_points,
        loiter_radius_nm=args.loiter_radius,
        loiter_min_turn_deg=args.loiter_turn,
    )

    if args.format in ("geojson", "stix"):
        from . import intel
        print(intel.export(result, args.format, observations=observations))
    elif args.format == "json":
        print(json.dumps(result.to_dict(), indent=2))
    else:
        print(_render_table(result))

    # Non-zero when anomalies are present so the tool can drive alerting.
    return 2 if result.anomalies else 0


if __name__ == "__main__":
    raise SystemExit(main())
