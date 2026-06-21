"""Native intel export — GeoJSON + STIX 2.1 for ADS-B anomalies."""

import json

from adsbwatch.core import Observation, Anomaly, AnalysisResult
from adsbwatch import intel


def _obs():
    return [
        Observation(timestamp=1750000000, icao="ABC123", callsign="HIJACK1",
                    lat=51.5, lon=-0.12, squawk="7500"),
        Observation(timestamp=1750000060, icao="DEF456", callsign="SCOUT",
                    lat=52.0, lon=-1.0, squawk="1200"),
    ]


def _result():
    anomalies = [
        Anomaly(kind="emergency_squawk", severity="critical", icao="ABC123",
                callsign="HIJACK1", detail="Squawk 7500 (hijack)", timestamp=1750000000,
                evidence={"squawk": "7500"}),
        Anomaly(kind="loiter", severity="medium", icao="DEF456", callsign="SCOUT",
                detail="Loiter orbit", timestamp=1750000060,
                evidence={"center": [52.0, -1.0], "radius_nm": 1.2}),
    ]
    return AnalysisResult(observations=2, aircraft=2, anomalies=anomalies)


def test_geojson_points_and_lonlat_order():
    doc = json.loads(intel.to_geojson(_result(), _obs()))
    assert doc["type"] == "FeatureCollection"
    assert len(doc["features"]) == 2
    # emergency squawk anomaly gets its position from the observation stream
    sq = next(f for f in doc["features"] if f["properties"]["kind"] == "emergency_squawk")
    assert sq["geometry"]["coordinates"] == [-0.12, 51.5]  # [lon, lat]
    # loiter gets coords from its own evidence center
    lo = next(f for f in doc["features"] if f["properties"]["kind"] == "loiter")
    assert lo["geometry"]["coordinates"] == [-1.0, 52.0]


def test_geojson_skips_uncoordinated():
    r = AnalysisResult(observations=1, aircraft=1, anomalies=[
        Anomaly(kind="callsign_spoof", severity="high", icao="ZZZ999",
                callsign="GHOST", detail="multiple callsigns", timestamp=1, evidence={})])
    doc = json.loads(intel.to_geojson(r, observations=[]))  # no position known
    assert doc["features"] == []


def test_stix_bundle_valid():
    doc = json.loads(intel.to_stix(_result(), _obs()))
    assert doc["type"] == "bundle"
    types = {o["type"] for o in doc["objects"]}
    assert {"report", "observed-data", "note", "location"} <= types
    for o in doc["objects"]:
        if o["type"] != "bundle":
            assert o["id"].startswith(o["type"] + "--")
            assert o.get("spec_version") == "2.1"


def test_stix_report_refs_resolve():
    doc = json.loads(intel.to_stix(_result(), _obs()))
    ids = {o["id"] for o in doc["objects"]}
    report = next(o for o in doc["objects"] if o["type"] == "report")
    assert all(ref in ids for ref in report["object_refs"])


def test_deterministic():
    assert intel.to_stix(_result(), _obs()) == intel.to_stix(_result(), _obs())
    assert intel.to_geojson(_result(), _obs()) == intel.to_geojson(_result(), _obs())


def test_export_dispatch_and_error():
    import pytest
    assert json.loads(intel.export(_result(), "geojson", _obs()))["type"] == "FeatureCollection"
    assert json.loads(intel.export(_result(), "stix", _obs()))["type"] == "bundle"
    with pytest.raises(ValueError):
        intel.export(_result(), "csv")


def test_cli_geojson(tmp_path, capsys):
    from adsbwatch.cli import main
    csv = tmp_path / "feed.csv"
    csv.write_text("timestamp,icao,callsign,lat,lon,squawk\n"
                   "1750000000,ABC123,HIJACK1,51.5,-0.12,7500\n", encoding="utf-8")
    main(["scan", str(csv), "--format", "geojson"])
    doc = json.loads(capsys.readouterr().out)
    assert doc["type"] == "FeatureCollection"
