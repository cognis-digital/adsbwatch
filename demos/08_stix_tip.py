"""Scenario 8 - threat-intel teams: STIX 2.1 into a TIP.

The same scan exports as a valid STIX 2.1 bundle - a `report` grouping a
`location` + `observed-data` + `note` per anomaly - ingestible by OpenCTI or any
TAXII-fed platform. This demo prints the bundle's object breakdown and verifies
every report reference resolves. Offline, stdlib only.
"""
import json

from _common import rule, sub, load_feed


def main() -> None:
    from adsbwatch.core import analyze
    from adsbwatch import intel

    rule("STIX 2.1 FOR TIPs  -  a resolvable threat-report bundle")

    result = analyze(load_feed())
    bundle = json.loads(intel.export(result, "stix", observations=load_feed()))

    counts = {}
    for o in bundle["objects"]:
        counts[o["type"]] = counts.get(o["type"], 0) + 1

    sub("Bundle")
    print(f"  id: {bundle['id']}")
    print("  objects: " + ", ".join(f"{k}={v}" for k, v in sorted(counts.items())))

    sub("Reference integrity (a broken TIP import is worse than none)")
    ids = {o["id"] for o in bundle["objects"]}
    report = next(o for o in bundle["objects"] if o["type"] == "report")
    unresolved = [r for r in report["object_refs"] if r not in ids]
    print(f"  report '{report['name']}' references {len(report['object_refs'])} object(s)")
    print(f"  unresolved references: {len(unresolved)}")
    assert not unresolved, "report references must all resolve"
    for o in bundle["objects"]:
        if o["type"] != "bundle":
            assert o["id"].startswith(o["type"] + "--")
            assert o.get("spec_version") == "2.1"
    print("  every SDO/SRO is 2.1 and correctly id-prefixed.")


if __name__ == "__main__":
    main()
