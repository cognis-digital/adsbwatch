"""adsbwatch feeds — live ADS-B ingestion from the OpenSky Network.

This is the real, edge/air-gap-deployable data-feed layer for adsbwatch. Instead
of only scanning a local CSV, adsbwatch can pull **live ADS-B state vectors** from
the OpenSky Network (`opensky-states` in the bundled Cognis feed catalog), cache
them to disk, and convert them straight into the `Observation` rows the anomaly
engine already consumes. The same cached snapshot re-serves **offline** so the
tool keeps working on disconnected / edge / air-gapped gear.

Only the `opensky-states` feed is wired here — it is the single catalog feed
relevant to ADS-B aircraft tracking. We never invent endpoints; the URL comes
from the bundled ``data_feeds_2026.json`` catalog.

OpenSky `states/all` row layout (index -> field) per the public API:
    0 icao24   1 callsign   2 origin_country   3 time_position
    4 last_contact   5 longitude   6 latitude   7 baro_altitude
    8 on_ground   9 velocity   10 true_track   11 vertical_rate
    12 sensors   13 geo_altitude   14 squawk   15 spi   16 position_source

Defensive / authorized-use OSINT only.
"""

from __future__ import annotations

import sys
from typing import Any, Optional

# The catalog feed id(s) this tool is allowed to consume.
RELEVANT_FEEDS = ("opensky-states",)

# OpenSky states/all column indices.
_I_ICAO = 0
_I_CALLSIGN = 1
_I_LON = 5
_I_LAT = 6
_I_BARO_ALT = 7
_I_GEO_ALT = 13
_I_SQUAWK = 14
_I_TIME = 4  # last_contact (always present); time_position (3) may be null

_M_PER_FT = 0.3048


def _datafeeds():
    """Import the co-bundled datafeeds module (kept beside this file)."""
    try:
        from . import datafeeds  # type: ignore
        return datafeeds
    except Exception:  # pragma: no cover - flat-layout / script fallback
        import datafeeds  # type: ignore
        return datafeeds


def _check_feed(feed_id: str) -> None:
    if feed_id not in RELEVANT_FEEDS:
        raise ValueError(
            f"feed {feed_id!r} is not wired into adsbwatch; "
            f"allowed: {', '.join(RELEVANT_FEEDS)}"
        )


def list_feeds() -> list[dict]:
    """Catalog entries relevant to adsbwatch (the OpenSky live ADS-B feed)."""
    df = _datafeeds()
    return [f for f in df.list_feeds() if f["id"] in RELEVANT_FEEDS]


def update(feed_id: str = "opensky-states") -> str:
    """Fetch the live feed and cache it. Returns the cache path. Online."""
    _check_feed(feed_id)
    return str(_datafeeds().update(feed_id))


def get_raw(feed_id: str = "opensky-states", *, offline: bool = False,
            max_age_hours: float = 1.0) -> Any:
    """Return the raw parsed OpenSky payload (dict), from cache or network."""
    _check_feed(feed_id)
    return _datafeeds().get(feed_id, offline=offline, max_age_hours=max_age_hours)


def _to_float(v: Any) -> Optional[float]:
    try:
        return None if v is None else float(v)
    except (TypeError, ValueError):
        return None


def states_to_observations(payload: dict, *, region: Optional[tuple] = None) -> list:
    """Convert an OpenSky `states/all` payload into adsbwatch Observation rows.

    Drops rows with no usable ICAO. Altitude is converted metres->feet so the
    rest of the engine (and CSVs) see consistent units. ``region`` optionally
    clips to a (lat_min, lon_min, lat_max, lon_max) bounding box.
    """
    try:
        from .core import Observation
    except Exception:  # pragma: no cover
        from core import Observation  # type: ignore

    out: list = []
    states = (payload or {}).get("states") or []
    snap_time = (payload or {}).get("time")
    for row in states:
        if not row or len(row) <= _I_SQUAWK:
            continue
        icao = (row[_I_ICAO] or "").strip().upper()
        if not icao:
            continue
        lat = _to_float(row[_I_LAT])
        lon = _to_float(row[_I_LON])
        if region and lat is not None and lon is not None:
            la0, lo0, la1, lo1 = region
            if not (la0 <= lat <= la1 and lo0 <= lon <= lo1):
                continue
        alt_m = _to_float(row[_I_BARO_ALT])
        if alt_m is None:
            alt_m = _to_float(row[_I_GEO_ALT])
        alt_ft = round(alt_m / _M_PER_FT, 1) if alt_m is not None else None
        ts = _to_float(row[_I_TIME]) or _to_float(snap_time) or 0.0
        out.append(Observation(
            timestamp=ts,
            icao=icao,
            callsign=(row[_I_CALLSIGN] or "").strip().upper(),
            lat=lat,
            lon=lon,
            altitude=alt_ft,
            squawk=(row[_I_SQUAWK] or "").strip(),
        ))
    return out


def fetch_observations(*, offline: bool = False, max_age_hours: float = 1.0,
                       region: Optional[tuple] = None) -> list:
    """One-call live (or cached/offline) ADS-B ingest -> Observation list.

    This is the real enrichment: it turns the live OpenSky feed into the exact
    input the anomaly engine scans, so `adsbwatch` can hunt emergency squawks,
    callsign spoofing and loiter patterns over **live airspace** — or over a
    cached snapshot on an air-gapped sensor.
    """
    payload = get_raw("opensky-states", offline=offline, max_age_hours=max_age_hours)
    return states_to_observations(payload, region=region)


# --------------------------------------------------------------------------- #
# CLI: adsbwatch feeds list|update|get <id> [--offline]
# --------------------------------------------------------------------------- #
def feeds_main(args) -> int:
    df = _datafeeds()
    sub = getattr(args, "feeds_cmd", None)

    if sub == "list":
        for f in list_feeds():
            age = df.cached_age_hours(f["id"])
            fresh = "uncached" if age is None else f"{age:.1f}h old"
            print(f"  {f['id']:16} {f.get('domain',''):8} [{fresh}]  {f['name']}")
            print(f"      src: {f['url']}")
        return 0

    if sub == "update":
        try:
            path = update(args.feed_id)
        except (ValueError, KeyError, ConnectionError) as e:
            print(f"error: {e}", file=sys.stderr)
            return 1
        print(f"  updated {args.feed_id} -> {path}")
        return 0

    if sub == "get":
        try:
            obs = fetch_observations(offline=args.offline,
                                     region=getattr(args, "_region", None))
        except (ValueError, KeyError, FileNotFoundError, ConnectionError) as e:
            print(f"error: {e}", file=sys.stderr)
            return 1
        # Summarise the live ingest as scan-ready input.
        emerg = [o for o in obs if o.squawk in ("7500", "7600", "7700")]
        print(f"opensky-states: {len(obs)} aircraft ingested "
              f"({'offline cache' if args.offline else 'live/cache'})")
        if emerg:
            print(f"  emergency squawks present: {len(emerg)}")
            for o in emerg[:20]:
                print(f"    {o.icao} {o.callsign or '-':8} squawk {o.squawk}")
        print(f"  -> feed adsbwatch's analyzer with {len(obs)} observation row(s)")
        return 0

    print("usage: adsbwatch feeds {list|update|get} [<id>] [--offline]",
          file=sys.stderr)
    return 1
