"""Scenario 10 - disconnected enclaves: sneakernet the feed cache.

On a connected sensor you refresh the OpenSky cache; to work inside an air gap
you carry that cache across on removable media. adsbwatch's datafeeds layer tars
the cache flat (`snapshot_export`) and re-hydrates it into any cache dir on the
far side (`snapshot_import`), name-independent. This demo does a full export ->
import round-trip between two temp cache dirs - offline, stdlib only.
"""
import json
import os
import tempfile

from _common import rule, sub, FEEDS_CACHE


def main() -> None:
    from adsbwatch import datafeeds

    rule("AIR-GAP SNAPSHOT  -  export the cache, carry it, re-import it")

    src = tempfile.mkdtemp(prefix="adsbwatch-connected-")
    dst = tempfile.mkdtemp(prefix="adsbwatch-airgap-")

    # 1) On the 'connected' side: seed a cache from the committed fixture.
    os.environ["COGNIS_FEEDS_CACHE"] = src
    data_path, meta_path = datafeeds._paths("opensky-states")
    fixture = os.path.join(FEEDS_CACHE, "opensky-states.data")
    with open(fixture, "rb") as fh:
        payload = fh.read()
    data_path.write_bytes(payload)
    meta_path.write_text(json.dumps({
        "feed": "opensky-states", "url": "opensky", "fetched_at": 1.0,
        "bytes": len(payload), "format": "json"}), encoding="utf-8")

    sub("Connected side: export the feed cache to an archive")
    archive = os.path.join(src, "feeds.tar.gz")
    n = datafeeds.snapshot_export(archive)
    print(f"  exported {n} feed(s) -> {archive} ({os.path.getsize(archive)} bytes)")

    # 2) On the 'air-gapped' side: fresh cache dir, import the archive.
    os.environ["COGNIS_FEEDS_CACHE"] = dst
    sub("Air-gapped side: import into a DIFFERENT cache dir")
    imported = datafeeds.snapshot_import(archive)
    print(f"  imported {imported} feed(s) into {dst}")

    # 3) Prove the far side can now serve the feed offline and analyse it.
    from adsbwatch import feeds
    from adsbwatch.core import analyze
    obs = feeds.fetch_observations(offline=True)
    result = analyze(obs)
    sub("Far side runs the engine over the carried snapshot")
    print(f"  {len(obs)} aircraft ingested; {len(result.anomalies)} anomaly/anomalies")
    assert imported >= 1 and obs, "snapshot round-trip must preserve the feed"
    print("  the feed source never touched the air-gapped box - only the cache did.")


if __name__ == "__main__":
    main()
