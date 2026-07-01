"""Edge-case and error-path tests for the core parsing + geo + detectors.

These push malformed input, boundary values and the less-travelled branches of
`adsbwatch.core` that the smoke tests do not cover. No network. Stdlib only.
"""

from __future__ import annotations

import math

import pytest

from adsbwatch.core import (
    Observation,
    Anomaly,
    AnalysisResult,
    analyze,
    parse_records,
    parse_csv,
    haversine_nm,
    _bearing,
    _ang_diff,
    _parse_timestamp,
    _parse_float,
    SQUAWK_MEANINGS,
)


# --- timestamp parsing -------------------------------------------------------
def test_parse_timestamp_epoch_float():
    assert _parse_timestamp("1717848000") == 1717848000.0
    assert _parse_timestamp("  1717848000.5 ") == 1717848000.5


def test_parse_timestamp_iso_with_z():
    ts = _parse_timestamp("2024-06-08T12:00:00Z")
    assert ts > 0


def test_parse_timestamp_iso_naive_treated_utc():
    naive = _parse_timestamp("2024-06-08T12:00:00")
    aware = _parse_timestamp("2024-06-08T12:00:00Z")
    assert naive == aware


def test_parse_timestamp_empty_raises():
    with pytest.raises(ValueError):
        _parse_timestamp("")
    with pytest.raises(ValueError):
        _parse_timestamp("   ")


def test_parse_timestamp_garbage_raises():
    with pytest.raises(ValueError):
        _parse_timestamp("not-a-time")


# --- float parsing -----------------------------------------------------------
def test_parse_float_blank_is_none():
    assert _parse_float("") is None
    assert _parse_float("   ") is None
    assert _parse_float(None) is None


def test_parse_float_bad_is_none_not_raise():
    assert _parse_float("abc") is None


def test_parse_float_valid():
    assert _parse_float(" -12.5 ") == -12.5


# --- record parsing ----------------------------------------------------------
def test_parse_records_missing_icao_raises_with_row_index():
    with pytest.raises(ValueError) as ei:
        parse_records([{"timestamp": "1", "icao": "ok"},
                       {"timestamp": "2", "callsign": "X"}])
    assert "row 1" in str(ei.value)


def test_parse_records_bad_timestamp_raises_with_row_index():
    with pytest.raises(ValueError) as ei:
        parse_records([{"timestamp": "nope", "icao": "ok"}])
    assert "row 0" in str(ei.value)


def test_parse_records_alias_columns():
    # hex/flit/time/latitude/longitude/alt aliases
    obs = parse_records([{"time": "1", "hex": "abc", "flight": "csn",
                          "latitude": "10", "longitude": "20", "alt": "500"}])
    assert obs[0].icao == "ABC"
    assert obs[0].callsign == "CSN"
    assert obs[0].lat == 10 and obs[0].lon == 20 and obs[0].altitude == 500


def test_parse_records_icao_uppercased_and_stripped():
    obs = parse_records([{"timestamp": "1", "icao": "  abcd12  "}])
    assert obs[0].icao == "ABCD12"


def test_parse_records_case_insensitive_headers():
    obs = parse_records([{"TimeStamp": "1", "ICAO": "abc", "CallSign": "x"}])
    assert obs[0].icao == "ABC" and obs[0].callsign == "X"


def test_parse_records_empty_iterable():
    assert parse_records([]) == []


# --- CSV parsing -------------------------------------------------------------
def test_parse_csv_no_header_raises(tmp_path):
    p = tmp_path / "empty.csv"
    p.write_text("", encoding="utf-8")
    with pytest.raises(ValueError):
        parse_csv(str(p))


def test_parse_csv_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        parse_csv(str(tmp_path / "nope.csv"))


def test_parse_csv_roundtrip(tmp_path):
    p = tmp_path / "f.csv"
    p.write_text("timestamp,icao,callsign,lat,lon,squawk\n"
                 "1,ABC,UAL1,40,-73,1200\n", encoding="utf-8")
    obs = parse_csv(str(p))
    assert len(obs) == 1 and obs[0].icao == "ABC"


# --- geo helpers -------------------------------------------------------------
def test_haversine_symmetric():
    a = haversine_nm(40, -73, 41, -72)
    b = haversine_nm(41, -72, 40, -73)
    assert abs(a - b) < 1e-9


def test_haversine_antipodal_half_circumference():
    # roughly half the Earth's circumference in NM
    d = haversine_nm(0, 0, 0, 180)
    assert 10700 < d < 10900, d


def test_bearing_cardinal_directions():
    assert abs(_bearing(0, 0, 1, 0) - 0.0) < 1.0        # due north
    assert abs(_bearing(0, 0, 0, 1) - 90.0) < 1.0       # due east


def test_ang_diff_wraps():
    assert abs(_ang_diff(350, 10) - 20.0) < 1e-9
    assert abs(_ang_diff(10, 350) + 20.0) < 1e-9


# --- analyze on empty / trivial input ---------------------------------------
def test_analyze_empty():
    r = analyze([])
    assert r.observations == 0 and r.aircraft == 0 and r.anomalies == []


def test_analyze_single_clean_obs():
    r = analyze([Observation(timestamp=1, icao="OK", callsign="UAL1",
                             lat=40, lon=-73, squawk="1200")])
    assert r.anomalies == []


def test_analyze_result_to_dict_shape():
    r = analyze([Observation(timestamp=1, icao="X", squawk="7700")])
    d = r.to_dict()
    assert d["anomaly_count"] == len(d["anomalies"]) == 1
    assert set(d) == {"observations", "aircraft", "anomaly_count", "anomalies"}


# --- emergency squawks -------------------------------------------------------
@pytest.mark.parametrize("code,sev", [("7500", "critical"), ("7600", "high"),
                                      ("7700", "critical")])
def test_emergency_squawk_severity(code, sev):
    r = analyze([Observation(timestamp=1, icao="E", squawk=code)])
    em = next(a for a in r.anomalies if a.kind == "emergency_squawk")
    assert em.severity == sev
    assert SQUAWK_MEANINGS[code] in em.detail


def test_emergency_squawk_deduped_per_code():
    obs = [Observation(timestamp=t, icao="E", squawk="7700") for t in range(5)]
    r = analyze(obs)
    ems = [a for a in r.anomalies if a.kind == "emergency_squawk"]
    assert len(ems) == 1  # one per distinct code, not per report


def test_normal_squawk_1200_not_flagged():
    r = analyze([Observation(timestamp=1, icao="E", squawk="1200")])
    assert not any(a.kind == "emergency_squawk" for a in r.anomalies)


# --- callsign anomalies ------------------------------------------------------
def test_callsign_spoof_multiple_identities():
    obs = [Observation(timestamp=1, icao="D", callsign="UAL1"),
           Observation(timestamp=2, icao="D", callsign="DAL9")]
    a = next(a for a in analyze(obs).anomalies if a.kind == "callsign_spoof")
    assert set(a.evidence["callsigns"]) == {"UAL1", "DAL9"}


def test_callsign_blank_only_no_flag():
    obs = [Observation(timestamp=1, icao="D", callsign=""),
           Observation(timestamp=2, icao="D", callsign="")]
    assert not any(a.kind == "callsign_spoof" for a in analyze(obs).anomalies)


def test_callsign_malformed_flagged():
    obs = [Observation(timestamp=1, icao="D", callsign="BAD CALL!")]
    a = next(a for a in analyze(obs).anomalies
             if a.kind == "callsign_spoof" and "Malformed" in a.detail)
    assert "BAD CALL!" in a.evidence["malformed"]


def test_callsign_too_long_malformed():
    obs = [Observation(timestamp=1, icao="D", callsign="TOOLONG12345")]
    assert any(a.kind == "callsign_spoof" for a in analyze(obs).anomalies)


# --- loiter ------------------------------------------------------------------
def _orbit(icao, n=12, r=0.01, cx=38.5, cy=-77.0):
    return [Observation(timestamp=i * 30, icao=icao, callsign="N1",
                        lat=cx + r * math.cos(2 * math.pi * i / n),
                        lon=cy + r * math.sin(2 * math.pi * i / n), altitude=4500)
            for i in range(n)]


def test_loiter_detected():
    assert any(a.kind == "loiter" for a in analyze(_orbit("O1")).anomalies)


def test_loiter_below_min_points_not_flagged():
    obs = _orbit("O2", n=4)
    assert not any(a.kind == "loiter" for a in
                   analyze(obs, loiter_min_points=6).anomalies)


def test_loiter_wide_spread_not_flagged():
    # points on a large circle exceed the radius gate
    obs = _orbit("O3", r=0.5)  # ~30 NM radius
    assert not any(a.kind == "loiter" for a in
                   analyze(obs, loiter_radius_nm=5.0).anomalies)


def test_loiter_ignores_rows_without_coords():
    obs = [Observation(timestamp=i, icao="O4", callsign="N1") for i in range(12)]
    assert not any(a.kind == "loiter" for a in analyze(obs).anomalies)


def test_loiter_evidence_has_center_and_turn():
    a = next(a for a in analyze(_orbit("O5")).anomalies if a.kind == "loiter")
    assert "center" in a.evidence and "cumulative_turn_deg" in a.evidence


# --- severity ordering -------------------------------------------------------
def test_anomalies_sorted_critical_first():
    obs = [Observation(timestamp=1, icao="A", squawk="7700")]      # critical
    obs += [Observation(timestamp=1, icao="B", callsign="UAL1"),
            Observation(timestamp=2, icao="B", callsign="DAL9")]   # high
    sevs = [a.severity for a in analyze(obs).anomalies]
    rank = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    assert sevs == sorted(sevs, key=lambda s: rank[s])


def test_observation_and_anomaly_to_dict():
    o = Observation(timestamp=1, icao="X")
    assert o.to_dict()["icao"] == "X"
    an = Anomaly("loiter", "medium", "X", "N1", "d", 1.0)
    assert an.to_dict()["kind"] == "loiter"
