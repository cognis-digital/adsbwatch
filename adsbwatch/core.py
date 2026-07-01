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
import math
import re
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Iterable, Optional

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

# Fastest air-breathing aircraft in level flight (SR-71) is ~2000 kt; anything
# implying a ground speed far beyond this between two consecutive reports from a
# single hardware address is physically impossible and a classic signature of a
# spoofed/injected position (or a corrupt feed). We default the ceiling well
# above any conventional aircraft to keep false positives near zero.
DEFAULT_MAX_GROUND_SPEED_KT = 3500.0

# No conventional aircraft sustains a climb/descent beyond roughly this many feet
# per minute; a computed vertical rate far above it between two consecutive
# reports for one ICAO is either a corrupt/spoofed altitude or a data artifact.
# Fighters can briefly exceed 30k ft/min in a zoom climb, so we default high to
# keep false positives near zero and let operators tighten it.
DEFAULT_MAX_VERTICAL_RATE_FPM = 60000.0

# Two distinct ICAOs holding tight in both horizontal distance and altitude while
# co-present in time is a formation-flight signature (relevant to force
# protection / airspace monitoring). Defaults are conservative so aircraft that
# merely pass near one another are not flagged.
DEFAULT_FORMATION_RADIUS_NM = 1.0
DEFAULT_FORMATION_ALT_FT = 500.0
DEFAULT_FORMATION_MIN_SAMPLES = 3


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
    kind: str            # 'emergency_squawk' | 'callsign_spoof' | 'loiter' |
                         # 'impossible_kinematics' | 'squawk_change' |
                         # 'impossible_vertical_rate' | 'formation'
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
    """Read a CSV file of ADS-B observations into a list of Observation."""
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


def _detect_impossible_kinematics(obs_by_ac: dict, *, max_speed_kt: float) -> list:
    """Flag physically impossible motion for a single ICAO.

    Between two consecutive geolocated reports from one hardware address we
    compute the implied ground speed (great-circle distance / elapsed time). A
    speed above ``max_speed_kt`` means the aircraft would have to teleport — the
    hallmark of a spoofed / injected position report or two aircraft sharing one
    (cloned) ICAO. Reports with the same timestamp but different positions are
    treated as an infinite-speed jump. Zero/negative time deltas from duplicate
    identical points are ignored.
    """
    found: list = []
    for icao, obs in obs_by_ac.items():
        pts = [o for o in obs if o.lat is not None and o.lon is not None]
        pts.sort(key=lambda o: o.timestamp)
        for a, b in zip(pts, pts[1:]):
            dist_nm = haversine_nm(a.lat, a.lon, b.lat, b.lon)
            if dist_nm < 1e-6:
                continue  # same position -> no jump regardless of dt
            dt_h = (b.timestamp - a.timestamp) / 3600.0
            if dt_h <= 0:
                speed = float("inf")  # moved without time passing
            else:
                speed = dist_nm / dt_h
            if speed > max_speed_kt:
                found.append(Anomaly(
                    kind="impossible_kinematics",
                    severity="high",
                    icao=icao,
                    callsign=(b.callsign or a.callsign or ""),
                    detail=(f"Implied ground speed "
                            f"{'inf' if speed == float('inf') else f'{speed:.0f}'} kt "
                            f"({dist_nm:.1f} NM in {(b.timestamp - a.timestamp):.1f}s) "
                            f"exceeds {max_speed_kt:.0f} kt — likely spoofed/injected position"),
                    timestamp=b.timestamp,
                    evidence={
                        "implied_speed_kt": (None if speed == float("inf")
                                             else round(speed, 1)),
                        "distance_nm": round(dist_nm, 3),
                        "dt_sec": round(b.timestamp - a.timestamp, 3),
                        "from": [round(a.lat, 5), round(a.lon, 5)],
                        "to": [round(b.lat, 5), round(b.lon, 5)],
                        "max_speed_kt": max_speed_kt,
                    },
                ))
                break  # one finding per aircraft is enough to raise it
    return found


def _detect_squawk_changes(obs_by_ac: dict, *, watch_codes=None) -> list:
    """Flag a transponder code changing to (or through) an emergency code.

    A mid-track transition *into* 7500/7600/7700 is operationally distinct from a
    feed that simply starts on an emergency code: it marks the moment a crew
    declared an emergency (or, if the aircraft was previously squawking a normal
    code, a possible sudden hijack/comms event). One finding per aircraft per
    entered emergency code, timestamped at the transition.
    """
    watch = set(watch_codes) if watch_codes else set(SQUAWK_MEANINGS)
    found: list = []
    for icao, obs in obs_by_ac.items():
        pts = sorted(obs, key=lambda o: o.timestamp)
        prev = None
        entered = set()
        for o in pts:
            code = (o.squawk or "").strip()
            if not code:
                continue
            if prev is not None and code != prev and code in watch and code not in entered:
                entered.add(code)
                sev = "critical" if code in ("7500", "7700") else "high"
                meaning = SQUAWK_MEANINGS.get(code, "special-purpose code")
                found.append(Anomaly(
                    kind="squawk_change",
                    severity=sev,
                    icao=icao,
                    callsign=o.callsign,
                    detail=(f"Transponder changed {prev} -> {code} "
                            f"({meaning}) mid-track"),
                    timestamp=o.timestamp,
                    evidence={
                        "from": prev,
                        "to": code,
                        "meaning": meaning,
                    },
                ))
            if code:
                prev = code
    return found


def _detect_vertical_rate(obs_by_ac: dict, *, max_rate_fpm: float) -> list:
    """Flag an implausible barometric climb/descent rate for a single ICAO.

    Between two consecutive reports carrying an altitude we compute the vertical
    rate (delta-alt in feet / elapsed minutes). A rate beyond ``max_rate_fpm`` is
    either a spoofed/corrupt altitude or a data artifact — of interest both for
    feed-integrity and for spotting injected tracks. One finding per aircraft.
    """
    found: list = []
    for icao, obs in obs_by_ac.items():
        pts = [o for o in obs if o.altitude is not None]
        pts.sort(key=lambda o: o.timestamp)
        for a, b in zip(pts, pts[1:]):
            dalt = abs(b.altitude - a.altitude)
            if dalt < 1.0:
                continue
            dt_min = (b.timestamp - a.timestamp) / 60.0
            if dt_min <= 0:
                rate = float("inf")
            else:
                rate = dalt / dt_min
            if rate > max_rate_fpm:
                found.append(Anomaly(
                    kind="impossible_vertical_rate",
                    severity="medium",
                    icao=icao,
                    callsign=(b.callsign or a.callsign or ""),
                    detail=(f"Vertical rate "
                            f"{'inf' if rate == float('inf') else f'{rate:.0f}'} ft/min "
                            f"({dalt:.0f} ft in {(b.timestamp - a.timestamp):.1f}s) "
                            f"exceeds {max_rate_fpm:.0f} ft/min — suspect altitude"),
                    timestamp=b.timestamp,
                    evidence={
                        "rate_fpm": (None if rate == float("inf") else round(rate, 1)),
                        "delta_alt_ft": round(dalt, 1),
                        "dt_sec": round(b.timestamp - a.timestamp, 3),
                        "from_alt": a.altitude,
                        "to_alt": b.altitude,
                        "max_rate_fpm": max_rate_fpm,
                    },
                ))
                break
    return found


def _time_overlap_positions(obs_a: list, obs_b: list, *, tol_s: float = 30.0):
    """Yield (pa, pb) pairs of geolocated reports from two aircraft that are
    close in time (within ``tol_s``). Both lists must be sorted by timestamp."""
    ga = [o for o in obs_a if o.lat is not None and o.lon is not None]
    gb = [o for o in obs_b if o.lat is not None and o.lon is not None]
    j = 0
    for pa in ga:
        # advance b-pointer to the first report not too far in the past
        while j < len(gb) and gb[j].timestamp < pa.timestamp - tol_s:
            j += 1
        k = j
        while k < len(gb) and gb[k].timestamp <= pa.timestamp + tol_s:
            yield pa, gb[k]
            k += 1


def _detect_formation(obs_by_ac: dict, *, radius_nm: float, alt_ft: float,
                      min_samples: int, tol_s: float = 30.0) -> list:
    """Detect two distinct ICAOs flying in close formation.

    Two aircraft that repeatedly (>= ``min_samples`` co-timed reports) hold within
    ``radius_nm`` horizontally and ``alt_ft`` vertically are flagged as a
    formation. Purely descriptive situational awareness (force protection /
    airspace monitoring): it identifies *that* aircraft are flying together, never
    who to act against. One finding per unordered aircraft pair.
    """
    found: list = []
    icaos = sorted(obs_by_ac)
    sorted_obs = {i: sorted(obs_by_ac[i], key=lambda o: o.timestamp) for i in icaos}
    for x in range(len(icaos)):
        for y in range(x + 1, len(icaos)):
            ia, ib = icaos[x], icaos[y]
            samples = 0
            min_d = float("inf")
            max_alt_gap = 0.0
            first_ts = None
            last_ts = None
            for pa, pb in _time_overlap_positions(sorted_obs[ia], sorted_obs[ib],
                                                  tol_s=tol_s):
                d = haversine_nm(pa.lat, pa.lon, pb.lat, pb.lon)
                if d > radius_nm:
                    continue
                if pa.altitude is not None and pb.altitude is not None:
                    gap = abs(pa.altitude - pb.altitude)
                    if gap > alt_ft:
                        continue
                    max_alt_gap = max(max_alt_gap, gap)
                samples += 1
                min_d = min(min_d, d)
                ts = max(pa.timestamp, pb.timestamp)
                first_ts = ts if first_ts is None else min(first_ts, ts)
                last_ts = ts if last_ts is None else max(last_ts, ts)
            if samples >= min_samples:
                ca = next((o.callsign for o in sorted_obs[ia] if o.callsign), "")
                cb = next((o.callsign for o in sorted_obs[ib] if o.callsign), "")
                found.append(Anomaly(
                    kind="formation",
                    severity="medium",
                    icao=ia,
                    callsign=f"{ca or ia}+{cb or ib}",
                    detail=(f"Formation: {ia} and {ib} held within "
                            f"{min_d:.2f} NM for {samples} co-timed reports"),
                    timestamp=first_ts if first_ts is not None else 0.0,
                    evidence={
                        "icaos": [ia, ib],
                        "callsigns": [ca, cb],
                        "samples": samples,
                        "min_separation_nm": round(min_d, 3),
                        "max_alt_gap_ft": round(max_alt_gap, 1),
                        "first_ts": first_ts,
                        "last_ts": last_ts,
                    },
                ))
    return found


# ---------------------------------------------------------------------------
# Top-level analysis
# ---------------------------------------------------------------------------

def analyze(observations: list, *, loiter_min_points: int = 6,
            loiter_radius_nm: float = 5.0,
            loiter_min_turn_deg: float = 270.0,
            kinematics_max_speed_kt: float = DEFAULT_MAX_GROUND_SPEED_KT,
            vertical_rate_max_fpm: float = DEFAULT_MAX_VERTICAL_RATE_FPM,
            detect_squawk_changes: bool = True,
            detect_formation: bool = True,
            formation_radius_nm: float = DEFAULT_FORMATION_RADIUS_NM,
            formation_alt_ft: float = DEFAULT_FORMATION_ALT_FT,
            formation_min_samples: int = DEFAULT_FORMATION_MIN_SAMPLES) -> AnalysisResult:
    """Run all detectors over a list of Observation objects.

    ``kinematics_max_speed_kt`` sets the implied ground-speed ceiling for the
    impossible-kinematics detector; a speed above it between two consecutive
    reports from one ICAO is flagged as a likely spoofed/injected position. Set
    it to ``0`` or a negative value to disable that detector.

    ``vertical_rate_max_fpm`` sets the climb/descent ceiling (feet per minute) for
    the vertical-rate detector; ``0`` or negative disables it.

    ``detect_squawk_changes`` flags a transponder transitioning *into* an
    emergency code mid-track. ``detect_formation`` flags two ICAOs holding tight
    formation (``formation_radius_nm`` / ``formation_alt_ft`` /
    ``formation_min_samples`` tune it). All new detectors are additive and
    default-on; existing detectors and output are unchanged.
    """
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
    if kinematics_max_speed_kt and kinematics_max_speed_kt > 0:
        anomalies += _detect_impossible_kinematics(
            obs_by_ac, max_speed_kt=kinematics_max_speed_kt)
    if detect_squawk_changes:
        anomalies += _detect_squawk_changes(obs_by_ac)
    if vertical_rate_max_fpm and vertical_rate_max_fpm > 0:
        anomalies += _detect_vertical_rate(
            obs_by_ac, max_rate_fpm=vertical_rate_max_fpm)
    if detect_formation:
        anomalies += _detect_formation(
            obs_by_ac,
            radius_nm=formation_radius_nm,
            alt_ft=formation_alt_ft,
            min_samples=formation_min_samples,
        )

    sev_rank = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    anomalies.sort(key=lambda a: (sev_rank.get(a.severity, 9), a.timestamp, a.icao))

    return AnalysisResult(
        observations=len(observations),
        aircraft=len(obs_by_ac),
        anomalies=anomalies,
    )
