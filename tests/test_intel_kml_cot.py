"""Tests for the KML and CoT (Cursor-on-Target) intel exporters.

Both must be well-formed XML and must carry the anomaly picture. CoT must stay
neutral (unknown affiliation) — situational awareness, never a hostile
targeting designation.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET

from adsbwatch.core import Observation, analyze, Anomaly, AnalysisResult
from adsbwatch.intel import to_kml, to_cot, export


def _result_with_geo():
    obs = [Observation(timestamp=0, icao="A1", callsign="AAL1", lat=40.0, lon=-74.0,
                       squawk="7700")]
    return analyze(obs), obs


def test_kml_is_well_formed_xml():
    result, obs = _result_with_geo()
    root = ET.fromstring(to_kml(result, obs))
    assert root.tag.endswith("kml")


def test_kml_has_placemark_with_coords():
    result, obs = _result_with_geo()
    kml = to_kml(result, obs)
    assert "<Placemark>" in kml
    assert "-74.0,40.0,0" in kml


def test_kml_escapes_special_chars():
    a = Anomaly(kind="loiter", severity="medium", icao="Z<1>", callsign="A&B",
                detail="x < y & z", timestamp=0,
                evidence={"center": [10.0, 20.0]})
    kml = to_kml(AnalysisResult(1, 1, [a]))
    assert "&lt;" in kml and "&amp;" in kml
    ET.fromstring(kml)   # still parses


def test_cot_is_well_formed_xml():
    result, obs = _result_with_geo()
    root = ET.fromstring(to_cot(result, obs))
    assert root.tag == "events"


def test_cot_event_is_unknown_affiliation():
    result, obs = _result_with_geo()
    root = ET.fromstring(to_cot(result, obs))
    ev = root.find("event")
    assert ev is not None
    # a-u-A = atom, UNKNOWN affiliation, Air. Never 'a-h-*' (hostile).
    assert ev.get("type") == "a-u-A"
    assert "-h-" not in ev.get("type")


def test_cot_carries_remark_and_point():
    result, obs = _result_with_geo()
    root = ET.fromstring(to_cot(result, obs))
    ev = root.find("event")
    pt = ev.find("point")
    assert pt.get("lat") == "40.0" and pt.get("lon") == "-74.0"
    remark = ev.find("detail/remarks").text
    assert "emergency_squawk" in remark


def test_exporters_registered():
    result, obs = _result_with_geo()
    assert export(result, "kml", obs).startswith("<?xml")
    assert export(result, "cot", obs).startswith("<?xml")


def test_no_geo_anomaly_produces_empty_but_valid():
    a = Anomaly(kind="callsign_spoof", severity="high", icao="X", callsign="Y",
                detail="d", timestamp=0, evidence={})
    kml = to_kml(AnalysisResult(0, 0, [a]))    # no coords -> no placemark
    cot = to_cot(AnalysisResult(0, 0, [a]))
    ET.fromstring(kml)
    ET.fromstring(cot)
    assert "<Placemark>" not in kml
