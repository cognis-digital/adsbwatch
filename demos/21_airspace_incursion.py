"""Scenario 21 - airspace monitoring: restricted-zone / NOTAM incursion.

Loads OFFLINE restricted-airspace zones (a circle range + a polygon TFR from a
bundled JSON fixture - stand-ins for a NOTAM/TFR export) and checks the sample
ADS-B feed for aircraft that enter an active zone within its altitude band. Pure
situational awareness for a human: it reports *that* a track entered a monitored
volume, nothing more. Offline, zero dependencies.
"""
import os

from _common import rule, sub, load_feed, print_anomaly, DEMO_DIR


def main() -> None:
    from adsbwatch import airspace

    rule("AIRSPACE INCURSION  -  offline restricted-zone / NOTAM check")

    observations = load_feed()
    zones = airspace.load_zones(os.path.join(DEMO_DIR, "01-basic", "zones.json"))

    sub(f"Loaded {len(zones)} restricted zone(s)")
    for z in zones:
        band = ""
        if z.alt_floor_ft is not None or z.alt_ceiling_ft is not None:
            band = f"  band {z.alt_floor_ft or 0:.0f}-{z.alt_ceiling_ft or 99999:.0f} ft"
        print(f"    [{z.severity:<8}] {z.shape:<8} {z.id}  ({z.name}){band}")

    incursions = airspace.detect_incursions(observations, zones)
    sub(f"Incursions detected: {len(incursions)}")
    for a in incursions:
        print_anomaly(a)

    print("\n  Scope: descriptive airspace monitoring for a human analyst - it")
    print("  reports that a track entered a monitored volume; it does not target.")
    assert isinstance(incursions, list)


if __name__ == "__main__":
    main()
