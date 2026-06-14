"""Core analysis engine for ADSBWATCH.

Pure-stdlib. Consumes a list of ADS-B observation rows (one position report per
row) and produces anomaly findings. No network access.

Expected CSV columns (header row, case-insensitive, extra columns ignored):
    timestamp  - unix epoch seconds (int/float) or ISO-8601 string
    icao       - 24-bit ICAO hex address (aircraft unique id)
    callsign   - flight/callsign string (may be blank)
    lat        - latitude in degrees
    lon        - longitude in degrees
    altitude   - barometric/geometric altitude in feet (may be blank)
    squawk     - 4-digit octal transponder code (may be blank)
"""

from __future__ import annotations

import csv
import json
import math
import re
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Iterable, Optional

# ---------------------------------------------------------------------------
# Package identity
# ---------------------------------------------------------------------------

TOOL_NAME = "adsbwatch"
TOOL_VERSION = "0.1.0"

# ---------------------------------------------------------------------------
# Reference data
# ---------------------------------------------------------------------------

# Emergency / special-purpose squawk codes (ICAO / ATC convention).
SQUAWK_MEANINGS = {
    "7500": "Unlawful interference (hijack)",
    "7600": "Radio communication failure",
    "7700": "General emergency",
}

# A well-formed callsign: 2-3 char operator/ICAO prefix + alphanumerics, or a
# tail number. We treat callsigns as suspicious when they contain illegal
# characters or are implausibly short/long.
_CALLSIGN_OK = re.compile(r"^[A-Z0-9]{2,8}$")

EARTH_RADIUS_NM = 3440.065  # nautical miles


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class Observation:
    """A single ADS-B position report."""
    timestamp: float
    icao: str
    callsign: str = ""
    lat: Optional[float] = None
    lon: Optional[float] = None
    altitude: Optional[float] = None
    squawk: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Anomaly:
    """A detected anomaly tied to an aircraft."""
    kind: str            # 'emergency_squawk' | 'callsign_spoof' | 'loiter'
    severity: str        # 'critical' | 'high' | 'medium' | 'low'
    icao: str
    callsign: str
    detail: str
    timestamp: float
    evidence: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class AnalysisResult:
    observations: int
    aircraft: int
    anomalies: list  # list[Anomaly]

    def to_dict(self) -> dict:
        return {
            "observations": self.observations,
            "aircraft": self.aircraft,
            "anomaly_count": len(self.anomalies),
            "anomalies": [a.to_dict() for a in self.anomalies],
        }


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def _parse_timestamp(raw: str) -> float:
    raw = (raw or "").strip()
    if not raw:
        raise ValueError("empty timestamp")
    try:
        return float(raw)
    except ValueError:
        pass
    # Try ISO-8601 (tolerate trailing Z).
    iso = raw.replace("Z", "+00:00")
    dt = datetime.fromisoformat(iso)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.timestamp()


def _parse_float(raw: str) -> Optional[float]:
    raw = (raw or "").strip()
    if not raw:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def _norm_key(k: str) -> str:
    return (k or "").strip().lower()


def parse_records(rows: Iterable[dict]) -> list:
    """Parse already-dict rows (mapping of column->value) into Observations."""
    out: list = []
    for i, row in enumerate(rows):
        norm = {_norm_key(k): v for k, v in row.items()}
        icao = (norm.get("icao") or norm.get("hex") or "").strip().upper()
        if not icao:
            raise ValueError(f"row {i}: missing icao")
        try:
            ts = _parse_timestamp(norm.get("timestamp") or norm.get("time") or "")
        except ValueError as e:
            raise ValueError(f"row {i}: bad timestamp ({e})") from e
        callsign = (norm.get("callsign") or norm.get("flight") or "").strip().upper()
        squawk = (norm.get("squawk") or "").strip()
        out.append(Observation(
            timestamp=ts,
            icao=icao,
            callsign=callsign,
            lat=_parse_float(norm.get("lat") or norm.get("latitude") or ""),
            lon=_parse_float(norm.get("lon") or norm.get("longitude") or ""),
            altitude=_parse_float(norm.get("altitude") or norm.get("alt") or ""),
            squawk=squawk,
        ))
    return out


def parse_csv(path: str) -> list:
    """Read a CSV file of ADS-B observations into a list of Observation.

    Raises FileNotFoundError if *path* does not exist, ValueError on parse
    problems.  Returns an empty list for a header-only (no data rows) file.
    """
    if not path:
        raise ValueError("feed path must not be empty")
    with open(path, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        if reader.fieldnames is None:
            raise ValueError("CSV has no header row")
        return parse_records(reader)


# ---------------------------------------------------------------------------
# Geo helpers
# ---------------------------------------------------------------------------

def haversine_nm(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in nautical miles."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    # Clamp to [0, 1] to guard against floating-point values marginally outside
    # the valid domain of asin (can happen at identical or antipodal points).
    a = max(0.0, min(1.0, a))
    return 2 * EARTH_RADIUS_NM * math.asin(math.sqrt(a))


def _bearing(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Initial bearing in degrees (0-360) from point 1 to point 2."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dl = math.radians(lon2 - lon1)
    y = math.sin(dl) * math.cos(p2)
    x = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    return (math.degrees(math.atan2(y, x)) + 360.0) % 360.0


def _ang_diff(a: float, b: float) -> float:
    """Smallest signed difference between two bearings, in (-180, 180]."""
    d = (b - a + 180.0) % 360.0 - 180.0
    return d


# ---------------------------------------------------------------------------
# Detectors
# ---------------------------------------------------------------------------

def _detect_emergency_squawks(obs_by_ac: dict) -> list:
    found: list = []
    for icao, obs in obs_by_ac.items():
        seen = set()
        for o in obs:
            code = o.squawk
            if code in SQUAWK_MEANINGS and code not in seen:
                seen.add(code)
                sev = "critical" if code in ("7500", "7700") else "high"
                found.append(Anomaly(
                    kind="emergency_squawk",
                    severity=sev,
                    icao=icao,
                    callsign=o.callsign,
                    detail=f"Squawk {code}: {SQUAWK_MEANINGS[code]}",
                    timestamp=o.timestamp,
                    evidence={"squawk": code, "meaning": SQUAWK_MEANINGS[code]},
                ))
    return found


def _detect_callsign_anomalies(obs_by_ac: dict) -> list:
    """Flag a single ICAO broadcasting multiple distinct callsigns (spoofing /
    identity flip) and malformed callsigns."""
    found: list = []
    for icao, obs in obs_by_ac.items():
        callsigns = [o.callsign for o in obs if o.callsign]
        distinct = []
        for c in callsigns:
            if c not in distinct:
                distinct.append(c)

        # Multiple identities from one hardware address within the dataset.
        if len(distinct) > 1:
            first = next(o for o in obs if o.callsign)
            found.append(Anomaly(
                kind="callsign_spoof",
                severity="high",
                icao=icao,
                callsign="/".join(distinct),
                detail=(f"ICAO {icao} broadcast {len(distinct)} distinct "
                        f"callsigns: {', '.join(distinct)}"),
                timestamp=first.timestamp,
                evidence={"callsigns": distinct},
            ))

        # Malformed callsign(s).
        bad = sorted({c for c in distinct if not _CALLSIGN_OK.match(c)})
        if bad:
            o = next(o for o in obs if o.callsign in bad)
            found.append(Anomaly(
                kind="callsign_spoof",
                severity="medium",
                icao=icao,
                callsign=",".join(bad),
                detail=f"Malformed callsign(s): {', '.join(bad)}",
                timestamp=o.timestamp,
                evidence={"malformed": bad},
            ))
    return found


def _detect_loiter(obs_by_ac: dict, *, min_points: int, radius_nm: float,
                   min_turn_deg: float) -> list:
    """Detect orbit/loiter: track stays within a small radius while cumulative
    heading change exceeds a threshold (i.e. circling rather than transiting).
    """
    found: list = []
    for icao, obs in obs_by_ac.items():
        pts = [o for o in obs if o.lat is not None and o.lon is not None]
        pts.sort(key=lambda o: o.timestamp)
        if len(pts) < min_points:
            continue

        # Centroid of the track.
        clat = sum(p.lat for p in pts) / len(pts)
        clon = sum(p.lon for p in pts) / len(pts)
        max_r = max(haversine_nm(clat, clon, p.lat, p.lon) for p in pts)
        if max_r > radius_nm:
            continue  # spread too wide -> transiting, not loitering

        # Cumulative absolute heading change along the track.
        bearings = []
        for a, b in zip(pts, pts[1:]):
            if haversine_nm(a.lat, a.lon, b.lat, b.lon) < 1e-4:
                continue
            bearings.append(_bearing(a.lat, a.lon, b.lat, b.lon))
        total_turn = 0.0
        for x, y in zip(bearings, bearings[1:]):
            total_turn += abs(_ang_diff(x, y))

        if total_turn >= min_turn_deg:
            dur = pts[-1].timestamp - pts[0].timestamp
            found.append(Anomaly(
                kind="loiter",
                severity="medium",
                icao=icao,
                callsign=next((p.callsign for p in pts if p.callsign), ""),
                detail=(f"Loiter pattern: {len(pts)} points within "
                        f"{max_r:.2f} NM, {total_turn:.0f} deg cumulative turn "
                        f"over {dur/60:.1f} min"),
                timestamp=pts[0].timestamp,
                evidence={
                    "points": len(pts),
                    "radius_nm": round(max_r, 3),
                    "cumulative_turn_deg": round(total_turn, 1),
                    "duration_sec": round(dur, 1),
                    "center": [round(clat, 5), round(clon, 5)],
                },
            ))
    return found


# ---------------------------------------------------------------------------
# Top-level analysis
# ---------------------------------------------------------------------------

def analyze(observations: list, *, loiter_min_points: int = 6,
            loiter_radius_nm: float = 5.0,
            loiter_min_turn_deg: float = 270.0) -> AnalysisResult:
    """Run all detectors over a list of Observation objects.

    Raises ValueError for out-of-range tuning parameters.
    Returns an AnalysisResult with an empty anomalies list when *observations*
    is empty.
    """
    if loiter_min_points < 2:
        raise ValueError(
            f"loiter_min_points must be >= 2, got {loiter_min_points!r}"
        )
    if loiter_radius_nm <= 0:
        raise ValueError(
            f"loiter_radius_nm must be > 0, got {loiter_radius_nm!r}"
        )
    if loiter_min_turn_deg <= 0:
        raise ValueError(
            f"loiter_min_turn_deg must be > 0, got {loiter_min_turn_deg!r}"
        )
    obs_by_ac: dict = {}
    for o in observations:
        obs_by_ac.setdefault(o.icao, []).append(o)

    anomalies: list = []
    anomalies += _detect_emergency_squawks(obs_by_ac)
    anomalies += _detect_callsign_anomalies(obs_by_ac)
    anomalies += _detect_loiter(
        obs_by_ac,
        min_points=loiter_min_points,
        radius_nm=loiter_radius_nm,
        min_turn_deg=loiter_min_turn_deg,
    )

    sev_rank = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    anomalies.sort(key=lambda a: (sev_rank.get(a.severity, 9), a.timestamp, a.icao))

    return AnalysisResult(
        observations=len(observations),
        aircraft=len(obs_by_ac),
        anomalies=anomalies,
    )


# ---------------------------------------------------------------------------
# Convenience wrappers (used by mcp_server and external callers)
# ---------------------------------------------------------------------------

def scan(path: str, **kwargs) -> AnalysisResult:
    """Parse *path* and run :func:`analyze`. Convenience wrapper for MCP/CLI."""
    return analyze(parse_csv(path), **kwargs)


def to_json(result: AnalysisResult) -> str:
    """Serialise an :class:`AnalysisResult` to a JSON string."""
    return json.dumps(result.to_dict(), indent=2)
