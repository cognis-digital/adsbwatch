"""Scenario 12 - multi-INT fusion: correlate ADS-B with local sensors.

An ADS-B anomaly is stronger evidence when a camera and an RF logger saw
something at the same place and time. This demo fuses a loiter anomaly with
committed local-sensor records on a shared timeline via `decision.correlate()`,
showing corroboration and a confidence note - pattern-of-life, not targeting.
Offline, stdlib only.
"""
from _common import rule, sub, SENSORS_CSV


def main() -> None:
    from adsbwatch.core import Anomaly
    from adsbwatch import decision

    rule("SENSOR FUSION  -  ADS-B + camera + RF on one timeline")

    events = decision.load_sensor_events(SENSORS_CSV)
    sub(f"Local sensor log ({len(events)} event(s))")
    for e in events:
        print(f"  {e.source:<16} {e.type:<14} t={e.timestamp:.0f}  {e.detail}")

    # An anomaly whose time lines up with the first two sensor events.
    base = events[0].timestamp
    a = Anomaly("loiter", "medium", "100200", "N551LW",
                "Loiter over sector N", base + 20)

    sub("Correlate the anomaly against the sensor timeline (+/-60s)")
    corr = decision.correlate([a], events, window_s=60.0)[0]
    print(f"  corroborated: {corr['corroborated']}")
    print(f"  confidence:   {corr['confidence']}  (evidence_count={corr['evidence_count']})")
    for hit in corr["correlated_events"]:
        print(f"    + {hit['source']}/{hit['type']} (dt {hit['dt_s']:+.0f}s): {hit['detail']}")

    sub("Why fuse")
    print("  A lone ADS-B blip can be a data artifact; a blip a camera and an RF")
    print("  logger both saw at the same spot is a real contact worth a human's")
    print("  time. Correlation raises confidence without ever naming a response.")
    assert corr["corroborated"]


if __name__ == "__main__":
    main()
