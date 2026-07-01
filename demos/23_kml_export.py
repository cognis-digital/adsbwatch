"""Scenario 23 - KML export for Google Earth / QGIS.

The scan's geolocated anomalies export as a KML document with one severity-styled
Placemark each, ready to open in Google Earth or QGIS. This demo emits the KML,
parses it back to prove it is well-formed, and counts the placemarks. Offline.
"""
import xml.etree.ElementTree as ET

from _common import rule, sub, load_feed


def main() -> None:
    from adsbwatch.core import analyze
    from adsbwatch import intel

    rule("KML EXPORT  -  open the anomaly picture in Google Earth / QGIS")

    observations = load_feed()
    result = analyze(observations)
    kml = intel.export(result, "kml", observations=observations)

    root = ET.fromstring(kml)   # proves it parses as XML
    ns = {"k": "http://www.opengis.net/kml/2.2"}
    marks = root.findall(".//k:Placemark", ns)

    sub(f"KML document with {len(marks)} placemark(s)")
    for pm in marks:
        name = pm.find("k:name", ns).text
        coords = pm.find(".//k:coordinates", ns).text
        print(f"    {name:<40} @ {coords}")

    print("\n  Severity drives the icon colour (red=critical ... green=low).")
    assert root.tag.endswith("kml")


if __name__ == "__main__":
    main()
