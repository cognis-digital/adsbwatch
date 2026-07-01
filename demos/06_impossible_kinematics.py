"""Scenario 6 - spoofing hunters: impossible kinematics (position injection).

A real aircraft cannot teleport. When one ICAO 24-bit address reports two
positions whose separation implies a ground speed far beyond any aircraft, the
position is almost certainly SPOOFED or INJECTED (or the ICAO has been cloned
onto two airframes). This demo builds such a track and runs the real
impossible-kinematics detector - offline, stdlib only.
"""
from _common import rule, sub, print_anomaly


def main() -> None:
    from adsbwatch.core import Observation, analyze

    rule("IMPOSSIBLE KINEMATICS  -  a track that teleports = a spoof")

    # One hardware address 'jumping' JFK -> Heathrow in a single 60s interval.
    obs = [
        Observation(timestamp=0, icao="5P00F1", callsign="GHOST", lat=40.64, lon=-73.78),
        Observation(timestamp=60, icao="5P00F1", callsign="GHOST", lat=51.47, lon=-0.45),
    ]
    # Also a normal transiting airliner that must NOT trip the detector.
    obs += [
        Observation(timestamp=0, icao="AAA111", callsign="UAL10", lat=40.0, lon=-74.0),
        Observation(timestamp=600, icao="AAA111", callsign="UAL10", lat=40.6, lon=-74.6),
    ]

    sub("Two aircraft: one teleports, one flies normally")
    result = analyze(obs)
    print(f"  {result.observations} reports / {result.aircraft} aircraft -> "
          f"{len(result.anomalies)} anomaly/anomalies\n")

    for a in result.anomalies:
        print_anomaly(a)
        ev = a.evidence
        if a.kind == "impossible_kinematics":
            spd = ev.get("implied_speed_kt")
            print(f"      implied speed: {'infinite (same timestamp)' if spd is None else f'{spd:.0f} kt'} "
                  f"over {ev['distance_nm']:.0f} NM in {ev['dt_sec']:.0f}s "
                  f"(ceiling {ev['max_speed_kt']:.0f} kt)")

    sub("Tunable ceiling")
    print("  The default ground-speed ceiling is deliberately high (3500 kt) so")
    print("  conventional aircraft never trip it. A paranoid analyst can lower it")
    print("  with `adsbwatch scan --max-speed 900` to also catch suspiciously fast")
    print("  'aircraft', or set --max-speed 0 to switch the detector off entirely.")


if __name__ == "__main__":
    main()
