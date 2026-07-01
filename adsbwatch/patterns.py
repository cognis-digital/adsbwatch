"""Pattern-of-life analytics for an ADS-B observation stream — offline, stdlib.

Where the detectors in :mod:`adsbwatch.core` answer *"is this single event
anomalous?"*, this module answers *"what is the behaviour over time?"* — the
situational-awareness layer that turns a pile of position reports into a picture
an analyst can reason about:

* :func:`aircraft_profiles` — per-ICAO summary: first/last seen, dwell, report
  count, distinct callsigns/squawks, altitude range, bounding box, track length.
* :func:`recurring_visits` — aircraft that repeatedly appear near a point of
  interest across separated time windows (a "pattern of life" around a site).
* :func:`summarize` — a rolled-up report suitable for JSON export or a briefing.

All purely descriptive and defensive: it characterises observed behaviour for a
human analyst; it does not identify individuals, target, or recommend force.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .core import Observation, haversine_nm


@dataclass
class AircraftProfile:
    icao: str
    first_seen: float
    last_seen: float
    reports: int
    callsigns: list = field(default_factory=list)
    squawks: list = field(default_factory=list)
    alt_min_ft: Optional[float] = None
    alt_max_ft: Optional[float] = None
    bbox: Optional[list] = None       # [min_lat, min_lon, max_lat, max_lon]
    track_nm: float = 0.0             # cumulative great-circle path length

    @property
    def dwell_s(self) -> float:
        return max(0.0, self.last_seen - self.first_seen)

    def to_dict(self) -> dict:
        return {
            "icao": self.icao,
            "first_seen": self.first_seen,
            "last_seen": self.last_seen,
            "dwell_s": round(self.dwell_s, 1),
            "reports": self.reports,
            "callsigns": self.callsigns,
            "squawks": self.squawks,
            "alt_min_ft": self.alt_min_ft,
            "alt_max_ft": self.alt_max_ft,
            "bbox": self.bbox,
            "track_nm": round(self.track_nm, 2),
        }


def _by_icao(observations: list) -> dict:
    d: dict = {}
    for o in observations:
        d.setdefault(o.icao, []).append(o)
    return d


def aircraft_profiles(observations: list) -> list:
    """Per-ICAO pattern-of-life profiles, sorted by report count (descending)."""
    profiles: list = []
    for icao, obs in _by_icao(observations).items():
        pts = sorted(obs, key=lambda o: o.timestamp)
        callsigns: list = []
        squawks: list = []
        for o in pts:
            if o.callsign and o.callsign not in callsigns:
                callsigns.append(o.callsign)
            if o.squawk and o.squawk not in squawks:
                squawks.append(o.squawk)
        alts = [o.altitude for o in pts if o.altitude is not None]
        geo = [o for o in pts if o.lat is not None and o.lon is not None]
        bbox = None
        if geo:
            lats = [o.lat for o in geo]
            lons = [o.lon for o in geo]
            bbox = [round(min(lats), 5), round(min(lons), 5),
                    round(max(lats), 5), round(max(lons), 5)]
        track = 0.0
        for a, b in zip(geo, geo[1:]):
            track += haversine_nm(a.lat, a.lon, b.lat, b.lon)
        profiles.append(AircraftProfile(
            icao=icao,
            first_seen=pts[0].timestamp,
            last_seen=pts[-1].timestamp,
            reports=len(pts),
            callsigns=callsigns,
            squawks=squawks,
            alt_min_ft=(min(alts) if alts else None),
            alt_max_ft=(max(alts) if alts else None),
            bbox=bbox,
            track_nm=track,
        ))
    profiles.sort(key=lambda p: (p.reports, p.dwell_s), reverse=True)
    return profiles


def recurring_visits(observations: list, poi_lat: float, poi_lon: float, *,
                     radius_nm: float = 5.0, gap_s: float = 3600.0,
                     min_visits: int = 2) -> list:
    """Aircraft that repeatedly approach a point of interest in separated windows.

    A "visit" is a run of near-POI reports; two visits are distinct when
    separated by more than ``gap_s`` of absence. Aircraft with at least
    ``min_visits`` distinct visits are returned — a pattern-of-life signal around
    a monitored site. Descriptive only.
    """
    out: list = []
    for icao, obs in _by_icao(observations).items():
        near = [o for o in sorted(obs, key=lambda o: o.timestamp)
                if o.lat is not None and o.lon is not None
                and haversine_nm(poi_lat, poi_lon, o.lat, o.lon) <= radius_nm]
        if not near:
            continue
        visits = []
        cur = [near[0]]
        for prev, o in zip(near, near[1:]):
            if o.timestamp - prev.timestamp > gap_s:
                visits.append(cur)
                cur = [o]
            else:
                cur.append(o)
        visits.append(cur)
        if len(visits) >= min_visits:
            out.append({
                "icao": icao,
                "callsign": next((o.callsign for o in near if o.callsign), ""),
                "visits": len(visits),
                "total_reports_near": len(near),
                "windows": [
                    {"start": v[0].timestamp, "end": v[-1].timestamp, "reports": len(v)}
                    for v in visits
                ],
                "closest_nm": round(min(
                    haversine_nm(poi_lat, poi_lon, o.lat, o.lon) for o in near), 3),
            })
    out.sort(key=lambda d: d["visits"], reverse=True)
    return out


def summarize(observations: list) -> dict:
    """A rolled-up pattern-of-life report for JSON export / briefings."""
    profs = aircraft_profiles(observations)
    ts = [o.timestamp for o in observations]
    return {
        "observations": len(observations),
        "aircraft": len(profs),
        "window": {
            "start": (min(ts) if ts else None),
            "end": (max(ts) if ts else None),
        },
        "profiles": [p.to_dict() for p in profs],
    }
