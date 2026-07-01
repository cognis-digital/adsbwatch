"""Edge cases for the GeoJSON / STIX 2.1 intel export."""

from __future__ import annotations

import json

import pytest

from adsbwatch.core import Observation, Anomaly, AnalysisResult, analyze
from adsbwatch import intel


def _result(anoms, obs=2, ac=2):
    return AnalysisResult(observations=obs, aircraft=ac, anomalies=anoms)


def _emergency():
    return Anomaly("emergency_squawk", "critical", "ABC123", "HIJACK1",
                   "Squawk 7700", 1750000000, evidence={"squawk": "7700"})


def _loiter():
    return Anomaly("loiter", "medium", "DEF456", "SCOUT", "orbit", 1750000060,
                   evidence={"center": [52.0, -1.0], "radius_nm": 1.2})


# --- empty result ------------------------------------------------------------
def test_geojson_empty_result():
    doc = json.loads(intel.to_geojson(_result([], 0, 0)))
    assert doc["type"] == "FeatureCollection" and doc["features"] == []


def test_stix_empty_result_is_valid_bundle():
    doc = json.loads(intel.to_stix(_result([], 0, 0)))
    assert doc["type"] == "bundle"
    report = next(o for o in doc["objects"] if o["type"] == "report")
    assert report["object_refs"]  # falls back to self-ref, never empty


# --- coordinate sourcing -----------------------------------------------------
def test_geojson_uses_evidence_center_for_loiter():
    doc = json.loads(intel.to_geojson(_result([_loiter()]), observations=[]))
    f = doc["features"][0]
    assert f["geometry"]["coordinates"] == [-1.0, 52.0]  # [lon, lat]


def test_geojson_uses_observation_position_fallback():
    obs = [Observation(timestamp=1, icao="ABC123", lat=51.5, lon=-0.12)]
    doc = json.loads(intel.to_geojson(_result([_emergency()]), obs))
    assert doc["features"][0]["geometry"]["coordinates"] == [-0.12, 51.5]


def test_geojson_skips_anomaly_with_no_known_position():
    a = Anomaly("callsign_spoof", "high", "Z", "GHOST", "no pos", 1, evidence={})
    doc = json.loads(intel.to_geojson(_result([a]), observations=[]))
    assert doc["features"] == []


def test_geojson_last_position_wins():
    obs = [Observation(timestamp=1, icao="ABC123", lat=10.0, lon=10.0),
           Observation(timestamp=2, icao="ABC123", lat=20.0, lon=20.0)]
    doc = json.loads(intel.to_geojson(_result([_emergency()]), obs))
    assert doc["features"][0]["geometry"]["coordinates"] == [20.0, 20.0]


def test_geojson_properties_include_evidence():
    doc = json.loads(intel.to_geojson(_result([_loiter()]), observations=[]))
    props = doc["features"][0]["properties"]
    assert props["kind"] == "loiter" and props["radius_nm"] == 1.2


# --- STIX structure ----------------------------------------------------------
def test_stix_object_ids_prefixed_and_spec21():
    doc = json.loads(intel.to_stix(_result([_emergency(), _loiter()]),
                                   [Observation(timestamp=1, icao="ABC123", lat=51.5, lon=-0.12)]))
    for o in doc["objects"]:
        if o["type"] != "bundle":
            assert o["id"].startswith(o["type"] + "--")
            assert o.get("spec_version") == "2.1"


def test_stix_report_refs_all_resolve():
    doc = json.loads(intel.to_stix(_result([_emergency(), _loiter()]),
                                   [Observation(timestamp=1, icao="ABC123", lat=51.5, lon=-0.12)]))
    ids = {o["id"] for o in doc["objects"]}
    report = next(o for o in doc["objects"] if o["type"] == "report")
    assert all(ref in ids for ref in report["object_refs"])


def test_stix_note_labels_carry_kind_and_severity():
    doc = json.loads(intel.to_stix(_result([_emergency()]),
                                   [Observation(timestamp=1, icao="ABC123", lat=51.5, lon=-0.12)]))
    note = next(o for o in doc["objects"] if o["type"] == "note")
    assert "emergency_squawk" in note["labels"] and "critical" in note["labels"]


def test_stix_anomaly_without_location_still_emits_observed_data():
    a = Anomaly("callsign_spoof", "high", "Z", "GHOST", "no pos", 1, evidence={})
    doc = json.loads(intel.to_stix(_result([a]), observations=[]))
    types = {o["type"] for o in doc["objects"]}
    assert "observed-data" in types and "note" in types
    assert "location" not in types  # no coords -> no location SDO


# --- determinism + dispatch --------------------------------------------------
def test_exports_deterministic():
    obs = [Observation(timestamp=1, icao="ABC123", lat=51.5, lon=-0.12)]
    r = _result([_emergency(), _loiter()])
    assert intel.to_stix(r, obs) == intel.to_stix(_result([_emergency(), _loiter()]), obs)
    assert intel.to_geojson(r, obs) == intel.to_geojson(_result([_emergency(), _loiter()]), obs)


def test_export_dispatch_case_insensitive():
    assert json.loads(intel.export(_result([_loiter()]), "GEOJSON"))["type"] == "FeatureCollection"
    assert json.loads(intel.export(_result([_loiter()]), "Stix"))["type"] == "bundle"


def test_export_unknown_format_raises():
    with pytest.raises(ValueError):
        intel.export(_result([]), "csv")


def test_iso_timestamp_bad_epoch_uses_fallback():
    # a wildly out-of-range epoch must not crash the exporter
    a = Anomaly("loiter", "medium", "X", "N", "d", 1e300,
                evidence={"center": [1.0, 2.0]})
    doc = json.loads(intel.to_geojson(_result([a]), observations=[]))
    assert doc["features"][0]["properties"]["timestamp"]  # some ISO string


def test_kinematics_anomaly_exports_via_observation_position():
    obs = analyze([Observation(timestamp=0, icao="SP", lat=40.64, lon=-73.78),
                   Observation(timestamp=60, icao="SP", lat=51.5, lon=-0.12)])
    doc = json.loads(intel.to_geojson(
        obs, [Observation(timestamp=60, icao="SP", lat=51.5, lon=-0.12)]))
    assert any(f["properties"]["kind"] == "impossible_kinematics"
               for f in doc["features"])
