"""Hardening tests: edge cases, bad input, parameter validation, empty feeds."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from adsbwatch.core import (
    analyze,
    parse_records,
    parse_csv,
    haversine_nm,
    scan,
    to_json,
)
from adsbwatch.cli import main


# ---------------------------------------------------------------------------
# Edge cases: empty and minimal input
# ---------------------------------------------------------------------------

class TestEmptyInput(unittest.TestCase):
    def test_analyze_empty_observations(self):
        """analyze([]) must return a result with zero counts, not raise."""
        result = analyze([])
        self.assertEqual(result.observations, 0)
        self.assertEqual(result.aircraft, 0)
        self.assertEqual(result.anomalies, [])

    def test_parse_records_empty_iterable(self):
        """parse_records on an empty iterable returns an empty list."""
        obs = parse_records(iter([]))
        self.assertEqual(obs, [])

    def test_parse_csv_header_only(self):
        """A CSV with only a header row (no data) returns [] without error."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", delete=False, encoding="utf-8"
        ) as f:
            f.write("timestamp,icao,callsign,lat,lon,altitude,squawk\n")
            tmp = f.name
        try:
            obs = parse_csv(tmp)
            self.assertEqual(obs, [])
        finally:
            os.unlink(tmp)

    def test_to_dict_empty_result(self):
        """AnalysisResult.to_dict() works when anomalies list is empty."""
        result = analyze([])
        d = result.to_dict()
        self.assertEqual(d["observations"], 0)
        self.assertEqual(d["anomaly_count"], 0)
        self.assertEqual(d["anomalies"], [])


# ---------------------------------------------------------------------------
# Haversine domain-clamp (prevents ValueError from asin(>1))
# ---------------------------------------------------------------------------

class TestHaversineEdge(unittest.TestCase):
    def test_identical_points_returns_zero(self):
        """Identical lat/lon must return 0.0, not raise a domain error."""
        d = haversine_nm(51.5074, -0.1278, 51.5074, -0.1278)
        self.assertAlmostEqual(d, 0.0, places=6)

    def test_antipodal_points_finite(self):
        """Antipodal points (max distance) must return a finite positive number."""
        d = haversine_nm(90.0, 0.0, -90.0, 0.0)
        self.assertGreater(d, 0)
        self.assertTrue(d < 10_900)  # half Earth circumference ~10,800 NM


# ---------------------------------------------------------------------------
# analyze() parameter validation
# ---------------------------------------------------------------------------

class TestAnalyzeParameterValidation(unittest.TestCase):
    def test_loiter_min_points_zero_raises(self):
        with self.assertRaises(ValueError) as ctx:
            analyze([], loiter_min_points=0)
        self.assertIn("loiter_min_points", str(ctx.exception))

    def test_loiter_min_points_one_raises(self):
        with self.assertRaises(ValueError):
            analyze([], loiter_min_points=1)

    def test_loiter_radius_zero_raises(self):
        with self.assertRaises(ValueError) as ctx:
            analyze([], loiter_radius_nm=0.0)
        self.assertIn("loiter_radius_nm", str(ctx.exception))

    def test_loiter_radius_negative_raises(self):
        with self.assertRaises(ValueError):
            analyze([], loiter_radius_nm=-1.5)

    def test_loiter_turn_zero_raises(self):
        with self.assertRaises(ValueError) as ctx:
            analyze([], loiter_min_turn_deg=0.0)
        self.assertIn("loiter_min_turn_deg", str(ctx.exception))


# ---------------------------------------------------------------------------
# CLI parameter validation (bad loiter flags -> exit 1)
# ---------------------------------------------------------------------------

class TestCliParameterValidation(unittest.TestCase):
    def _make_minimal_csv(self) -> str:
        f = tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", delete=False, encoding="utf-8"
        )
        f.write("timestamp,icao,callsign,lat,lon,altitude,squawk\n")
        f.close()
        return f.name

    def test_loiter_points_one_returns_1(self):
        tmp = self._make_minimal_csv()
        try:
            rc = main(["scan", tmp, "--loiter-points", "1"])
            self.assertEqual(rc, 1)
        finally:
            os.unlink(tmp)

    def test_loiter_radius_zero_returns_1(self):
        tmp = self._make_minimal_csv()
        try:
            rc = main(["scan", tmp, "--loiter-radius", "0"])
            self.assertEqual(rc, 1)
        finally:
            os.unlink(tmp)

    def test_loiter_turn_negative_returns_1(self):
        tmp = self._make_minimal_csv()
        try:
            rc = main(["scan", tmp, "--loiter-turn", "-10"])
            self.assertEqual(rc, 1)
        finally:
            os.unlink(tmp)


# ---------------------------------------------------------------------------
# parse_csv missing-file and malformed-file error handling
# ---------------------------------------------------------------------------

class TestParseCsvErrors(unittest.TestCase):
    def test_missing_file_raises_file_not_found(self):
        with self.assertRaises(FileNotFoundError):
            parse_csv("/no/such/path/feed.csv")

    def test_empty_path_raises_value_error(self):
        with self.assertRaises(ValueError) as ctx:
            parse_csv("")
        self.assertIn("path", str(ctx.exception).lower())

    def test_bad_timestamp_raises_value_error(self):
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", delete=False, encoding="utf-8"
        ) as f:
            f.write("timestamp,icao\n")
            f.write("not-a-time,AABBCC\n")
            tmp = f.name
        try:
            with self.assertRaises(ValueError) as ctx:
                parse_csv(tmp)
            self.assertIn("timestamp", str(ctx.exception))
        finally:
            os.unlink(tmp)

    def test_missing_icao_raises_value_error(self):
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", delete=False, encoding="utf-8"
        ) as f:
            f.write("timestamp,callsign\n")
            f.write("1234567890,SWA1\n")
            tmp = f.name
        try:
            with self.assertRaises(ValueError) as ctx:
                parse_csv(tmp)
            self.assertIn("icao", str(ctx.exception))
        finally:
            os.unlink(tmp)


# ---------------------------------------------------------------------------
# scan() and to_json() convenience wrappers
# ---------------------------------------------------------------------------

class TestConvenienceWrappers(unittest.TestCase):
    def test_scan_header_only_csv(self):
        """scan() on a header-only CSV returns a clean empty result."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", delete=False, encoding="utf-8"
        ) as f:
            f.write("timestamp,icao,callsign,lat,lon,altitude,squawk\n")
            tmp = f.name
        try:
            result = scan(tmp)
            self.assertEqual(result.observations, 0)
            self.assertEqual(result.anomalies, [])
        finally:
            os.unlink(tmp)

    def test_to_json_returns_valid_json(self):
        """to_json() must return a string that parses as valid JSON."""
        import json
        result = analyze([])
        raw = to_json(result)
        parsed = json.loads(raw)
        self.assertIn("observations", parsed)
        self.assertIn("anomaly_count", parsed)
        self.assertEqual(parsed["anomalies"], [])


if __name__ == "__main__":
    unittest.main()
