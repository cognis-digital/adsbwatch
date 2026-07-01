"""Tests for offline restricted-airspace / NOTAM incursion detection."""

from __future__ import annotations

import json

import pytest

from adsbwatch.core import Observation
from adsbwatch.airspace import (
    Zone,
    load_zones,
    detect_incursions,
    _point_in_polygon,
)


# --- geometry ----------------------------------------------------------------
def test_circle_contains():
    z = Zone(id="c", shape="circle", center=[40.0, -74.0], radius_nm=10)
    assert z.contains(40.0, -74.0)
    assert not z.contains(41.0, -74.0)   # ~60 NM north


def test_polygon_contains_and_outside():
    verts = [[0, 0], [0, 10], [10, 10], [10, 0]]
    assert _point_in_polygon(5, 5, verts)
    assert not _point_in_polygon(15, 5, verts)
    assert not _point_in_polygon(-1, 5, verts)


def test_polygon_vertex_is_inside():
    verts = [[0, 0], [0, 10], [10, 10], [10, 0]]
    assert _point_in_polygon(0, 0, verts)


def test_degenerate_polygon_is_empty():
    assert not _point_in_polygon(1, 1, [[0, 0], [1, 1]])


# --- altitude band and time window ------------------------------------------
def test_alt_band():
    z = Zone(id="a", center=[0, 0], radius_nm=5, alt_floor_ft=1000, alt_ceiling_ft=5000)
    assert z.alt_in_band(3000)
    assert not z.alt_in_band(500)
    assert not z.alt_in_band(9000)
    assert z.alt_in_band(None)   # unknown altitude fails safe -> considered in band


def test_active_window():
    z = Zone(id="w", center=[0, 0], radius_nm=5, active_from=100, active_to=200)
    assert z.active_at(150)
    assert not z.active_at(50)
    assert not z.active_at(300)


# --- detection ---------------------------------------------------------------
def test_incursion_detected():
    zones = [Zone(id="R1", name="range", center=[40.0, -74.0], radius_nm=10, severity="high")]
    obs = [Observation(timestamp=0, icao="AC", callsign="X", lat=40.0, lon=-74.0, altitude=3000)]
    hits = detect_incursions(obs, zones)
    assert len(hits) == 1
    assert hits[0].kind == "airspace_incursion"
    assert hits[0].evidence["zone_id"] == "R1"


def test_one_finding_per_aircraft_zone():
    zones = [Zone(id="R1", center=[40.0, -74.0], radius_nm=10)]
    obs = [Observation(timestamp=t, icao="AC", lat=40.0, lon=-74.0, altitude=3000)
           for t in range(5)]
    assert len(detect_incursions(obs, zones)) == 1


def test_outside_zone_not_flagged():
    zones = [Zone(id="R1", center=[40.0, -74.0], radius_nm=1)]
    obs = [Observation(timestamp=0, icao="AC", lat=45.0, lon=-70.0, altitude=3000)]
    assert detect_incursions(obs, zones) == []


def test_below_floor_not_flagged():
    zones = [Zone(id="R1", center=[40.0, -74.0], radius_nm=10,
                  alt_floor_ft=10000, alt_ceiling_ft=20000)]
    obs = [Observation(timestamp=0, icao="AC", lat=40.0, lon=-74.0, altitude=3000)]
    assert detect_incursions(obs, zones) == []


def test_inactive_window_not_flagged():
    zones = [Zone(id="R1", center=[40.0, -74.0], radius_nm=10,
                  active_from=1000, active_to=2000)]
    obs = [Observation(timestamp=0, icao="AC", lat=40.0, lon=-74.0, altitude=3000)]
    assert detect_incursions(obs, zones) == []


def test_missing_coords_ignored():
    zones = [Zone(id="R1", center=[40.0, -74.0], radius_nm=10)]
    obs = [Observation(timestamp=0, icao="AC", lat=None, lon=None)]
    assert detect_incursions(obs, zones) == []


# --- loading -----------------------------------------------------------------
def test_load_zones_from_text_list():
    text = json.dumps([{"id": "z", "center": [1, 2], "radius_nm": 3}])
    zones = load_zones(text)
    assert len(zones) == 1 and zones[0].shape == "circle"


def test_load_zones_from_dict_wrapper():
    text = json.dumps({"zones": [{"id": "z", "vertices": [[0, 0], [0, 1], [1, 1]]}]})
    zones = load_zones(text)
    assert zones[0].shape == "polygon"


def test_load_zones_empty():
    assert load_zones("") == []
    assert load_zones(None) == []


def test_load_zones_bad_json_raises():
    with pytest.raises(ValueError):
        load_zones("[not json")


def test_load_zones_iso_window():
    text = json.dumps([{"id": "z", "center": [1, 2], "radius_nm": 3,
                        "active_from": "2024-01-01T00:00:00Z"}])
    z = load_zones(text)[0]
    assert z.active_from is not None
