"""Scenario 16 - the whole pipeline in one pass.

Ingest -> analyse -> triage -> correlate -> recommend -> export. This scenario
walks the complete adsbwatch workflow end to end over the bundled feed and
sensor log, touching every layer of the real API, and prints a compact summary
at each stage. Offline, stdlib only.
"""
import json

from _common import rule, sub, load_feed, SENSORS_CSV


def main() -> None:
    from adsbwatch.core import analyze
    from adsbwatch import decision, intel

    rule("FULL PIPELINE  -  ingest -> analyse -> decide -> export")

    # 1. ingest + analyse
    observations = load_feed()
    result = analyze(observations)
    sub("1. Ingest + analyse")
    print(f"  {result.observations} reports / {result.aircraft} aircraft -> "
          f"{len(result.anomalies)} anomaly/anomalies")
    kinds = {}
    for a in result.anomalies:
        kinds[a.kind] = kinds.get(a.kind, 0) + 1
    print("  by kind: " + ", ".join(f"{k}={v}" for k, v in sorted(kinds.items())))

    # 2. decision support (triage + correlate + advisory recs)
    sensors = decision.load_sensor_events(SENSORS_CSV)
    report = decision.assess(result, sensors)
    sub("2. Decision support (human-in-the-loop)")
    print(f"  incidents: {report['incident_count']}  "
          f"human_authorization_required: {report['human_authorization_required']}")
    top = report["incidents"][0]
    print(f"  top incident: {top['kind']} {top['icao']} (P{top['priority']}, "
          f"{len(top['recommendations'])} advisory rec(s))")

    # 3. exports
    sub("3. Export for downstream tools")
    geo = json.loads(intel.export(result, "geojson", observations=observations))
    stix = json.loads(intel.export(result, "stix", observations=observations))
    print(f"  GeoJSON: {len(geo['features'])} map feature(s)")
    print(f"  STIX 2.1: {len(stix['objects'])} bundle object(s)")

    sub("One feed, every consumer")
    print("  A single CSV drove anomaly detection, an operator work-queue with")
    print("  sensor corroboration, and both a map layer and a TIP bundle - offline,")
    print("  no dependencies, and no action taken without a human.")
    assert report["human_authorization_required"] is True
    assert geo["type"] == "FeatureCollection" and stix["type"] == "bundle"


if __name__ == "__main__":
    main()
