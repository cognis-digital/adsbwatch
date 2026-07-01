"""Offline tests for the datafeeds cache/catalog layer.

Uses a per-test temporary COGNIS_FEEDS_CACHE and never fetches over the network:
we write cache files by hand, then exercise get(offline=True), freshness, and the
air-gap snapshot export/import round-trip.
"""

from __future__ import annotations

import json
import os
import tempfile
import time
import unittest


class TempCache:
    """Context manager that isolates COGNIS_FEEDS_CACHE and reloads module state."""

    def __enter__(self):
        self._old = os.environ.get("COGNIS_FEEDS_CACHE")
        self._dir = tempfile.mkdtemp(prefix="adsbwatch-df-")
        os.environ["COGNIS_FEEDS_CACHE"] = self._dir
        return self._dir

    def __exit__(self, *exc):
        if self._old is None:
            os.environ.pop("COGNIS_FEEDS_CACHE", None)
        else:
            os.environ["COGNIS_FEEDS_CACHE"] = self._old


def _df():
    from adsbwatch import datafeeds
    return datafeeds


def _write_cache(df, feed_id, payload, *, fmt="json", age_h=0.0):
    data_path, meta_path = df._paths(feed_id)
    data_path.write_bytes(json.dumps(payload).encode()
                          if fmt == "json" else str(payload).encode())
    meta_path.write_text(json.dumps({
        "feed": feed_id, "url": "x", "fetched_at": time.time() - age_h * 3600.0,
        "bytes": 1, "format": fmt}), encoding="utf-8")
    return data_path


class TestCatalog(unittest.TestCase):
    def test_catalog_has_opensky(self):
        ids = {f["id"] for f in _df().list_feeds()}
        self.assertIn("opensky-states", ids)

    def test_list_feeds_domain_filter(self):
        df = _df()
        all_feeds = df.list_feeds()
        # filtering by a domain returns a subset
        if all_feeds:
            dom = all_feeds[0].get("domain")
            if dom:
                subset = df.list_feeds(domain=dom)
                self.assertTrue(all(f.get("domain") == dom for f in subset))


class TestOfflineGet(unittest.TestCase):
    def test_get_offline_serves_cache(self):
        with TempCache():
            df = _df()
            _write_cache(df, "opensky-states", {"states": [], "time": 1})
            data = df.get("opensky-states", offline=True)
            self.assertEqual(data["time"], 1)

    def test_get_offline_missing_raises(self):
        with TempCache():
            df = _df()
            with self.assertRaises(FileNotFoundError):
                df.get("opensky-states", offline=True)

    def test_get_unknown_feed_raises_keyerror(self):
        with TempCache():
            df = _df()
            with self.assertRaises(KeyError):
                df.update("not-a-real-feed")

    def test_cached_age_hours(self):
        with TempCache():
            df = _df()
            self.assertIsNone(df.cached_age_hours("opensky-states"))
            _write_cache(df, "opensky-states", {"states": []}, age_h=2.0)
            age = df.cached_age_hours("opensky-states")
            self.assertTrue(1.9 < age < 2.1, age)


class TestSnapshotRoundTrip(unittest.TestCase):
    def test_export_import_roundtrip(self):
        with TempCache() as d1:
            df = _df()
            _write_cache(df, "opensky-states", {"states": [], "time": 42})
            archive = os.path.join(d1, "snap.tar.gz")
            n = df.snapshot_export(archive)
            self.assertGreaterEqual(n, 1)
            # import into a *different* cache dir -> name-independent
            with TempCache():
                df2 = _df()
                imported = df2.snapshot_import(archive)
                self.assertGreaterEqual(imported, 1)
                data = df2.get("opensky-states", offline=True)
                self.assertEqual(data["time"], 42)


if __name__ == "__main__":
    unittest.main()
