"""Edge cases for the live-feed / OpenSky ingest layer — OFFLINE ONLY.

Points COGNIS_FEEDS_CACHE at the committed trimmed OpenSky fixture and always
reads offline=True, so nothing ever touches the network.
"""

from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

FIXTURE_CACHE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "fixtures", "feeds_cache")


def setUpModule():
    os.environ["COGNIS_FEEDS_CACHE"] = FIXTURE_CACHE


from adsbwatch import feeds
from adsbwatch.core import Observation, analyze


class TestFeedGuards(unittest.TestCase):
    def test_reject_unknown_feed_update(self):
        with self.assertRaises(ValueError):
            feeds.update("cisa-kev")

    def test_reject_unknown_feed_get_raw(self):
        with self.assertRaises(ValueError):
            feeds.get_raw("epss", offline=True)

    def test_list_feeds_only_opensky(self):
        self.assertEqual([f["id"] for f in feeds.list_feeds()], ["opensky-states"])


class TestStatesToObservations(unittest.TestCase):
    def test_empty_payload(self):
        self.assertEqual(feeds.states_to_observations({}), [])
        self.assertEqual(feeds.states_to_observations({"states": None}), [])
        self.assertEqual(feeds.states_to_observations(None), [])

    def test_row_without_icao_dropped(self):
        payload = {"time": 1, "states": [
            ["", "X", "US", 1, 1, -73.0, 40.0, 3000, False, 0, 0, 0, None, 3000, "1200", False, 0],
        ]}
        self.assertEqual(feeds.states_to_observations(payload), [])

    def test_short_row_skipped(self):
        payload = {"time": 1, "states": [["abc", "X"]]}  # far fewer than needed cols
        self.assertEqual(feeds.states_to_observations(payload), [])

    def test_icao_uppercased_callsign_trimmed(self):
        payload = {"time": 1, "states": [
            ["abc123", "  hi ", "US", 1, 1, -73.0, 40.0, 3000, False, 0, 0, 0,
             None, 3000, "7700", False, 0],
        ]}
        obs = feeds.states_to_observations(payload)
        self.assertEqual(obs[0].icao, "ABC123")
        self.assertEqual(obs[0].callsign, "HI")

    def test_geo_altitude_fallback_when_baro_null(self):
        payload = {"time": 1, "states": [
            ["abc", "X", "US", 1, 1, -73.0, 40.0, None, False, 0, 0, 0,
             None, 3048.0, "1200", False, 0],  # baro null, geo=3048m -> 10000 ft
        ]}
        obs = feeds.states_to_observations(payload)
        self.assertTrue(9990 < obs[0].altitude < 10010, obs[0].altitude)

    def test_region_clip_filters(self):
        payload = {"time": 1, "states": [
            ["us1", "A", "US", 1, 1, -73.0, 40.5, 3000, False, 0, 0, 0, None, 3000, "1200", False, 0],
            ["eu1", "B", "FR", 1, 1, 2.4, 46.7, 3000, False, 0, 0, 0, None, 3000, "1000", False, 0],
        ]}
        obs = feeds.states_to_observations(payload, region=(40.0, -74.0, 41.0, -73.0))
        icaos = {o.icao for o in obs}
        self.assertIn("US1", icaos)
        self.assertNotIn("EU1", icaos)


class TestOfflineFixtureIngest(unittest.TestCase):
    def test_get_raw_offline_has_states(self):
        payload = feeds.get_raw("opensky-states", offline=True)
        self.assertGreaterEqual(len(payload["states"]), 3)

    def test_fetch_observations_offline(self):
        obs = feeds.fetch_observations(offline=True)
        self.assertTrue(all(isinstance(o, Observation) for o in obs))
        self.assertIn("A1B2C3", {o.icao for o in obs})

    def test_hijack_altitude_converted_to_feet(self):
        obs = feeds.fetch_observations(offline=True)
        hij = next(o for o in obs if o.icao == "A1B2C3")
        self.assertTrue(11990 < hij.altitude < 12010, hij.altitude)

    def test_null_position_row_kept_but_no_coords(self):
        obs = feeds.fetch_observations(offline=True)
        dead = next((o for o in obs if o.icao == "DEADBE"), None)
        self.assertIsNotNone(dead)
        self.assertIsNone(dead.lat)

    def test_offline_ingest_drives_engine(self):
        result = analyze(feeds.fetch_observations(offline=True))
        em = next(a for a in result.anomalies if a.kind == "emergency_squawk")
        self.assertEqual(em.icao, "A1B2C3")
        self.assertEqual(em.severity, "critical")

    def test_region_clip_offline(self):
        obs = feeds.fetch_observations(offline=True, region=(40.0, -74.0, 41.0, -73.0))
        icaos = {o.icao for o in obs}
        self.assertIn("A1B2C3", icaos)
        self.assertNotIn("39DE4F", icaos)


class TestOfflineMissingCache(unittest.TestCase):
    def test_offline_no_cache_raises(self):
        # point at an empty dir -> offline + nothing cached -> FileNotFoundError
        import tempfile
        old = os.environ.get("COGNIS_FEEDS_CACHE")
        with tempfile.TemporaryDirectory() as d:
            os.environ["COGNIS_FEEDS_CACHE"] = d
            try:
                with self.assertRaises(FileNotFoundError):
                    feeds.get_raw("opensky-states", offline=True)
            finally:
                os.environ["COGNIS_FEEDS_CACHE"] = old or FIXTURE_CACHE


if __name__ == "__main__":
    unittest.main()
