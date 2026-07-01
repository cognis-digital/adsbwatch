"""Edge cases for the decision-support layer: loaders, triage, correlation, the
advisory scope guard, and the empty-input paths.
"""

from __future__ import annotations

import json

import pytest

from adsbwatch import decision
from adsbwatch.core import Anomaly


def _anom(kind="loiter", sev="medium", icao="ABC", ts=1000.0):
    return Anomaly(kind, sev, icao, "N1", f"{kind} detail", ts)


# --- load_sensor_events: the fixed empty/whitespace bug ----------------------
def test_load_empty_string_yields_no_events():
    assert decision.load_sensor_events("") == []


def test_load_whitespace_only_yields_no_events():
    assert decision.load_sensor_events("   \n  ") == []


def test_load_none_yields_no_events():
    assert decision.load_sensor_events(None) == []


def test_load_json_list_inline():
    evs = decision.load_sensor_events(
        '[{"timestamp": 5, "source": "cam", "type": "motion", "detail": "x"}]')
    assert len(evs) == 1 and evs[0].source == "cam"


def test_load_json_dict_with_events_key():
    evs = decision.load_sensor_events('{"events": [{"timestamp": 1, "source": "rf"}]}')
    assert len(evs) == 1 and evs[0].source == "rf"


def test_load_json_detail_with_comma_not_misparsed_as_csv():
    evs = decision.load_sensor_events(
        '[{"timestamp": 1, "source": "cam", "detail": "a, b, c"}]')
    assert len(evs) == 1 and evs[0].detail == "a, b, c"


def test_load_csv_inline():
    evs = decision.load_sensor_events(
        "timestamp,source,type,detail\n10,cam,motion,hi\n20,rf,burst,ho")
    assert len(evs) == 2 and evs[1].type == "burst"


def test_load_csv_file(tmp_path):
    p = tmp_path / "s.csv"
    p.write_text("timestamp,source,type,detail\n1,cam,motion,x\n", encoding="utf-8")
    evs = decision.load_sensor_events(str(p))
    assert len(evs) == 1


def test_load_json_file(tmp_path):
    p = tmp_path / "s.json"
    p.write_text('[{"timestamp": 1, "source": "cam"}]', encoding="utf-8")
    evs = decision.load_sensor_events(str(p))
    assert len(evs) == 1


def test_load_missing_file_raises():
    with pytest.raises((FileNotFoundError, OSError)):
        decision.load_sensor_events("/no/such/sensors.csv")


def test_load_malformed_json_raises_valueerror():
    with pytest.raises(ValueError):
        decision.load_sensor_events("[{bad json")


def test_load_alias_fields():
    evs = decision.load_sensor_events(
        '[{"ts": 3, "sensor": "gate", "event": "denied", "description": "d"}]')
    assert evs[0].timestamp == 3 and evs[0].source == "gate" and evs[0].type == "denied"


def test_load_skips_unparseable_rows():
    evs = decision.load_sensor_events(
        '[{"timestamp": "notnum", "source": "x"}, {"timestamp": 2, "source": "ok"}]')
    assert len(evs) == 1 and evs[0].source == "ok"


# --- triage ------------------------------------------------------------------
def test_triage_empty():
    assert decision.triage([]) == []


def test_triage_dedupe_within_window():
    out = decision.triage([_anom(ts=1000), _anom(ts=1010)], dedupe_window_s=60)
    assert len(out) == 1 and out[0]["count"] == 2


def test_triage_no_dedupe_outside_window():
    out = decision.triage([_anom(ts=1000), _anom(ts=5000)], dedupe_window_s=60)
    assert len(out) == 2


def test_triage_confidence_escalates_with_repeats():
    reps = [_anom(ts=1000 + i * 5) for i in range(3)]
    out = decision.triage(reps, dedupe_window_s=60)
    assert out[0]["confidence"] == "high"


def test_triage_sorted_by_priority_desc():
    anoms = [_anom("loiter", "medium", "A", 1), _anom("emergency_squawk", "critical", "B", 2)]
    out = decision.triage(anoms)
    assert out[0]["severity"] == "critical"


# --- correlate ---------------------------------------------------------------
def test_correlate_no_events():
    out = decision.correlate([_anom()], [], window_s=60)
    assert out[0]["corroborated"] is False and out[0]["confidence"] == "low"


def test_correlate_hits_within_window():
    ev = decision.SensorEvent(timestamp=1030, source="cam", type="motion")
    out = decision.correlate([_anom(ts=1000)], [ev], window_s=60)
    assert out[0]["corroborated"] and out[0]["evidence_count"] == 2


def test_correlate_ignores_out_of_window():
    ev = decision.SensorEvent(timestamp=99999, source="cam")
    out = decision.correlate([_anom(ts=1000)], [ev], window_s=60)
    assert out[0]["correlated_events"] == []


def test_correlate_high_confidence_two_plus():
    evs = [decision.SensorEvent(timestamp=1010, source="a"),
           decision.SensorEvent(timestamp=1020, source="b")]
    out = decision.correlate([_anom(ts=1000)], evs, window_s=60)
    assert out[0]["confidence"] == "high"


# --- recommend (advisory only) ----------------------------------------------
@pytest.mark.parametrize("kind", ["emergency_squawk", "callsign_spoof", "loiter",
                                  "impossible_kinematics", "totally_unknown"])
def test_recommend_actions_always_allowed(kind):
    for r in decision.recommend(kind, "high"):
        assert r.action in decision._ALLOWED_ACTIONS


def test_recommend_high_severity_adds_escalation():
    recs = decision.recommend("loiter", "critical")
    assert any(r.action == "escalate_authority" for r in recs)


def test_kinematics_playbook_present():
    recs = decision.recommend("impossible_kinematics", "high")
    actions = {r.action for r in recs}
    assert "request_identification" in actions and "preserve_evidence" in actions


def test_assert_advisory_rejects_effector_action():
    bad = [decision.Recommendation("engage_target", "fire", "immediate")]
    with pytest.raises(ValueError):
        decision._assert_advisory(bad)


# --- assess ------------------------------------------------------------------
def test_assess_empty_result():
    from adsbwatch.core import AnalysisResult
    rep = decision.assess(AnalysisResult(0, 0, []))
    assert rep["incident_count"] == 0 and rep["human_authorization_required"] is True


def test_assess_accepts_bare_anomaly_list():
    rep = decision.assess([_anom("emergency_squawk", "critical", "X", 1)])
    assert rep["incident_count"] == 1


def test_assess_no_effector_terms_in_incidents():
    rep = decision.assess([_anom("emergency_squawk", "critical")])
    blob = json.dumps(rep["incidents"]).lower()
    for bad in ("engage", "open fire", "intercept", "launch", "strike",
                "destroy", "neutralize", "weapon"):
        assert bad not in blob


def test_assess_incident_shape():
    rep = decision.assess([_anom("loiter", "medium")])
    inc = rep["incidents"][0]
    assert {"icao", "kind", "severity", "priority", "recommendations", "correlation"} <= set(inc)


def test_sensor_event_to_dict():
    ev = decision.SensorEvent(timestamp=1, source="cam", type="motion")
    assert ev.to_dict()["source"] == "cam"
