"""Scenario 9 - sector watch: clip live ingest to a bounding box.

An edge sensor rarely cares about the whole planet. adsbwatch can clip the live
(or cached) OpenSky ingest to a lat/lon bounding box, so you only analyse the
airspace over your sector. This demo runs the cached snapshot twice - global,
then clipped to a box around the NYC contact - offline.
"""
import os

from _common import rule, sub, FEEDS_CACHE


def main() -> None:
    os.environ["COGNIS_FEEDS_CACHE"] = FEEDS_CACHE
    from adsbwatch import feeds

    rule("REGION CLIP  -  analyse only the airspace over your sector")

    sub("Global ingest (whole cached snapshot)")
    all_obs = feeds.fetch_observations(offline=True)
    print(f"  {len(all_obs)} aircraft: " + ", ".join(sorted(o.icao for o in all_obs)))

    sub("Clipped to a box around the NYC contact (40..41 N, -74..-73 W)")
    box = (40.0, -74.0, 41.0, -73.0)
    clipped = feeds.fetch_observations(offline=True, region=box)
    print(f"  bounding box: {box}")
    print(f"  {len(clipped)} aircraft in box: "
          + ", ".join(sorted(o.icao for o in clipped)))

    sub("Why clip at the edge")
    print("  Clipping happens during ingest, before analysis, so an air-gapped")
    print("  sensor spends its cycles only on the airspace it is responsible for -")
    print("  the France contact in the snapshot is dropped before the engine runs.")
    assert len(clipped) < len(all_obs)


if __name__ == "__main__":
    main()
