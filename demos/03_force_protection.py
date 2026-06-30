"""Scenario 3 - defense / force-protection: decision SUPPORT, human in command.

A loiter over a sensitive site is rarely the whole story. The decision-support
layer triages the anomalies, fuses them with *other local sensors* (a camera
that saw motion, an RF logger that caught a burst) on a shared timeline, and
emits ADVISORY courses of action for the operator on watch. It commands NO
effector and never acts on its own - every recommendation needs a human.

This demo builds an aligned ADS-B + sensor timeline in code so the correlation
is visible, then runs the real `decision.assess()` report.
"""
from _common import rule, sub, fmt_ts


def main() -> None:
    from adsbwatch.core import Observation, analyze
    from adsbwatch import decision

    rule("FORCE PROTECTION  -  triage + correlate, operator decides")

    # An aircraft orbiting a fixed point near a perimeter (a loiter), built so
    # its timestamps line up with the local-sensor log below.
    import math
    base = 1717848000.0
    cx, cy = 38.50, -77.00
    r = 0.01  # ~0.6 NM orbit
    obs = []
    for i in range(12):
        ang = 2 * math.pi * i / 12
        obs.append(Observation(
            timestamp=base + i * 30,
            icao="100200",
            callsign="N551LW",
            lat=cx + r * math.cos(ang),
            lon=cy + r * math.sin(ang),
            altitude=4500,
            squawk="4521",
        ))

    # Other LOCAL sensors that fired around the same time (camera / RF logger).
    sensor_events = [
        decision.SensorEvent(timestamp=base + 60, source="camera-north",
                             type="motion", detail="Slow mover in sector N",
                             lat=38.50, lon=-77.00),
        decision.SensorEvent(timestamp=base + 75, source="rf-log",
                             type="rf_burst", detail="2.4GHz burst over the site",
                             lat=38.50, lon=-77.00),
    ]

    result = analyze(obs)
    print(f"\nADS-B: {result.observations} reports / {result.aircraft} aircraft, "
          f"{len(result.anomalies)} anomaly/anomalies.")
    print(f"Local sensors on the timeline: {len(sensor_events)} event(s).")

    report = decision.assess(result, sensor_events, window_s=120.0)

    sub("Decision-support report (advisory only)")
    print(f"  scope: {report['scope']}")
    print(f"  human_authorization_required: {report['human_authorization_required']}")
    print(f"  incidents: {report['incident_count']}\n")

    for i, inc in enumerate(report["incidents"], 1):
        corr = inc["correlation"]
        events = corr.get("correlated_events", [])
        print(f"  [{i}] {inc['kind']}  ICAO {inc['icao']} {inc['callsign'] or '-'}  "
              f"severity={inc['severity']} priority={inc['priority']} "
              f"confidence={inc['confidence']}")
        print(f"      {inc['detail']}")
        if events:
            print(f"      corroborated by {len(events)} sensor event(s):")
            for e in events:
                print(f"        + {e['source']}/{e['type']} (dt {e['dt_s']:+.0f}s): {e['detail']}")
        print("      recommended (the operator decides and acts):")
        for rec in inc["recommendations"]:
            print(f"        - [{rec['urgency']}] {rec['action']}: {rec['text']}")
        print()

    sub("Hard scope")
    print("  Every recommended action is sensing / notification / evidence work.")
    print("  There is NO interface to weapons, jammers or interceptors, and the")
    print("  layer never acts autonomously - enforced by an allow-list and tests.")


if __name__ == "__main__":
    main()
