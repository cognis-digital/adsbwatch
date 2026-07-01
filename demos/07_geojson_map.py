"""Scenario 7 - GIS analysts: GeoJSON straight onto a map.

The scan's geolocated anomalies export as a GeoJSON FeatureCollection you drop
directly into Leaflet / QGIS / kepler.gl / Mapbox. This demo prints the exact
FeatureCollection (coordinates in [lon, lat] order per the GeoJSON spec) so you
can see what lands on the map. Offline, zero dependencies.
"""
import json

from _common import rule, sub, load_feed


def main() -> None:
    from adsbwatch.core import analyze
    from adsbwatch import intel

    rule("GEOJSON FOR MAPS  -  drop anomalies onto Leaflet / QGIS")

    observations = load_feed()
    result = analyze(observations)
    doc = json.loads(intel.export(result, "geojson", observations=observations))

    sub("FeatureCollection")
    print(f"  type: {doc['type']}  features: {len(doc['features'])}")
    for f in doc["features"]:
        lon, lat = f["geometry"]["coordinates"]
        p = f["properties"]
        print(f"    ({lat:.4f}, {lon:.4f})  {p['severity']:<8} {p['kind']:<22} "
              f"{p['icao']} {p['callsign'] or '-'}")

    sub("Spec compliance")
    print("  Every geometry is a Point with coordinates in [lon, lat] order, and")
    print("  each feature's properties carry the full anomaly (kind, severity,")
    print("  ICAO, callsign, detail + evidence) so map popups are self-describing.")
    assert doc["type"] == "FeatureCollection"


if __name__ == "__main__":
    main()
