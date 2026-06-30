"""Scenario 1 - OSINT / aviation analysts: scan a feed for anomalies.

You have a CSV of ADS-B position reports off a cheap receiver. Before you stare
at a map, you want the machine to surface the *interesting* aircraft: who is
squawking an emergency, who is broadcasting more than one identity, and who is
circling instead of transiting. This demo runs the real anomaly engine over the
bundled sample feed and walks the findings, worst-first.
"""
from _common import rule, sub, load_feed, fmt_ts, SEV_ICON, FEED_CSV


def main() -> None:
    from adsbwatch.core import analyze

    rule("ANOMALY SCAN  -  surface the interesting aircraft first")
    print(f"\nFeed: {FEED_CSV}")

    observations = load_feed()
    result = analyze(observations)

    print(f"\nIngested {result.observations} position report(s) "
          f"across {result.aircraft} aircraft.")
    print(f"Engine flagged {len(result.anomalies)} anomaly/anomalies "
          f"(sorted critical -> low).\n")

    by_kind = {}
    for a in result.anomalies:
        by_kind.setdefault(a.kind, 0)
        by_kind[a.kind] += 1
    print("  by kind: " + ", ".join(f"{k}={v}" for k, v in sorted(by_kind.items())))

    sub("Findings, worst first")
    for a in result.anomalies:
        icon = SEV_ICON.get(a.severity, "[????]")
        print(f"\n{icon} {a.kind}  ({a.severity})")
        print(f"     aircraft : ICAO {a.icao}  callsign {a.callsign or '-'}")
        print(f"     when     : {fmt_ts(a.timestamp)}")
        print(f"     detail   : {a.detail}")
        if a.evidence:
            keys = ", ".join(f"{k}={v}" for k, v in list(a.evidence.items())[:4])
            print(f"     evidence : {keys}")

    sub("Analyst takeaway")
    print("  The 7700 general-emergency squawk is the headline; the single ICAO")
    print("  broadcasting two callsigns (UAL123 -> DAL999) is a likely identity")
    print("  flip; and the tight 270deg+ orbit is a loiter worth a second look.")
    print("  Everything above came from the REAL engine over a local CSV - no net.")


if __name__ == "__main__":
    main()
