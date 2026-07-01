"""Scenario 20 - the combined spoofing signature.

A determined spoofer trips more than one detector at once: one hardware address
emitting two callsigns AND a position that teleports. This demo builds that
combined track and shows adsbwatch surfacing BOTH the callsign-spoof and the
impossible-kinematics anomaly for the same ICAO - corroborating evidence of a
manipulated identity. Offline, stdlib only.
"""
from _common import rule, sub, print_anomaly


def main() -> None:
    from adsbwatch.core import Observation, analyze

    rule("SPOOF COMBO  -  two identities AND a teleport, one ICAO")

    icao = "BADA55"
    obs = [
        # First identity, over New York.
        Observation(timestamp=0, icao=icao, callsign="UAL100", lat=40.64, lon=-73.78),
        Observation(timestamp=30, icao=icao, callsign="UAL100", lat=40.66, lon=-73.74),
        # Second identity AND an impossible jump to London ~30s later.
        Observation(timestamp=60, icao=icao, callsign="DAL999", lat=51.47, lon=-0.45),
    ]

    result = analyze(obs)
    sub(f"Anomalies for ICAO {icao}")
    for a in result.anomalies:
        print_anomaly(a)

    kinds = {a.kind for a in result.anomalies if a.icao == icao}
    sub("Corroboration")
    print(f"  detectors tripped for {icao}: {sorted(kinds)}")
    print("  A single address that both wears two airline callsigns and jumps the")
    print("  Atlantic in 30s is not a data glitch - it is a manufactured track.")
    print("  Two independent detectors agreeing is the citable part of the story.")
    assert "callsign_spoof" in kinds
    assert "impossible_kinematics" in kinds


if __name__ == "__main__":
    main()
