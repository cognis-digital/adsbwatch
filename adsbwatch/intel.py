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


# --------------------------------------------------------------------------- #
# KML (Google Earth / QGIS)
# --------------------------------------------------------------------------- #
def _xml_escape(s: str) -> str:
    return (str(s).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


# Google-Earth placemark colours are aabbggrr (alpha,blue,green,red).
_KML_COLOR = {
    "critical": "ff0000ff",   # red
    "high": "ff007fff",       # orange
    "medium": "ff00ffff",     # yellow
    "low": "ff00ff00",        # green
}


def to_kml(result, observations=None) -> str:
    """Google Earth / KML: one styled Placemark per geolocated anomaly.

    Colours track severity so an analyst can eyeball the picture in Earth/QGIS.
    Standard library only; no map service.
    """
    pos = _positions(observations)
    styles = []
    for sev, color in _KML_COLOR.items():
        styles.append(
            f'    <Style id="sev-{sev}">\n'
            f'      <IconStyle><color>{color}</color>'
            f'<Icon><href>http://maps.google.com/mapfiles/kml/shapes/target.png</href></Icon>'
            f'</IconStyle>\n    </Style>')
    marks = []
    for a in result.anomalies:
        c = _coords(a, pos)
        if c is None:
            continue
        lat, lon = c
        sev = a.severity if a.severity in _KML_COLOR else "medium"
        name = _xml_escape(f"{a.kind}: {a.icao} {a.callsign}".strip())
        desc = _xml_escape(f"{a.detail} ({_iso(a.timestamp)})")
        marks.append(
            f'    <Placemark>\n'
            f'      <name>{name}</name>\n'
            f'      <description>{desc}</description>\n'
            f'      <styleUrl>#sev-{sev}</styleUrl>\n'
            f'      <Point><coordinates>{lon},{lat},0</coordinates></Point>\n'
            f'    </Placemark>')
    body = "\n".join(styles + marks)
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<kml xmlns="http://www.opengis.net/kml/2.2">\n'
        '  <Document>\n'
        '    <name>adsbwatch anomalies</name>\n'
        f'{body}\n'
        '  </Document>\n'
        '</kml>\n')


# --------------------------------------------------------------------------- #
# Cursor-on-Target (CoT) — ATAK / TAK situational-awareness feed
# --------------------------------------------------------------------------- #
# Neutral/unknown SA event type. We deliberately emit a generic track/point
# atom, NOT a hostile designation — this is situational awareness for a human,
# not targeting.
_COT_TYPE = "a-u-A"   # atom, unknown affiliation, Air


def to_cot(result, observations=None, *, stale_s: float = 3600.0) -> str:
    """Cursor-on-Target XML events (ATAK/TAK/WinTAK) for each geolocated anomaly.

    Emits neutral/unknown air tracks (``a-u-A``) with a remark carrying the
    finding — situational awareness for an operator's common operating picture.
    It is not a targeting designation and carries no affiliation as hostile.
    """
    pos = _positions(observations)
    events = []
    for a in result.anomalies:
        c = _coords(a, pos)
        if c is None:
            continue
        lat, lon = c
        t = _iso(a.timestamp)
        stale = _iso(float(a.timestamp) + stale_s) if _is_num(a.timestamp) else t
        uid = _xml_escape(f"adsbwatch.{a.icao}.{a.kind}.{int(_num(a.timestamp))}")
        remark = _xml_escape(f"[{a.severity}] {a.kind}: {a.detail}")
        callsign = _xml_escape(a.callsign or a.icao)
        events.append(
            f'  <event version="2.0" uid="{uid}" type="{_COT_TYPE}" '
            f'time="{t}" start="{t}" stale="{stale}" how="m-g">\n'
            f'    <point lat="{lat}" lon="{lon}" hae="0" ce="9999999" le="9999999"/>\n'
            f'    <detail>\n'
            f'      <contact callsign="{callsign}"/>\n'
            f'      <remarks>{remark}</remarks>\n'
            f'    </detail>\n'
            f'  </event>')
    inner = "\n".join(events)
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        '<events>\n'
        f'{inner}\n'
        '</events>\n')


def _is_num(v) -> bool:
    try:
        float(v)
        return True
    except (TypeError, ValueError):
        return False


def _num(v) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


_EXPORTERS = {"geojson": to_geojson, "stix": to_stix, "kml": to_kml, "cot": to_cot}


def export(result, fmt: str, observations=None) -> str:
    fmt = fmt.lower()
    if fmt not in _EXPORTERS:
        raise ValueError(f"unknown export format {fmt!r}; choose one of {sorted(_EXPORTERS)}")
    return _EXPORTERS[fmt](result, observations)
