"""Tests for the additive detectors: squawk-change, vertical-rate, formation.

All offline, stdlib only. These detectors are default-on in ``analyze`` and only
fire on genuine signatures, so existing findings are unaffected.
"""

from __future__ import annotations

from adsbwatch.core import (
    Observation,
    analyze,
    _detect_squawk_changes,
    _detect_vertical_rate,
    _detect_formation,
    DEFAULT_MAX_VERTICAL_RATE_FPM,
)


def _by_icao(obs):
    d = {}
    for o in obs:
        d.setdefault(o.icao, []).append(o)
    return d


# --- squawk change -----------------------------------------------------------
def test_squawk_change_into_emergency_flagged():
    obs = [Observation(timestamp=0, icao="AC1", callsign="X", squawk="1200"),
           Observation(timestamp=30, icao="AC1", callsign="X", squawk="7700")]
    a = next(a for a in analyze(obs).anomalies if a.kind == "squawk_change")
    assert a.severity == "critical"
    assert a.evidence["from"] == "1200"
    assert a.evidence["to"] == "7700"


def test_squawk_change_7600_is_high():
    hits = _detect_squawk_changes(_by_icao([
        Observation(timestamp=0, icao="B", squawk="2000"),
        Observation(timestamp=10, icao="B", squawk="7600"),
    ]))
    assert hits and hits[0].severity == "high"


def test_initial_emergency_code_is_not_a_change():
    # first-ever code being emergency is the emergency_squawk detector's job,
    # not squawk_change (avoids double counting).
    obs = [Observation(timestamp=0, icao="C", squawk="7700")]
    assert not any(a.kind == "squawk_change" for a in analyze(obs).anomalies)


def test_squawk_change_once_per_code():
    obs = [Observation(timestamp=0, icao="D", squawk="1200"),
           Observation(timestamp=1, icao="D", squawk="7700"),
           Observation(timestamp=2, icao="D", squawk="7700")]
    hits = [a for a in analyze(obs).anomalies if a.kind == "squawk_change"]
    assert len(hits) == 1


def test_normal_squawk_change_not_flagged():
    obs = [Observation(timestamp=0, icao="E", squawk="1200"),
           Observation(timestamp=10, icao="E", squawk="2200")]
    assert not any(a.kind == "squawk_change" for a in analyze(obs).anomalies)


# --- vertical rate -----------------------------------------------------------
def test_vertical_rate_teleport_altitude():
    obs = [Observation(timestamp=0, icao="V", altitude=1000, lat=1, lon=1),
           Observation(timestamp=1, icao="V", altitude=90000, lat=1, lon=1)]
    a = next(a for a in analyze(obs).anomalies if a.kind == "impossible_vertical_rate")
    assert a.severity == "medium"
    assert a.evidence["delta_alt_ft"] == 89000.0


def test_vertical_rate_same_timestamp_is_infinite():
    hits = _detect_vertical_rate(_by_icao([
        Observation(timestamp=5, icao="W", altitude=1000),
        Observation(timestamp=5, icao="W", altitude=50000),
    ]), max_rate_fpm=DEFAULT_MAX_VERTICAL_RATE_FPM)
    assert hits and hits[0].evidence["rate_fpm"] is None
    assert "inf" in hits[0].detail


def test_normal_climb_not_flagged():
    # 3000 ft in 3 minutes = 1000 ft/min: normal
    obs = [Observation(timestamp=0, icao="Y", altitude=5000),
           Observation(timestamp=180, icao="Y", altitude=8000)]
    assert not any(a.kind == "impossible_vertical_rate" for a in analyze(obs).anomalies)


def test_vertical_rate_disabled_with_zero():
    obs = [Observation(timestamp=0, icao="Z", altitude=0),
           Observation(timestamp=1, icao="Z", altitude=99999)]
    assert not any(a.kind == "impossible_vertical_rate"
                   for a in analyze(obs, vertical_rate_max_fpm=0).anomalies)


def test_vertical_rate_ignores_missing_altitude():
    hits = _detect_vertical_rate(_by_icao([
        Observation(timestamp=0, icao="N", altitude=None),
        Observation(timestamp=1, icao="N", altitude=None),
    ]), max_rate_fpm=100.0)
    assert hits == []


# --- formation ---------------------------------------------------------------
def _tight_pair():
    obs = []
    for i in range(4):
        t = i * 10
        obs.append(Observation(timestamp=t, icao="LEAD", callsign="VIPER1",
                               lat=40.0 + i * 0.001, lon=-74.0, altitude=20000))
        obs.append(Observation(timestamp=t, icao="WING", callsign="VIPER2",
                               lat=40.0 + i * 0.001, lon=-74.002, altitude=20050))
    return obs


def test_formation_detected():
    a = next(a for a in analyze(_tight_pair()).anomalies if a.kind == "formation")
    assert set(a.evidence["icaos"]) == {"LEAD", "WING"}
    assert a.evidence["samples"] >= 3
    assert a.evidence["min_separation_nm"] < 1.0


def test_formation_one_finding_per_pair():
    hits = [a for a in analyze(_tight_pair()).anomalies if a.kind == "formation"]
    assert len(hits) == 1


def test_far_apart_not_formation():
    obs = [Observation(timestamp=i * 10, icao="A", lat=40.0, lon=-74.0, altitude=20000)
           for i in range(4)]
    obs += [Observation(timestamp=i * 10, icao="B", lat=41.0, lon=-72.0, altitude=20000)
            for i in range(4)]
    assert not any(a.kind == "formation" for a in analyze(obs).anomalies)


def test_formation_altitude_gap_excludes():
    obs = []
    for i in range(4):
        t = i * 10
        obs.append(Observation(timestamp=t, icao="HI", lat=40.0, lon=-74.0, altitude=35000))
        obs.append(Observation(timestamp=t, icao="LO", lat=40.0, lon=-74.001, altitude=5000))
    assert not any(a.kind == "formation" for a in analyze(obs).anomalies)


def test_formation_disabled():
    assert not any(a.kind == "formation"
                   for a in analyze(_tight_pair(), detect_formation=False).anomalies)


def test_formation_direct_empty():
    assert _detect_formation({}, radius_nm=1.0, alt_ft=500.0, min_samples=3) == []
