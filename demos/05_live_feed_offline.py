"""Scenario 5 - edge / air-gap operators: live ADS-B, served offline.

adsbwatch can pull live ADS-B state vectors from the OpenSky Network, cache them
to disk, and re-serve that snapshot OFFLINE on disconnected / edge / air-gapped
gear. This demo points the feed cache at the committed OpenSky fixture and runs
the *exact same* ingest + anomaly engine with NO network access - proving the
disconnected workflow end to end.
"""
import os

from _common import rule, sub, FEEDS_CACHE


def main() -> None:
    # Point the data-feed cache at the committed offline fixture BEFORE importing
    # the feeds layer reads it. This is the air-gap path: cache only, no network.
    os.environ["COGNIS_FEEDS_CACHE"] = FEEDS_CACHE

    from adsbwatch import feeds
    from adsbwatch.core import analyze

    rule("LIVE FEED, OFFLINE  -  air-gap ADS-B over a cached snapshot")
    print(f"\nFeed cache (offline fixture): {FEEDS_CACHE}")

    sub("Wired feed(s)")
    for f in feeds.list_feeds():
        print(f"  {f['id']}  ({f.get('domain', '-')})  {f['name']}")
        print(f"    src: {f['url']}")

    sub("Ingest the cached OpenSky snapshot (offline=True, no network)")
    obs = feeds.fetch_observations(offline=True)
    print(f"  ingested {len(obs)} aircraft from the cached snapshot")
    emerg = [o for o in obs if o.squawk in ("7500", "7600", "7700")]
    if emerg:
        print(f"  emergency squawks present in the snapshot: {len(emerg)}")
        for o in emerg:
            print(f"    {o.icao} {o.callsign or '-':8} squawk {o.squawk}")

    sub("Run the SAME anomaly engine over the live-style ingest")
    result = analyze(obs)
    print(f"  {result.observations} report(s) / {result.aircraft} aircraft -> "
          f"{len(result.anomalies)} anomaly/anomalies")
    for a in result.anomalies:
        print(f"    {a.severity:<8} {a.kind:<16} {a.icao} {a.callsign or '-'}: {a.detail}")

    sub("Why it matters")
    print("  On a connected sensor you'd run `adsbwatch feeds update opensky-states`")
    print("  then carry the cache across the air gap. On the isolated box the tool")
    print("  keeps hunting squawks / spoofing / loiter over the last snapshot - the")
    print("  feed source changes, the analysis engine does not.")


if __name__ == "__main__":
    main()
