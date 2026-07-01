"""CLI tests for the new subcommands (airspace, patterns) and formats (kml, cot)."""

from __future__ import annotations

import json
import os

from adsbwatch.cli import main

HERE = os.path.dirname(os.path.abspath(__file__))
FEED = os.path.join(HERE, "..", "demos", "01-basic", "feed.csv")
ZONES = os.path.join(HERE, "..", "demos", "01-basic", "zones.json")


def test_airspace_finds_incursion(capsys):
    rc = main(["airspace", FEED, "--zones", ZONES])
    out = capsys.readouterr().out
    assert rc == 2                      # incursion(s) found
    assert "airspace_incursion" in out


def test_airspace_json(capsys):
    rc = main(["airspace", FEED, "--zones", ZONES, "--format", "json"])
    out = capsys.readouterr().out
    data = json.loads(out)
    assert data["anomaly_count"] >= 1
    assert rc == 2


def test_airspace_missing_zones_file(capsys):
    rc = main(["airspace", FEED, "--zones", os.path.join(HERE, "nope.json")])
    err = capsys.readouterr().err
    assert rc == 1
    assert "failed to read zones" in err


def test_patterns_table(capsys):
    rc = main(["patterns", FEED])
    out = capsys.readouterr().out
    assert rc == 0
    assert "pattern-of-life" in out


def test_patterns_poi_json(capsys):
    rc = main(["patterns", FEED, "--poi", "40.65,-73.77", "--min-visits", "1",
               "--format", "json"])
    out = capsys.readouterr().out
    data = json.loads(out)
    assert "recurring_visits" in data
    assert rc == 0


def test_patterns_bad_poi(capsys):
    rc = main(["patterns", FEED, "--poi", "garbage"])
    err = capsys.readouterr().err
    assert rc == 1
    assert "--poi must be" in err


def test_scan_kml_format(capsys):
    rc = main(["scan", FEED, "--format", "kml"])
    out = capsys.readouterr().out
    assert out.startswith("<?xml")
    assert "<kml" in out
    assert rc == 2


def test_scan_cot_format(capsys):
    rc = main(["scan", FEED, "--format", "cot"])
    out = capsys.readouterr().out
    assert "<events>" in out
    assert 'type="a-u-A"' in out


def test_scan_with_zones_adds_incursion(capsys):
    rc = main(["scan", FEED, "--zones", ZONES, "--format", "json"])
    out = capsys.readouterr().out
    data = json.loads(out)
    kinds = {a["kind"] for a in data["anomalies"]}
    assert "airspace_incursion" in kinds
    assert rc == 2
