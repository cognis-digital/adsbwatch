"""Scenario 24 - Cursor-on-Target (CoT) feed for ATAK / TAK.

Exports each geolocated anomaly as a CoT event for a TAK common operating
picture (ATAK / WinTAK / TAK Server). The events are NEUTRAL/unknown air tracks
(type a-u-A) carrying the finding in a remark - situational awareness for an
operator, never a hostile targeting designation. Offline, stdlib only.
"""
import xml.etree.ElementTree as ET

from _common import rule, sub, load_feed


def main() -> None:
    from adsbwatch.core import analyze
    from adsbwatch import intel

    rule("COT / ATAK  -  push the picture to a TAK common operating picture")

    observations = load_feed()
    result = analyze(observations)
    cot = intel.export(result, "cot", observations=observations)

    root = ET.fromstring(cot)
    events = root.findall("event")

    sub(f"{len(events)} CoT event(s)")
    for ev in events:
        pt = ev.find("point")
        remark = ev.find("detail/remarks").text
        # a-u-A = atom / UNKNOWN affiliation / Air. Never hostile (a-h-*).
        assert ev.get("type") == "a-u-A" and "-h-" not in ev.get("type")
        print(f"    [{ev.get('type')}] ({pt.get('lat')}, {pt.get('lon')})  {remark}")

    print("\n  Affiliation is UNKNOWN (a-u-A) by design: this is shared awareness")
    print("  for a human, not a hostile designation and not a targeting cue.")
    assert root.tag == "events"


if __name__ == "__main__":
    main()
