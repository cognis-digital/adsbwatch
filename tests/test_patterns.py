"""Tests for pattern-of-life analytics (offline, stdlib)."""

from __future__ import annotations

from adsbwatch.core import Observation
from adsbwatch.patterns import (
    aircraft_profiles,
    recurring_visits,
    summarize,
)


def _stream():
    obs = []
    # AC1: two separated visits near a POI at (40, -74)
    obs += [Observation(timestamp=t, icao="AC1", callsign="X", lat=40.0, lon=-74.0, altitude=3000)
            for t in (0, 30, 60)]
    obs += [Observation(timestamp=t, icao="AC1", callsign="X", lat=40.0, lon=-74.0, altitude=3200)
            for t in (10000, 10030)]
    # AC2: one pass far away
    obs += [Observation(timestamp=t, icao="AC2", callsign="Y", lat=10.0, lon=10.0, altitude=8000)
            for t in (0, 30)]
    return obs


def test_profiles_basic():
    profs = aircraft_profiles(_stream())
    by = {p.icao: p for p in profs}
    assert by["AC1"].reports == 5
    assert by["AC1"].callsigns == ["X"]
    assert by["AC1"].alt_min_ft == 3000
    assert by["AC1"].alt_max_ft == 3200
    assert by["AC1"].dwell_s == 10030


def test_profiles_bbox_and_track():
    profs = aircraft_profiles([
        Observation(timestamp=0, icao="T", lat=40.0, lon=-74.0),
        Observation(timestamp=10, icao="T", lat=40.0, lon=-73.0),
    ])
    p = profs[0]
    assert p.bbox == [40.0, -74.0, 40.0, -73.0]
    assert p.track_nm > 0


def test_profiles_sorted_by_reports():
    profs = aircraft_profiles(_stream())
    assert profs[0].icao == "AC1"   # 5 reports > AC2's 2


def test_recurring_visits_two_windows():
    rv = recurring_visits(_stream(), 40.0, -74.0, radius_nm=5, gap_s=3600, min_visits=2)
    assert len(rv) == 1
    assert rv[0]["icao"] == "AC1"
    assert rv[0]["visits"] == 2


def test_recurring_visits_min_visits_filters():
    rv = recurring_visits(_stream(), 40.0, -74.0, radius_nm=5, gap_s=3600, min_visits=3)
    assert rv == []


def test_recurring_visits_none_near():
    rv = recurring_visits(_stream(), 0.0, 0.0, radius_nm=1, min_visits=1)
    assert rv == []


def test_summarize_shape():
    s = summarize(_stream())
    assert s["observations"] == 7
    assert s["aircraft"] == 2
    assert s["window"]["start"] == 0
    assert s["window"]["end"] == 10030
    assert len(s["profiles"]) == 2


def test_summarize_empty():
    s = summarize([])
    assert s["observations"] == 0
    assert s["window"]["start"] is None


def test_to_dict_roundtrip():
    p = aircraft_profiles(_stream())[0]
    d = p.to_dict()
    assert d["icao"] == "AC1"
    assert "dwell_s" in d and "track_nm" in d
