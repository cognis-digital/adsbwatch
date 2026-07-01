"""Restricted-airspace / NOTAM incursion detection — offline, stdlib only.

Given a set of restricted zones (loaded from an OFFLINE fixture — a NOTAM export,
a prohibited/restricted-area list, or a TFR snapshot) and a stream of ADS-B
:class:`~adsbwatch.core.Observation` reports, this module flags aircraft whose
reported position enters a zone during that zone's active window and within its
altitude band.

Scope is strictly defensive / situational-awareness: it answers *"did a track
enter a monitored volume?"* for airspace monitoring and force protection. It does
not track people, target, or recommend any use of force — it emits
:class:`~adsbwatch.core.Anomaly` records the same way the other detectors do, for
a human to assess (see :mod:`adsbwatch.decision`).

Zone geometry supported (all offline, no map service):

* **circle**   — ``{"shape": "circle", "center": [lat, lon], "radius_nm": R}``
* **polygon**  — ``{"shape": "polygon", "vertices": [[lat, lon], ...]}``

Optional per-zone fields: ``id``, ``name``, ``severity`` (default ``high``),
``alt_floor_ft`` / ``alt_ceiling_ft`` (band the restriction applies to),
``active_from`` / ``active_to`` (unix epoch or ISO-8601; open-ended if omitted).
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from typing import Optional

from .core import Anomaly, Observation, haversine_nm, _parse_timestamp


# --------------------------------------------------------------------------- #
# Zone model
# --------------------------------------------------------------------------- #
@dataclass
class Zone:
    """A restricted/monitored airspace volume loaded from an offline fixture."""
    id: str
    name: str = ""
    shape: str = "circle"                 # 'circle' | 'polygon'
    severity: str = "high"
    center: Optional[list] = None         # [lat, lon] for circle
    radius_nm: Optional[float] = None     # for circle
    vertices: list = field(default_factory=list)  # [[lat, lon], ...] for polygon
    alt_floor_ft: Optional[float] = None
    alt_ceiling_ft: Optional[float] = None
    active_from: Optional[float] = None   # unix epoch
    active_to: Optional[float] = None

    def active_at(self, ts: float) -> bool:
        if self.active_from is not None and ts < self.active_from:
            return False
        if self.active_to is not None and ts > self.active_to:
            return False
        return True

    def alt_in_band(self, alt: Optional[float]) -> bool:
        """True if ``alt`` falls in the restricted band. Unknown altitude is
        treated as *potentially* in the band (fail-safe: do not silently clear)."""
        if alt is None:
            return True
        if self.alt_floor_ft is not None and alt < self.alt_floor_ft:
            return False
        if self.alt_ceiling_ft is not None and alt > self.alt_ceiling_ft:
            return False
        return True

    def contains(self, lat: float, lon: float) -> bool:
        if self.shape == "circle":
            if not self.center or self.radius_nm is None:
                return False
            d = haversine_nm(self.center[0], self.center[1], lat, lon)
            return d <= self.radius_nm
        if self.shape == "polygon":
            return _point_in_polygon(lat, lon, self.vertices)
        return False


def _point_in_polygon(lat: float, lon: float, verts: list) -> bool:
    """Ray-casting point-in-polygon. ``verts`` is [[lat, lon], ...].

    Operates in planar lat/lon degrees, which is accurate enough for the modest
    zone sizes (airfields, ranges, TFRs) this tool targets. A point on an edge is
    treated as inside.
    """
    n = len(verts)
    if n < 3:
        return False
    inside = False
    j = n - 1
    for i in range(n):
        yi, xi = verts[i][0], verts[i][1]   # lat, lon
        yj, xj = verts[j][0], verts[j][1]
        # exact-vertex / horizontal-edge tolerance
        if (abs(yi - lat) < 1e-12 and abs(xi - lon) < 1e-12):
            return True
        intersect = ((yi > lat) != (yj > lat)) and (
            lon < (xj - xi) * (lat - yi) / ((yj - yi) or 1e-15) + xi)
        if intersect:
            inside = not inside
        j = i
    return inside


# --------------------------------------------------------------------------- #
# Loading zones from offline fixtures
# --------------------------------------------------------------------------- #
def _coerce_ts(v):
    if v in (None, ""):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        try:
            return _parse_timestamp(str(v))
        except ValueError:
            return None


def zone_from_dict(d: dict) -> Zone:
    return Zone(
        id=str(d.get("id") or d.get("name") or "zone"),
        name=str(d.get("name") or d.get("id") or ""),
        shape=str(d.get("shape") or ("polygon" if d.get("vertices") else "circle")).lower(),
        severity=str(d.get("severity") or "high").lower(),
        center=list(d["center"]) if d.get("center") else None,
        radius_nm=(float(d["radius_nm"]) if d.get("radius_nm") not in (None, "") else None),
        vertices=[list(v) for v in (d.get("vertices") or [])],
        alt_floor_ft=(float(d["alt_floor_ft"]) if d.get("alt_floor_ft") not in (None, "") else None),
        alt_ceiling_ft=(float(d["alt_ceiling_ft"]) if d.get("alt_ceiling_ft") not in (None, "") else None),
        active_from=_coerce_ts(d.get("active_from")),
        active_to=_coerce_ts(d.get("active_to")),
    )


def load_zones(path_or_text: str) -> list:
    """Load restricted zones from a JSON file/text (offline fixture).

    Accepts a filesystem path or raw JSON text. The JSON may be a list of zone
    objects or ``{"zones": [...]}``. Malformed JSON raises ``ValueError``.
    """
    if path_or_text is None:
        return []
    text = path_or_text
    stripped = path_or_text.strip()
    is_path = "\n" not in path_or_text and stripped[:1] not in ("[", "{") and stripped != ""
    if is_path:
        with open(path_or_text, encoding="utf-8") as fh:
            text = fh.read()
    if not text.strip():
        return []
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise ValueError(f"could not parse zones: {e}") from e
    if isinstance(data, dict):
        data = data.get("zones", [])
    return [zone_from_dict(z) for z in data]


# --------------------------------------------------------------------------- #
# Incursion detection
# --------------------------------------------------------------------------- #
def detect_incursions(observations: list, zones: list) -> list:
    """Flag observations whose position enters an active zone in its altitude band.

    Returns a list of :class:`~adsbwatch.core.Anomaly` of kind ``airspace_incursion``.
    One finding per (aircraft, zone) at the FIRST entering report, so a track that
    lingers inside a zone raises once rather than per report.
    """
    found: list = []
    seen: set = set()
    ordered = sorted(
        (o for o in observations if o.lat is not None and o.lon is not None),
        key=lambda o: o.timestamp,
    )
    for o in ordered:
        for z in zones:
            key = (o.icao, z.id)
            if key in seen:
                continue
            if not z.active_at(o.timestamp):
                continue
            if not z.alt_in_band(o.altitude):
                continue
            if not z.contains(o.lat, o.lon):
                continue
            seen.add(key)
            found.append(Anomaly(
                kind="airspace_incursion",
                severity=z.severity if z.severity in ("critical", "high", "medium", "low") else "high",
                icao=o.icao,
                callsign=o.callsign,
                detail=(f"Entered restricted zone '{z.name or z.id}' at "
                        f"[{o.lat:.4f}, {o.lon:.4f}]"
                        + (f" @ {o.altitude:.0f} ft" if o.altitude is not None else "")),
                timestamp=o.timestamp,
                evidence={
                    "zone_id": z.id,
                    "zone_name": z.name,
                    "shape": z.shape,
                    "position": [round(o.lat, 5), round(o.lon, 5)],
                    "altitude_ft": o.altitude,
                    "alt_floor_ft": z.alt_floor_ft,
                    "alt_ceiling_ft": z.alt_ceiling_ft,
                },
            ))
    found.sort(key=lambda a: (a.timestamp, a.icao))
    return found
