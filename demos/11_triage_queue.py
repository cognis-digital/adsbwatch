"""Scenario 11 - watch officers: a triaged work queue.

When many anomalies fire, the operator needs the most important one at the top,
with near-duplicate repeats merged into a single, higher-confidence line. This
demo runs the real `decision.triage()` over the sample feed's anomalies and
prints the ranked queue - highest priority first. Offline, stdlib only.
"""
from _common import rule, sub, load_feed


def main() -> None:
    from adsbwatch.core import analyze
    from adsbwatch import decision

    rule("TRIAGE QUEUE  -  worst-first, duplicates merged")

    anomalies = analyze(load_feed()).anomalies
    ranked = decision.triage(anomalies, dedupe_window_s=120.0)

    sub(f"{len(ranked)} incident(s), ranked")
    for i, m in enumerate(ranked, 1):
        seen = f" x{m['count']}" if m["count"] > 1 else ""
        print(f"  [{i}] P{m['priority']:<4} {m['severity']:<8} {m['kind']:<22} "
              f"{m['icao']} {m['callsign'] or '-'}  conf={m['confidence']}{seen}")
        print(f"      {m['detail']}")

    sub("How the priority is built")
    print("  priority = severity rank, nudged up by persistence (repeat sightings).")
    print("  Confidence rises from low -> medium -> high as the same anomaly recurs")
    print("  inside the dedupe window, so a one-off blip never outranks a pattern.")
    assert ranked, "sample feed should produce at least one incident"
    prios = [m["priority"] for m in ranked]
    assert prios == sorted(prios, reverse=True)


if __name__ == "__main__":
    main()
