"""Smoke tests for ADSBWATCH. No network. Stdlib unittest."""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from adsbwatch import (
    analyze,
    parse_records,
    parse_csv,
    TOOL_NAME,
    TOOL_VERSION,
    SQUAWK_MEANINGS,
)
from adsbwatch.core import haversine_nm
from adsbwatch.cli import main, build_parser

DEMO = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "demos", "01-basic", "feed.csv",
)


class TestMeta(unittest.TestCase):
    def test_meta(self):
        self.assertEqual(TOOL_NAME, "adsbwatch")
        self.assertTrue(TOOL_VERSION)


class TestGeo(unittest.TestCase):
    def test_haversine_zero(self):
        self.assertAlmostEqual(haversine_nm(40, -73, 40, -73), 0.0, places=6)

    def test_haversine_known(self):
        # ~1 degree of latitude ~= 60 NM.
        d = haversine_nm(40.0, -73.0, 41.0, -73.0)
        self.assertTrue(59 < d < 61, d)


class TestEmergencySquawk(unittest.TestCase):
    def test_detects_7700(self):
        rows = [
            {"timestamp": "1", "icao": "abc123", "callsign": "TST1",
             "lat": "1", "lon": "1", "altitude": "1000", "squawk": "7700"},
        ]
        res = analyze(parse_records(rows))
        kinds = [a.kind for a in res.anomalies]
        self.assertIn("emergency_squawk", kinds)
        em = next(a for a in res.anomalies if a.kind == "emergency_squawk")
        self.assertEqual(em.severity, "critical")
        self.assertIn("7700", SQUAWK_MEANINGS["7700"] and em.detail)

    def test_7600_is_high(self):
        rows = [{"timestamp": "1", "icao": "x", "squawk": "7600"}]
        res = analyze(parse_records(rows))
        em = next(a for a in res.anomalies if a.kind == "emergency_squawk")
        self.assertEqual(em.severity, "high")


class TestCallsignSpoof(unittest.TestCase):
    def test_multiple_callsigns_flagged(self):
        rows = [
            {"timestamp": "1", "icao": "dead01", "callsign": "UAL1"},
            {"timestamp": "2", "icao": "dead01", "callsign": "DAL9"},
        ]
        res = analyze(parse_records(rows))
        self.assertTrue(any(a.kind == "callsign_spoof" for a in res.anomalies))

    def test_malformed_callsign(self):
        rows = [{"timestamp": "1", "icao": "dead02", "callsign": "BAD CALL!"}]
        res = analyze(parse_records(rows))
        self.assertTrue(any(
            a.kind == "callsign_spoof" and "Malformed" in a.detail
            for a in res.anomalies))

    def test_clean_single_callsign(self):
        rows = [
            {"timestamp": "1", "icao": "clean1", "callsign": "SWA88"},
            {"timestamp": "2", "icao": "clean1", "callsign": "SWA88"},
        ]
        res = analyze(parse_records(rows))
        self.assertFalse(any(a.kind == "callsign_spoof" for a in res.anomalies))


class TestLoiter(unittest.TestCase):
    def test_detects_orbit(self):
        import math
        rows = []
        cx, cy = 38.5, -77.0
        r = 0.01  # ~0.6 NM radius circle
        for i in range(12):
            ang = 2 * math.pi * i / 12
            rows.append({
                "timestamp": str(i * 30),
                "icao": "orbit1",
                "callsign": "N1",
                "lat": str(cx + r * math.cos(ang)),
                "lon": str(cy + r * math.sin(ang)),
                "altitude": "4500",
            })
        res = analyze(parse_records(rows))
        self.assertTrue(any(a.kind == "loiter" for a in res.anomalies))

    def test_transit_not_loiter(self):
        rows = []
        for i in range(12):
            rows.append({
                "timestamp": str(i * 30),
                "icao": "trans1",
                "callsign": "N2",
                "lat": str(35.0 + i * 0.1),
                "lon": str(-80.0 - i * 0.1),
                "altitude": "38000",
            })
        res = analyze(parse_records(rows))
        self.assertFalse(any(a.kind == "loiter" for a in res.anomalies))


class TestParseAndCli(unittest.TestCase):
    def test_parse_demo_csv(self):
        obs = parse_csv(DEMO)
        self.assertGreater(len(obs), 0)
        icaos = {o.icao for o in obs}
        self.assertIn("A1B2C3", icaos)

    def test_iso_timestamp(self):
        rows = [{"timestamp": "2024-06-08T12:00:00Z", "icao": "iso1",
                 "squawk": "1200"}]
        obs = parse_records(rows)
        self.assertEqual(len(obs), 1)
        self.assertGreater(obs[0].timestamp, 0)

    def test_missing_icao_raises(self):
        with self.assertRaises(ValueError):
            parse_records([{"timestamp": "1", "callsign": "X"}])

    def test_cli_demo_returns_2(self):
        # Demo file contains anomalies -> exit code 2.
        rc = main(["scan", DEMO, "--format", "json"])
        self.assertEqual(rc, 2)

    def test_cli_no_command_returns_1(self):
        self.assertEqual(main([]), 1)

    def test_cli_bad_path_returns_1(self):
        rc = main(["scan", os.path.join(os.sep, "no", "such", "feed.csv")])
        self.assertEqual(rc, 1)

    def test_parser_builds(self):
        self.assertIsNotNone(build_parser())


if __name__ == "__main__":
    unittest.main()
