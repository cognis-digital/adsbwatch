"""Tests for the impossible-kinematics (position-spoof) detector.

A single ICAO whose consecutive geolocated reports imply a ground speed beyond
any real aircraft is flagged as a likely spoofed / injected position or a cloned
transponder. No network. Stdlib only.
"""

from __future__ import annotations

import pytest

from adsbwatch.core import (
    Observation,
    analyze,
    _detect_impossible_kinematics,
    DEFAULT_MAX_GROUND_SPEED_KT,
)


def _by_icao(obs):
    d = {}
    for o in obs:
        d.setdefault(o.icao, []).append(o)
    return d


# --- positive detections -----------------------------------------------------
def test_teleport_flagged():
    # NYC -> London in 60s: physically impossible.
    obs = [Observation(timestamp=0, icao="SPOOF", callsign="GHOST", lat=40.64, lon=-73.78),
           Observation(timestamp=60, icao="SPOOF", callsign="GHOST", lat=51.5, lon=-0.12)]
    a = next(a for a in analyze(obs).anomalies if a.kind == "impossible_kinematics")
    assert a.severity == "high"
    assert a.icao == "SPOOF"
    assert a.evidence["implied_speed_kt"] > DEFAULT_MAX_GROUND_SPEED_KT


def test_same_timestamp_different_position_is_infinite_speed():
    obs = [Observation(timestamp=100, icao="J", lat=10.0, lon=10.0),
           Observation(timestamp=100, icao="J", lat=20.0, lon=20.0)]
    a = next(a for a in analyze(obs).anomalies if a.kind == "impossible_kinematics")
    # infinite speed serialises as None with an "inf" marker in the detail text
    assert a.evidence["implied_speed_kt"] is None
    assert "inf" in a.detail


def test_evidence_records_from_to_and_distance():
    obs = [Observation(timestamp=0, icao="K", lat=0.0, lon=0.0),
           Observation(timestamp=1, icao="K", lat=0.0, lon=10.0)]
    a = next(a for a in analyze(obs).anomalies if a.kind == "impossible_kinematics")
    assert a.evidence["from"] == [0.0, 0.0]
    assert a.evidence["to"] == [0.0, 10.0]
    assert a.evidence["distance_nm"] > 0
    assert a.evidence["dt_sec"] == 1


def test_one_finding_per_aircraft():
    # three impossible jumps in a row -> still a single anomaly for that ICAO
    obs = [Observation(timestamp=i, icao="M", lat=(i * 40) % 80, lon=(i * 40) % 160)
           for i in range(4)]
    ks = [a for a in analyze(obs).anomalies if a.kind == "impossible_kinematics"]
    assert len(ks) == 1


# --- negatives (no false positives) -----------------------------------------
def test_normal_cruise_not_flagged():
    # ~0.5 deg over 10 minutes ~ real airliner speed
    obs = [Observation(timestamp=0, icao="OK", lat=40.0, lon=-74.0),
           Observation(timestamp=600, icao="OK", lat=40.5, lon=-74.5)]
    assert not any(a.kind == "impossible_kinematics" for a in analyze(obs).anomalies)


def test_stationary_same_point_not_flagged():
    obs = [Observation(timestamp=0, icao="S", lat=40.0, lon=-74.0),
           Observation(timestamp=0, icao="S", lat=40.0, lon=-74.0)]  # identical, dt=0
    assert not any(a.kind == "impossible_kinematics" for a in analyze(obs).anomalies)


def test_rows_without_coords_ignored():
    obs = [Observation(timestamp=0, icao="N", lat=None, lon=None),
           Observation(timestamp=1, icao="N", lat=None, lon=None)]
    assert not any(a.kind == "impossible_kinematics" for a in analyze(obs).anomalies)


def test_single_report_cannot_flag():
    obs = [Observation(timestamp=0, icao="P", lat=40.0, lon=-74.0)]
    assert not any(a.kind == "impossible_kinematics" for a in analyze(obs).anomalies)


def test_out_of_order_timestamps_are_sorted_first():
    # same two points, but supplied newest-first; sorting means dt>0, real speed
    obs = [Observation(timestamp=600, icao="Q", lat=40.5, lon=-74.5),
           Observation(timestamp=0, icao="Q", lat=40.0, lon=-74.0)]
    assert not any(a.kind == "impossible_kinematics" for a in analyze(obs).anomalies)


# --- threshold controls ------------------------------------------------------
def test_disabled_with_zero_threshold():
    obs = [Observation(timestamp=0, icao="Z", lat=40.64, lon=-73.78),
           Observation(timestamp=60, icao="Z", lat=51.5, lon=-0.12)]
    assert not any(a.kind == "impossible_kinematics"
                   for a in analyze(obs, kinematics_max_speed_kt=0).anomalies)


def test_disabled_with_negative_threshold():
    obs = [Observation(timestamp=0, icao="Z", lat=40.64, lon=-73.78),
           Observation(timestamp=60, icao="Z", lat=51.5, lon=-0.12)]
    assert not any(a.kind == "impossible_kinematics"
                   for a in analyze(obs, kinematics_max_speed_kt=-1).anomalies)


def test_lower_threshold_catches_fast_but_real_speed():
    # ~450 kt cruise; a paranoid 300-kt ceiling should catch it
    obs = [Observation(timestamp=0, icao="F", lat=40.0, lon=-74.0),
           Observation(timestamp=600, icao="F", lat=41.2, lon=-74.0)]  # ~72 NM / 10 min = 432 kt
    hits = _detect_impossible_kinematics(_by_icao(obs), max_speed_kt=300.0)
    assert hits and hits[0].kind == "impossible_kinematics"


def test_direct_detector_returns_list():
    assert _detect_impossible_kinematics({}, max_speed_kt=100.0) == []
