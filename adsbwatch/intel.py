"""Native, dependency-free intel export for adsbwatch anomalies.

Turns an :class:`~adsbwatch.core.AnalysisResult` into the formats analysts and
SOCs actually consume:

* **GeoJSON** — each geolocated anomaly as a point for Leaflet/Mapbox/QGIS/kepler.gl
  (plotting emergency squawks / spoofed callsigns / loiter orbits on a map).
* **STIX 2.1** — a valid bundle pairing a ``location`` SDO with an ``observed-data``
  + ``note`` per anomaly, grouped in a ``report``; ingestible by TIPs/OpenCTI.

Coordinates come from the anomaly's own evidence (loiter ``center``) or, failing
that, the aircraft's last known position from the observation stream. Standard
library only — complements :mod:`adsbwatch.connect` (the cognis-connect bridge).
"""

from __future__ import annotations

import json
import time
import uuid

_NS = uuid.UUID("ad5b0000-0000-4000-8000-636f676e6973")
_FALLBACK_TS = "2026-01-01T00:00:00.000Z"


def _iso(epoch) -> str:
    try:
        return time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime(float(epoch)))
    except (TypeError, ValueError, OSError, OverflowError):
        return _FALLBACK_TS


def _positions(observations) -> dict:
    """icao -> (lat, lon) from the latest position report carrying coordinates."""
    pos: dict = {}
    for o in (observations or []):
        lat = getattr(o, "lat", None)
        lon = getattr(o, "lon", None)
        if lat is not None and lon is not None:
            pos[getattr(o, "icao", "")] = (float(lat), float(lon))
    return pos


def _coords(a, pos: dict):
    center = (a.evidence or {}).get("center")
    if isinstance(center, (list, tuple)) and len(center) == 2:
        return float(center[0]), float(center[1])
    return pos.get(a.icao)


# --------------------------------------------------------------------------- #
# GeoJSON
# --------------------------------------------------------------------------- #
def to_geojson(result, observations=None) -> str:
    pos = _positions(observations)
    feats = []
    for a in result.anomalies:
        c = _coords(a, pos)
        if c is None:
            continue
        lat, lon = c
        feats.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [lon, lat]},  # [lon,lat]
            "properties": {
                "kind": a.kind, "severity": a.severity, "icao": a.icao,
                "callsign": a.callsign, "detail": a.detail,
                "timestamp": _iso(a.timestamp), **(a.evidence or {}),
            },
        })
    return json.dumps({"type": "FeatureCollection", "features": feats}, indent=2)


# --------------------------------------------------------------------------- #
# STIX 2.1
# --------------------------------------------------------------------------- #
def to_stix(result, observations=None) -> str:
    pos = _positions(observations)
    objects: list = []
    refs: list = []
    for a in result.anomalies:
        seed = json.dumps(a.to_dict(), sort_keys=True, default=str)
        ts = _iso(a.timestamp)
        note_id = f"note--{uuid.uuid5(_NS, 'note:' + seed)}"
        obs_id = f"observed-data--{uuid.uuid5(_NS, 'obs:' + seed)}"
        obj_refs = []
        c = _coords(a, pos)
        if c is not None:
            lat, lon = c
            loc_id = f"location--{uuid.uuid5(_NS, f'loc:{a.icao}:{lat},{lon}')}"
            objects.append({
                "type": "location", "spec_version": "2.1", "id": loc_id,
                "created": ts, "modified": ts, "latitude": lat, "longitude": lon,
                "name": f"{a.icao} {a.callsign}".strip(),
            })
            obj_refs.append(loc_id)
            refs.append(loc_id)
        objects.append({
            "type": "observed-data", "spec_version": "2.1", "id": obs_id,
            "created": ts, "modified": ts,
            "first_observed": ts, "last_observed": ts, "number_observed": 1,
            "object_refs": obj_refs or [note_id],
        })
        objects.append({
            "type": "note", "spec_version": "2.1", "id": note_id,
            "created": ts, "modified": ts,
            "abstract": f"{a.kind}: {a.icao} {a.callsign}".strip(),
            "content": a.detail,
            "labels": [a.kind, a.severity],
            "object_refs": [obs_id] + obj_refs,
        })
        refs.extend([obs_id, note_id])

    report_id = f"report--{uuid.uuid5(_NS, 'report:' + '|'.join(refs))}"
    report = {
        "type": "report", "spec_version": "2.1", "id": report_id,
        "created": _FALLBACK_TS, "modified": _FALLBACK_TS,
        "name": f"adsbwatch anomaly report ({len(result.anomalies)} anomalies)",
        "report_types": ["threat-report"], "published": _FALLBACK_TS,
        "object_refs": refs or [report_id],
    }
    return json.dumps({
        "type": "bundle",
        "id": f"bundle--{uuid.uuid5(_NS, report_id)}",
        "objects": [report] + objects,
    }, indent=2)


_EXPORTERS = {"geojson": to_geojson, "stix": to_stix}


def export(result, fmt: str, observations=None) -> str:
    fmt = fmt.lower()
    if fmt not in _EXPORTERS:
        raise ValueError(f"unknown export format {fmt!r}; choose one of {sorted(_EXPORTERS)}")
    return _EXPORTERS[fmt](result, observations)
