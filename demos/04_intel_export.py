"""Scenario 4 - researchers & SOC analysts: export to maps and TIPs.

Findings are only useful in the tools your team already runs. adsbwatch's native,
zero-dependency intel layer turns the same scan into **GeoJSON** (drop straight
into Leaflet / QGIS / kepler.gl to plot the anomalies on a map) and a valid
**STIX 2.1** bundle (ingest into OpenCTI / any threat-intel platform). Offline,
stdlib only.
"""
import json

from _common import rule, sub, load_feed


def main() -> None:
    from adsbwatch.core import analyze
    from adsbwatch import intel

    rule("INTEL EXPORT  -  GeoJSON for maps, STIX 2.1 for TIPs")

    observations = load_feed()
    result = analyze(observations)
    print(f"\n{len(result.anomalies)} anomaly/anomalies to export "
          f"({result.aircraft} aircraft).")

    # --- GeoJSON -----------------------------------------------------------
    sub("GeoJSON (Leaflet / QGIS / kepler.gl)")
    geo = json.loads(intel.export(result, "geojson", observations=observations))
    feats = geo["features"]
    print(f"  FeatureCollection with {len(feats)} geolocated point feature(s):")
    for f in feats:
        lon, lat = f["geometry"]["coordinates"]
        p = f["properties"]
        print(f"    ({lat:.4f}, {lon:.4f})  {p['severity']:<8} {p['kind']:<16} "
              f"{p['icao']} {p['callsign'] or '-'}")

    # --- STIX 2.1 ----------------------------------------------------------
    sub("STIX 2.1 bundle (OpenCTI / TIPs)")
    bundle = json.loads(intel.export(result, "stix", observations=observations))
    types = {}
    for o in bundle["objects"]:
        types[o["type"]] = types.get(o["type"], 0) + 1
    print(f"  bundle id: {bundle['id']}")
    print(f"  {len(bundle['objects'])} object(s): "
          + ", ".join(f"{k}={v}" for k, v in sorted(types.items())))
    report = next(o for o in bundle["objects"] if o["type"] == "report")
    print(f"  report: {report['name']}")
    note = next((o for o in bundle["objects"] if o["type"] == "note"), None)
    if note:
        print(f"  sample note: {note['abstract']}  labels={note['labels']}")

    sub("Why two formats")
    print("  GeoJSON answers 'where is this happening?' on a map; STIX answers")
    print("  'how do I get this into my intel platform and correlate it?'. Same")
    print("  scan, two consumers, no extra dependencies, fully offline.")


if __name__ == "__main__":
    main()
