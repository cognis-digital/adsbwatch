"""Decision-support layer - the architecture *above* the alert, with the human kept in command.

When an anomaly fires, an operator still has to decide what it means and what to do. This
module helps that decision WITHOUT making it for them or touching any effector:

  1. triage()      - score, de-duplicate and rank anomalies so the operator looks at the
                     most important thing first.
  2. correlate()   - fuse ADS-B anomalies with other LOCAL sensor logs (cameras, RF logs,
                     access-control, etc.) on a shared timeline to build pattern-of-life and
                     an evidence bundle (per the "correlate, don't replace" approach).
  3. recommend()   - produce ADVISORY courses of action for a human operator (log, notify,
                     escalate to authorities, cross-cue a camera, request ID, preserve
                     evidence). The operator decides and acts.

HARD SCOPE (enforced by an allow-list + tests): this is decision *support*, not decision
*authority*. It emits recommendations and notifications for a person to act on. It has NO
interface to weapons, jammers, interceptors, or any effector, and it never acts
autonomously. Every recommendation requires human authorization. Pure standard library,
fully local (data sovereignty).
"""

from __future__ import annotations

import csv
import io
import json
from dataclasses import asdict, dataclass, field

SCOPE = ("decision-support (human-in-the-loop): triage, correlation and ADVISORY "
         "recommendations for an operator. No effector/weapon interface; never autonomous; "
         "every action requires human authorization.")

# The ONLY action types this layer may ever recommend. All are things a human does to
# understand the situation, preserve evidence, or alert the proper authority. Anything that
# would command force (engage/fire/jam/intercept/launch/strike/destroy/neutralize) is
# deliberately absent and is rejected by `_assert_advisory` + tests.
_ALLOWED_ACTIONS = {
    "log",                 # record + timestamp the event
    "notify_operator",     # surface to the human on watch
    "escalate_authority",  # hand off to ATC / police / the responsible agency
    "correlate",           # pull in other local sensor data
    "cross_cue_camera",    # slew/point a camera to gather more information (sensing only)
    "request_identification",  # query secondary ID sources (Mode S, flight plans)
    "preserve_evidence",   # snapshot the data for later review / reporting
    "continue_monitoring", # keep watching; no action yet
}

_SEV_RANK = {"critical": 4, "high": 3, "medium": 2, "low": 1, "info": 0}


@dataclass
class SensorEvent:
    """A generic record from any other LOCAL sensor (camera, RF logger, access control)."""
    timestamp: float
    source: str            # e.g. "camera-north", "rf-log", "access-control"
    type: str = ""         # e.g. "motion", "rf_burst", "badge_denied"
    detail: str = ""
    lat: float | None = None
    lon: float | None = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Recommendation:
    action: str            # one of _ALLOWED_ACTIONS
    text: str              # what the operator should consider doing
    urgency: str           # 'immediate' | 'prompt' | 'routine'

    def to_dict(self) -> dict:
        return asdict(self)


def _assert_advisory(recs: list[Recommendation]) -> None:
    for r in recs:
        if r.action not in _ALLOWED_ACTIONS:
            raise ValueError(f"non-advisory action '{r.action}' is out of scope: this layer "
                             f"only supports a human operator and never commands effectors")


# --- 1. triage ---------------------------------------------------------------
def triage(anomalies: list, *, dedupe_window_s: float = 120.0) -> list[dict]:
    """Rank anomalies by priority for the operator; merge near-duplicate repeats."""
    items = sorted(anomalies, key=lambda a: a.timestamp)
    merged: list = []
    for a in items:
        dup = next((m for m in merged if m["icao"] == a.icao and m["kind"] == a.kind
                    and abs(m["last_ts"] - a.timestamp) <= dedupe_window_s), None)
        if dup:
            dup["count"] += 1
            dup["last_ts"] = a.timestamp
            continue
        merged.append({"icao": a.icao, "callsign": a.callsign, "kind": a.kind,
                       "severity": a.severity, "detail": a.detail, "first_ts": a.timestamp,
                       "last_ts": a.timestamp, "count": 1, "anomaly": a.to_dict()})
    for m in merged:
        # priority = severity, nudged up by persistence (repeat sightings)
        m["priority"] = _SEV_RANK.get(m["severity"], 0) + min(2, m["count"] - 1) * 0.5
        m["confidence"] = "high" if m["count"] >= 3 else "medium" if m["count"] == 2 else "low"
    merged.sort(key=lambda m: (m["priority"], m["last_ts"]), reverse=True)
    return merged


# --- 2. correlate ------------------------------------------------------------
def correlate(anomalies: list, sensor_events: list[SensorEvent], *,
              window_s: float = 60.0) -> list[dict]:
    """Fuse each anomaly with other local sensor events close in time (and space, if known).
    Builds a small evidence bundle and a confidence note - pattern-of-life, not targeting."""
    out = []
    for a in anomalies:
        hits = []
        for ev in sensor_events:
            if abs(ev.timestamp - a.timestamp) > window_s:
                continue
            note = f"{ev.source}:{ev.type}"
            hits.append({"source": ev.source, "type": ev.type, "detail": ev.detail,
                         "dt_s": round(ev.timestamp - a.timestamp, 1), "note": note})
        out.append({
            "anomaly": a.to_dict(),
            "correlated_events": hits,
            "corroborated": bool(hits),
            "confidence": "high" if len(hits) >= 2 else "medium" if hits else "low",
            "evidence_count": 1 + len(hits),
        })
    return out


# --- 3. recommend (advisory only) -------------------------------------------
_PLAYBOOK = {
    "emergency_squawk": [
        ("escalate_authority", "Notify ATC / the responsible aviation authority of the "
         "emergency squawk; this is theirs to action.", "immediate"),
        ("preserve_evidence", "Snapshot the track and squawk history for the record.", "prompt"),
        ("log", "Log the event with timestamp and aircraft ID.", "immediate"),
    ],
    "callsign_spoof": [
        ("request_identification", "Verify the callsign against secondary ID (Mode S, filed "
         "flight plan) before treating it as hostile.", "prompt"),
        ("correlate", "Correlate with local RF logs / camera to confirm a real contact vs a "
         "data artifact.", "prompt"),
        ("escalate_authority", "If it persists near a sensitive site, hand the report to the "
         "responsible security authority.", "routine"),
    ],
    "loiter": [
        ("cross_cue_camera", "Cue an EO/IR camera to the loiter area to gather identifying "
         "imagery (sensing only).", "prompt"),
        ("correlate", "Correlate the loiter with ground sensors / access-control to build "
         "pattern-of-life.", "prompt"),
        ("notify_operator", "Surface to the operator on watch for a human assessment.", "prompt"),
    ],
    "impossible_kinematics": [
        ("request_identification", "Treat the position as suspect: verify against a second "
         "receiver / secondary radar before trusting the track.", "prompt"),
        ("preserve_evidence", "Snapshot the raw reports around the jump for later analysis of "
         "possible position spoofing or a cloned ICAO.", "prompt"),
        ("correlate", "Correlate with other local sensors to see whether any real contact "
         "exists at either reported position.", "prompt"),
    ],
}
_DEFAULT_PLAY = [
    ("notify_operator", "Surface to the operator for assessment.", "prompt"),
    ("log", "Log the anomaly with timestamp.", "routine"),
    ("continue_monitoring", "Keep monitoring; no action warranted yet.", "routine"),
]


def recommend(anomaly_kind: str, severity: str = "medium") -> list[Recommendation]:
    """Advisory courses of action for a HUMAN operator. Never commands an effector."""
    plays = _PLAYBOOK.get(anomaly_kind, _DEFAULT_PLAY)
    recs = [Recommendation(action=a, text=t, urgency=u) for (a, t, u) in plays]
    if severity in ("critical", "high") and not any(r.action == "escalate_authority" for r in recs):
        recs.insert(0, Recommendation("escalate_authority",
                                      "High severity - consider handing off to the responsible "
                                      "authority.", "immediate"))
    _assert_advisory(recs)
    return recs


# --- full decision-support report -------------------------------------------
def assess(result, sensor_events: list[SensorEvent] | None = None,
           *, window_s: float = 60.0) -> dict:
    """One-call decision SUPPORT: triage + correlate + per-incident advisory recommendations.
    Output is for a human; `human_authorization_required` is always True."""
    anomalies = getattr(result, "anomalies", result)
    sensor_events = sensor_events or []
    ranked = triage(anomalies)
    corr = {id(a): c for a, c in zip(anomalies, correlate(anomalies, sensor_events, window_s=window_s))}
    by_key = {(a.icao, a.kind, a.timestamp): a for a in anomalies}
    incidents = []
    for m in ranked:
        a = by_key.get((m["icao"], m["kind"], m["last_ts"])) or by_key.get((m["icao"], m["kind"], m["first_ts"]))
        c = corr.get(id(a)) if a is not None else None
        incidents.append({
            "icao": m["icao"], "callsign": m["callsign"], "kind": m["kind"],
            "severity": m["severity"], "priority": m["priority"], "confidence": m["confidence"],
            "detail": m["detail"], "repeat_count": m["count"],
            "correlation": c or {"correlated_events": [], "corroborated": False},
            "recommendations": [r.to_dict() for r in recommend(m["kind"], m["severity"])],
        })
    return {
        "scope": SCOPE,
        "human_authorization_required": True,
        "incident_count": len(incidents),
        "incidents": incidents,
    }


# --- loaders for external local sensor logs ---------------------------------
def load_sensor_events(path_or_text: str) -> list[SensorEvent]:
    """Load other local sensor records (CSV or JSON) for correlation.

    Accepts a path to a ``.csv``/``.json`` file, or the raw CSV/JSON text
    directly. Empty or whitespace-only input yields no events (rather than an
    opaque parse error). Malformed JSON/CSV raises ``ValueError``.
    """
    if path_or_text is None:
        return []
    text = path_or_text
    is_path = ("\n" not in path_or_text
               and path_or_text.strip()[:1] not in ("[", "{")
               and path_or_text.strip() != "")
    if is_path:
        # Treat as a filesystem path; propagate a clear FileNotFoundError/OSError.
        with open(path_or_text, encoding="utf-8") as fh:
            text = fh.read()

    stripped = text.strip()
    if not stripped:
        return []

    is_json = stripped[:1] in ("[", "{")
    is_csv = path_or_text.lower().endswith(".csv") or (not is_json and "," in text)
    try:
        if is_json:
            rows = json.loads(text)
        elif is_csv:
            rows = list(csv.DictReader(io.StringIO(text)))
        else:
            rows = []
    except (json.JSONDecodeError, csv.Error) as e:
        raise ValueError(f"could not parse sensor events: {e}") from e
    if isinstance(rows, dict):
        rows = rows.get("events", [])
    out = []
    for r in rows:
        try:
            out.append(SensorEvent(
                timestamp=float(r.get("timestamp") or r.get("ts") or 0),
                source=str(r.get("source") or r.get("sensor") or "sensor"),
                type=str(r.get("type") or r.get("event") or ""),
                detail=str(r.get("detail") or r.get("description") or ""),
                lat=float(r["lat"]) if r.get("lat") not in (None, "") else None,
                lon=float(r["lon"]) if r.get("lon") not in (None, "") else None,
            ))
        except (TypeError, ValueError):
            continue
    return out
