# Demos

Five runnable scenarios in [`../demos/`](../demos/), each targeting a different
audience. Every scenario is **offline** and uses the **real** adsbwatch API: it
parses a bundled sample ADS-B feed (or the committed OpenSky snapshot) and runs
the actual engine — no fabricated functions, no network.

```bash
python demos/run_all.py             # all five, end to end (exits 0)
python demos/01_anomaly_scan.py     # or just one
```

> Run with `PYTHONUTF8=1` on Windows for clean output.

## Audience map

| # | Scenario | Audience | Real API exercised |
|---|----------|----------|--------------------|
| 1 | [`01_anomaly_scan.py`](../demos/01_anomaly_scan.py) | OSINT / aviation analysts | `core.parse_csv`, `core.analyze`, `AnalysisResult` |
| 2 | [`02_callsign_spoofing.py`](../demos/02_callsign_spoofing.py) | Journalists / OSINT investigators | `core.analyze`, `Anomaly.to_dict` (JSON evidence) |
| 3 | [`03_force_protection.py`](../demos/03_force_protection.py) | Defense / force-protection | `decision.assess`, `SensorEvent`, triage + correlate |
| 4 | [`04_intel_export.py`](../demos/04_intel_export.py) | Researchers / SOC analysts | `intel.export` → GeoJSON + STIX 2.1 |
| 5 | [`05_live_feed_offline.py`](../demos/05_live_feed_offline.py) | Edge / air-gap operators | `feeds.fetch_observations(offline=True)`, `core.analyze` |

## 1. Anomaly scan — *surface the interesting aircraft first*
**OSINT / aviation analysts.** Runs the engine over the sample feed and walks
every finding worst-first: the `7700` emergency squawk, the ICAO broadcasting
two callsigns, and the 270°+ orbit. Shows the severity ranking and evidence the
engine attaches to each anomaly.

## 2. Callsign spoofing — *one aircraft, two identities*
**Journalists / open-source investigators.** Isolates the spoofing finding —
one transponder hardware address (ICAO) emitting two airline callsigns — and
prints the machine-readable JSON you can cite or hand to a data desk.
Reproducible: same CSV in, same JSON out, offline.

## 3. Force protection — *triage + correlate, operator decides*
**Defense / force-protection.** Builds an aligned ADS-B + local-sensor timeline,
then runs the decision-support layer: triage the loiter, fuse it with a camera
and an RF logger, and emit **advisory** courses of action. Demonstrates the hard
scope — sensing/notification/escalation only, no effectors, human in command.

## 4. Intel export — *GeoJSON for maps, STIX 2.1 for TIPs*
**Researchers / SOC analysts.** Exports the same scan two ways: GeoJSON points
for Leaflet/QGIS/kepler.gl, and a valid STIX 2.1 bundle (location +
observed-data + note under a report) for OpenCTI and other threat-intel
platforms. Zero dependencies.

## 5. Live feed, offline — *air-gap ADS-B over a cached snapshot*
**Edge / air-gap operators.** Points the feed cache at the committed OpenSky
fixture and runs the exact same ingest + engine with `offline=True` — no
network. Proves the disconnected workflow: the feed source changes, the analysis
engine does not.

---

Each demo prints clear, narrated output and exits 0, so they double as smoke
tests — `tests/test_demos.py` runs every scenario under `pytest`.
