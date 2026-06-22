"""Data-feed layer tests — OFFLINE ONLY.

These never hit the network: COGNIS_FEEDS_CACHE is pointed at the committed
trimmed OpenSky fixture under tests/fixtures/feeds_cache, and every read uses
offline=True so datafeeds serves from cache and never calls urllib.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

FIXTURE_CACHE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "fixtures", "feeds_cache")


def setUpModule():
    # Point the feed cache at the committed fixture BEFORE datafeeds reads the env.
    os.environ["COGNIS_FEEDS_CACHE"] = FIXTURE_CACHE


from adsbwatch import feeds
from adsbwatch.core import analyze, Observation
from adsbwatch.cli import main


class TestCatalogWiring(unittest.TestCase):
    def test_only_opensky_wired(self):
        ids = [f["id"] for f in feeds.list_feeds()]
        self.assertEqual(ids, ["opensky-states"])

    def test_relevant_feeds_constant(self):
        self.assertEqual(feeds.RELEVANT_FEEDS, ("opensky-states",))

    def test_reject_unknown_feed(self):
        with self.assertRaises(ValueError):
            feeds.get_raw("feodo-c2", offline=True)


class TestOfflineIngest(unittest.TestCase):
    def test_get_raw_offline(self):
        payload = feeds.get_raw("opensky-states", offline=True)
        self.assertIn("states", payload)
        self.assertGreaterEqual(len(payload["states"]), 3)

    def test_states_to_observations(self):
        obs = feeds.fetch_observations(offline=True)
        # 4 fixture rows, one has a null ICAO-less? all have icao; null-fields row kept.
        self.assertTrue(all(isinstance(o, Observation) for o in obs))
        icaos = {o.icao for o in obs}
        self.assertIn("A1B2C3", icaos)  # upper-cased
        # callsign trimmed + upper-cased
        hij = next(o for o in obs if o.icao == "A1B2C3")
        self.assertEqual(hij.callsign, "HIJACK1")
        self.assertEqual(hij.squawk, "7700")

    def test_altitude_converted_to_feet(self):
        obs = feeds.fetch_observations(offline=True)
        hij = next(o for o in obs if o.icao == "A1B2C3")
        # 3657.6 m -> ~12000 ft
        self.assertIsNotNone(hij.altitude)
        self.assertTrue(11990 < hij.altitude < 12010, hij.altitude)

    def test_region_clip(self):
        # Box around the NYC hijack point only.
        obs = feeds.fetch_observations(offline=True, region=(40.0, -74.0, 41.0, -73.0))
        icaos = {o.icao for o in obs}
        self.assertIn("A1B2C3", icaos)
        self.assertNotIn("39DE4F", icaos)  # France, clipped out


class TestEnrichmentEndToEnd(unittest.TestCase):
    def test_live_states_drive_anomaly_engine(self):
        # THE real enrichment: live feed -> observations -> existing analyzer
        # surfaces the 7700 emergency squawk.
        obs = feeds.fetch_observations(offline=True)
        result = analyze(obs)
        kinds = [a.kind for a in result.anomalies]
        self.assertIn("emergency_squawk", kinds)
        em = next(a for a in result.anomalies if a.kind == "emergency_squawk")
        self.assertEqual(em.icao, "A1B2C3")
        self.assertEqual(em.severity, "critical")


class TestCli(unittest.TestCase):
    def test_feeds_list(self):
        self.assertEqual(main(["feeds", "list"]), 0)

    def test_feeds_get_offline(self):
        self.assertEqual(main(["feeds", "get", "opensky-states", "--offline"]), 0)

    def test_feeds_no_subcmd_returns_1(self):
        self.assertEqual(main(["feeds"]), 1)

    def test_scan_live_offline_finds_anomaly(self):
        # scan --live --offline ingests the cached snapshot; anomalies -> rc 2.
        rc = main(["scan", "--live", "--offline", "--format", "json"])
        self.assertEqual(rc, 2)


if __name__ == "__main__":
    unittest.main()
