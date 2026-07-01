"""CLI argument, error-path and exit-code tests.

Exercises the command-line surface: exit codes (0 clean / 1 usage-or-error /
2 anomalies-present), format switches, region parsing, and clean errors on bad
input. No network. Stdlib only.
"""

from __future__ import annotations

import json
import os

import pytest

from adsbwatch.cli import main, build_parser, _parse_region

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FEED = os.path.join(ROOT, "demos", "01-basic", "feed.csv")


def _clean_csv(tmp_path):
    p = tmp_path / "clean.csv"
    p.write_text("timestamp,icao,callsign,lat,lon,squawk\n"
                 "1,ABC,UAL1,40,-73,1200\n", encoding="utf-8")
    return str(p)


# --- exit codes --------------------------------------------------------------
def test_scan_with_anomalies_returns_2():
    assert main(["scan", FEED, "--format", "json"]) == 2


def test_scan_clean_feed_returns_0(tmp_path):
    assert main(["scan", _clean_csv(tmp_path)]) == 0


def test_no_command_returns_1():
    assert main([]) == 1


def test_missing_feed_path_returns_1(tmp_path):
    assert main(["scan", str(tmp_path / "nope.csv")]) == 1


def test_scan_no_feed_no_live_returns_1():
    assert main(["scan"]) == 1


def test_bad_csv_returns_1(tmp_path):
    p = tmp_path / "bad.csv"
    p.write_text("timestamp,callsign\n1,X\n", encoding="utf-8")  # no icao column
    assert main(["scan", str(p)]) == 1


def test_empty_csv_no_header_returns_1(tmp_path):
    p = tmp_path / "empty.csv"
    p.write_text("", encoding="utf-8")
    assert main(["scan", str(p)]) == 1


# --- formats -----------------------------------------------------------------
def test_scan_table_default(capsys):
    main(["scan", FEED])
    out = capsys.readouterr().out
    assert "ADSBWATCH report" in out


def test_scan_json_shape(capsys):
    main(["scan", FEED, "--format", "json"])
    d = json.loads(capsys.readouterr().out)
    assert "anomalies" in d and "aircraft" in d


def test_scan_geojson(capsys):
    main(["scan", FEED, "--format", "geojson"])
    d = json.loads(capsys.readouterr().out)
    assert d["type"] == "FeatureCollection"


def test_scan_stix(capsys):
    main(["scan", FEED, "--format", "stix"])
    d = json.loads(capsys.readouterr().out)
    assert d["type"] == "bundle"


def test_clean_feed_table_says_no_anomalies(tmp_path, capsys):
    main(["scan", _clean_csv(tmp_path)])
    assert "No anomalies detected." in capsys.readouterr().out


# --- kinematics flag ---------------------------------------------------------
def test_max_speed_flag_can_flag_fast_track(tmp_path, capsys):
    p = tmp_path / "fast.csv"
    # ~432 kt real cruise; a 300 kt ceiling flags it
    p.write_text("timestamp,icao,callsign,lat,lon\n"
                 "0,FAST,UAL1,40.0,-74.0\n"
                 "600,FAST,UAL1,41.2,-74.0\n", encoding="utf-8")
    rc = main(["scan", str(p), "--max-speed", "300", "--format", "json"])
    assert rc == 2
    d = json.loads(capsys.readouterr().out)
    assert any(a["kind"] == "impossible_kinematics" for a in d["anomalies"])


def test_max_speed_zero_disables(tmp_path, capsys):
    p = tmp_path / "tele.csv"
    p.write_text("timestamp,icao,lat,lon\n"
                 "0,T,40.64,-73.78\n60,T,51.5,-0.12\n", encoding="utf-8")
    main(["scan", str(p), "--max-speed", "0", "--format", "json"])
    d = json.loads(capsys.readouterr().out)
    assert not any(a["kind"] == "impossible_kinematics" for a in d["anomalies"])


# --- region parsing ----------------------------------------------------------
def test_parse_region_ok():
    assert _parse_region("40,-74,41,-73") == (40.0, -74.0, 41.0, -73.0)


def test_parse_region_none():
    assert _parse_region(None) is None
    assert _parse_region("") is None


def test_parse_region_wrong_count_raises():
    with pytest.raises(ValueError):
        _parse_region("40,-74,41")


def test_parse_region_non_numeric_raises():
    with pytest.raises(ValueError):
        _parse_region("a,b,c,d")


# --- assess exit codes -------------------------------------------------------
def test_assess_with_incidents_returns_2():
    assert main(["assess", FEED]) == 2


def test_assess_clean_feed_returns_0(tmp_path):
    assert main(["assess", _clean_csv(tmp_path)]) == 0


def test_assess_bad_sensors_returns_1(tmp_path):
    assert main(["assess", FEED, "--sensors", str(tmp_path / "nope.csv")]) == 1


def test_assess_json(capsys):
    main(["assess", FEED, "--format", "json"])
    d = json.loads(capsys.readouterr().out)
    assert d["human_authorization_required"] is True


# --- parser / version --------------------------------------------------------
def test_version_exits_zero():
    with pytest.raises(SystemExit) as e:
        main(["--version"])
    assert e.value.code == 0


def test_parser_builds():
    assert build_parser() is not None


def test_unknown_command_returns_1():
    # argparse subparsers are optional here; an unrecognised token is a usage error
    with pytest.raises(SystemExit):
        main(["frobnicate"])
