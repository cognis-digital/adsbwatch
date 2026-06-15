"""Decision-support layer: triage, correlation, advisory recommendations, and the
hard human-in-the-loop scope guard (no effector/weapon actions, ever)."""

from __future__ import annotations

import json
import os

from adsbwatch import decision
from adsbwatch.core import Anomaly, analyze, parse_csv
from adsbwatch.cli import main

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FEED = os.path.join(ROOT, "demos", "01-basic", "feed.csv")
SENSORS = os.path.join(ROOT, "demos", "01-basic", "sensors.csv")


def _anoms():
    return analyze(parse_csv(FEED)).anomalies


# --- triage ------------------------------------------------------------------
def test_triage_ranks_by_severity():
    ranked = decision.triage(_anoms())
    assert ranked
    prios = [r["priority"] for r in ranked]
    assert prios == sorted(prios, reverse=True)         # highest priority first
    assert ranked[0]["severity"] in ("critical", "high")


def test_triage_dedupes_repeats():
    a = Anomaly("loiter", "medium", "ABC", "X", "loiter", 1000.0)
    b = Anomaly("loiter", "medium", "ABC", "X", "loiter", 1010.0)  # within window
    out = decision.triage([a, b], dedupe_window_s=60)
    assert len(out) == 1 and out[0]["count"] == 2 and out[0]["confidence"] == "medium"


# --- correlation -------------------------------------------------------------
def test_correlate_with_local_sensors():
    evs = decision.load_sensor_events(SENSORS)
    assert evs
    a = Anomaly("loiter", "medium", "100200", "N551LW", "loiter", 1700000020.0)
    corr = decision.correlate([a], evs, window_s=60)[0]
    assert corr["corroborated"] and corr["correlated_events"]
    assert corr["evidence_count"] >= 2


# --- recommendations are ADVISORY only (the boundary) ------------------------
def test_recommendations_are_advisory_only():
    for kind in ("emergency_squawk", "callsign_spoof", "loiter", "unknown_kind"):
        recs = decision.recommend(kind, "high")
        assert recs
        for r in recs:
            assert r.action in decision._ALLOWED_ACTIONS


def test_scope_guard_no_effector_actions_anywhere():
    """Hard line: nothing in the layer may command a weapon/effector or act autonomously."""
    report = decision.assess(analyze(parse_csv(FEED)), decision.load_sensor_events(SENSORS))
    assert report["human_authorization_required"] is True
    # scan the ACTIONABLE content (incidents + recommendations) - not the scope banner,
    # which legitimately names these terms to declare the boundary.
    blob = json.dumps(report["incidents"]).lower()
    for forbidden in ("engage", "open fire", " jam", "intercept", "launch",
                      "strike", "destroy", "neutralize", "kill", "shoot", "weapon"):
        assert forbidden not in blob, f"forbidden effector term leaked: {forbidden}"
    # every recommended action is on the advisory allow-list
    for inc in report["incidents"]:
        for r in inc["recommendations"]:
            assert r["action"] in decision._ALLOWED_ACTIONS


def test_assess_report_shape():
    report = decision.assess(analyze(parse_csv(FEED)))
    assert report["incident_count"] == len(report["incidents"]) >= 1
    inc = report["incidents"][0]
    assert {"icao", "kind", "severity", "priority", "recommendations", "correlation"} <= set(inc)


# --- CLI ---------------------------------------------------------------------
def test_cli_assess_json(capsys):
    rc = main(["assess", FEED, "--sensors", SENSORS, "--format", "json"])
    assert rc == 2                                       # incidents present -> non-zero gate
    data = json.loads(capsys.readouterr().out)
    assert data["human_authorization_required"] is True and data["incident_count"] >= 1


def test_cli_assess_table_shows_scope_and_human_gate(capsys):
    main(["assess", FEED])
    out = capsys.readouterr().out
    assert "human authorization required" in out.lower()
    assert "operator decides" in out.lower()
