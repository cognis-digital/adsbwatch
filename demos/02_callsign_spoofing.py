"""Scenario 2 - journalists & open-source investigators: the spoofing story.

A reporter has a flight-tracking dump and a tip that an aircraft was "flying
under a fake call sign." adsbwatch turns that hunch into something citable: one
hardware address (ICAO 24-bit) that broadcast two different callsigns, plus any
malformed identifiers. The JSON output is the evidence you paste into the story
or hand to a data desk - reproducible from the same public-style feed.
"""
import json

from _common import rule, sub, load_feed, fmt_ts


def main() -> None:
    from adsbwatch.core import analyze

    rule("CALLSIGN SPOOFING  -  one aircraft, two identities")

    observations = load_feed()
    result = analyze(observations)

    spoofs = [a for a in result.anomalies if a.kind == "callsign_spoof"]
    print(f"\nScanned {result.observations} reports / {result.aircraft} aircraft; "
          f"{len(spoofs)} callsign anomaly/anomalies.\n")

    for a in spoofs:
        print(f"  ICAO {a.icao}  ({a.severity}) at {fmt_ts(a.timestamp)}")
        print(f"    {a.detail}")
        callsigns = a.evidence.get("callsigns")
        if callsigns:
            print(f"    distinct callsigns from one transponder: {callsigns}")
        print()

    sub("The citable artifact (machine-readable JSON)")
    # Real exporter: AnalysisResult.to_dict(), filtered to the spoofing finding.
    payload = result.to_dict()
    payload["anomalies"] = [a.to_dict() for a in spoofs]
    payload["anomaly_count"] = len(spoofs)
    print(json.dumps(payload, indent=2))

    sub("Why it holds up")
    print("  The ICAO 24-bit address is burned into the transponder hardware; a")
    print("  single address emitting two airline callsigns in one pass is the")
    print("  signature of a swapped identity, not normal operations. The finding")
    print("  is reproducible: same CSV in, same JSON out, offline, every time.")


if __name__ == "__main__":
    main()
