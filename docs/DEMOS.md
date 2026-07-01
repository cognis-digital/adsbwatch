# Demos

Twenty runnable scenarios in [`../demos/`](../demos/), each targeting a different
audience or capability. Every scenario is **offline** and uses the **real**
adsbwatch API: it parses a bundled sample ADS-B feed (or the committed OpenSky
snapshot) and runs the actual engine — no fabricated functions, no network.

```bash
python demos/run_all.py             # all twenty, end to end (exits 0)
python demos/06_impossible_kinematics.py   # or just one
```

> Run with `PYTHONUTF8=1` on Windows for clean output. Each scenario exits 0.

## Audience / capability map

| # | Scenario | Audience | Real API exercised |
|---|----------|----------|--------------------|
| 1 | [`01_anomaly_scan.py`](../demos/01_anomaly_scan.py) | OSINT / aviation analysts | `core.parse_csv`, `core.analyze`, `AnalysisResult` |
| 2 | [`02_callsign_spoofing.py`](../demos/02_callsign_spoofing.py) | Journalists / OSINT investigators | `core.analyze`, `Anomaly.to_dict` (JSON evidence) |
| 3 | [`03_force_protection.py`](../demos/03_force_protection.py) | Defense / force-protection | `decision.assess`, `SensorEvent`, triage + correlate |
| 4 | [`04_intel_export.py`](../demos/04_intel_export.py) | Researchers / SOC analysts | `intel.export` → GeoJSON + STIX 2.1 |
| 5 | [`05_live_feed_offline.py`](../demos/05_live_feed_offline.py) | Edge / air-gap operators | `feeds.fetch_observations(offline=True)`, `core.analyze` |
| 6 | [`06_impossible_kinematics.py`](../demos/06_impossible_kinematics.py) | Spoofing hunters | `core.analyze` impossible-kinematics detector |
| 7 | [`07_geojson_map.py`](../demos/07_geojson_map.py) | GIS analysts | `intel.to_geojson` / `intel.export` |
| 8 | [`08_stix_tip.py`](../demos/08_stix_tip.py) | Threat-intel teams | `intel.to_stix`, reference-integrity check |
| 9 | [`09_region_clip.py`](../demos/09_region_clip.py) | Sector watch | `feeds.fetch_observations(region=…)` |
| 10 | [`10_airgap_snapshot.py`](../demos/10_airgap_snapshot.py) | Disconnected enclaves | `datafeeds.snapshot_export` / `snapshot_import` |
| 11 | [`11_triage_queue.py`](../demos/11_triage_queue.py) | Watch officers | `decision.triage` (rank + dedupe) |
| 12 | [`12_sensor_fusion.py`](../demos/12_sensor_fusion.py) | Multi-INT fusion | `decision.load_sensor_events`, `decision.correlate` |
| 13 | [`13_advisory_playbook.py`](../demos/13_advisory_playbook.py) | Policy / oversight | `decision.recommend`, `_assert_advisory` scope guard |
| 14 | [`14_malformed_input.py`](../demos/14_malformed_input.py) | Robustness / QA | `core.parse_records` error paths, loader hardening |
| 15 | [`15_loiter_tuning.py`](../demos/15_loiter_tuning.py) | Site tuning | `core.analyze` loiter knobs |
| 16 | [`16_full_pipeline.py`](../demos/16_full_pipeline.py) | End-to-end | ingest → analyse → assess → export |
| 17 | [`17_clean_feed.py`](../demos/17_clean_feed.py) | Baseline / false-positive check | `core.analyze`, `decision.assess` on clean traffic |
| 18 | [`18_emergency_response.py`](../demos/18_emergency_response.py) | Emergency handling | `SQUAWK_MEANINGS`, triage, advisory hand-off |
| 19 | [`19_cli_exit_codes.py`](../demos/19_cli_exit_codes.py) | Automation / CI | `cli.main` exit codes (0 / 1 / 2) |
| 20 | [`20_spoof_combo.py`](../demos/20_spoof_combo.py) | Correlated spoofing | callsign-spoof + impossible-kinematics together |

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

## 6. Impossible kinematics — *a track that teleports is a spoof*
**Spoofing hunters.** Builds a single ICAO that "jumps" JFK→Heathrow in 60 s and
shows the impossible-kinematics detector flagging it while a normally transiting
airliner is left alone. Demonstrates the tunable ground-speed ceiling
(`--max-speed`, `0` to disable).

## 7. GeoJSON for maps — *drop anomalies onto Leaflet / QGIS*
**GIS analysts.** Prints the exact GeoJSON `FeatureCollection` (coordinates in
`[lon, lat]` order) with each anomaly's full properties, ready for a web/desktop
map.

## 8. STIX 2.1 for TIPs — *a resolvable threat-report bundle*
**Threat-intel teams.** Emits the STIX 2.1 bundle and verifies every `report`
reference resolves and every object is 2.1-compliant and id-prefixed — a broken
TIP import is worse than none.

## 9. Region clip — *analyse only your sector*
**Sector watch.** Runs the cached snapshot globally, then clipped to a lat/lon
bounding box, showing the out-of-sector contact dropped during ingest before the
engine spends a cycle on it.

## 10. Air-gap snapshot — *sneakernet the feed cache*
**Disconnected enclaves.** Full `snapshot_export` → carry → `snapshot_import`
round-trip between two temp cache dirs, then serves and analyses the feed on the
"air-gapped" side — proving the cache, not the feed source, crossed the gap.

## 11. Triage queue — *worst-first, duplicates merged*
**Watch officers.** Runs `decision.triage()` to produce a ranked incident queue,
merging near-duplicate repeats into a single higher-confidence line.

## 12. Sensor fusion — *ADS-B + camera + RF on one timeline*
**Multi-INT fusion.** Correlates an anomaly with committed local-sensor records
via `decision.correlate()`, raising confidence when independent sensors agree —
pattern-of-life, not targeting.

## 13. Advisory playbook — *the operator decides, always*
**Policy / oversight.** Prints the advisory course-of-action playbook for every
anomaly kind and demonstrates the enforced scope guard rejecting an effector
action. No weapons/jammers/interceptors, ever; human-in-the-loop.

## 14. Malformed input — *fail loud, not silent*
**Robustness / QA.** Walks the tolerated paths (blank/garbage optional fields,
empty sensor logs) and the loudly-rejected ones (missing ICAO, bad timestamp,
malformed JSON) — the tool never silently corrupts a feed.

## 15. Loiter tuning — *three knobs, one orbiting track*
**Site tuning.** Runs the same orbit through the engine at several sensitivities
(min points, max radius, min turn) to show how an analyst dials loiter detection
to their operational context.

## 16. Full pipeline — *ingest → analyse → decide → export*
**End-to-end.** One pass through every layer of the real API over the bundled
feed and sensor log, with a compact summary at each stage.

## 17. Clean feed — *no false positives on ordinary traffic*
**Baseline.** Ordinary transiting traffic yields zero anomalies and a clean
assessment — the silence that makes the alerts trustworthy.

## 18. Emergency response — *the 7700 goes to the top*
**Emergency handling.** Isolates the emergency squawk, shows it ranking first in
triage, and prints the advisory hand-off to the responsible aviation authority.

## 19. CLI exit codes — *wire adsbwatch into a pipeline*
**Automation / CI.** Calls the real CLI on clean / dirty / missing feeds to show
the `0` / `2` / `1` exit codes you branch on in a cron job or CI gate.

## 20. Spoof combo — *two identities AND a teleport, one ICAO*
**Correlated spoofing.** A single hardware address that both wears two callsigns
and jumps the Atlantic trips two independent detectors at once — corroborating
evidence of a manufactured track.

## 21. Airspace incursion — *did a track enter a monitored volume?*
**Airspace monitoring.** Loads offline restricted zones (a circle range and a
polygon TFR, altitude-banded) and reports which aircraft entered an active zone —
descriptive situational awareness for a human, never targeting.

## 22. Pattern of life — *what is the behaviour over time?*
**Analytics.** Rolls the feed up into per-aircraft profiles (dwell, track length,
callsigns/squawks) and finds aircraft making recurring visits near a point of
interest around a monitored site.

## 23. KML export — *open the picture in Google Earth / QGIS*
**GIS.** Emits severity-styled KML placemarks for every geolocated anomaly, then
parses it back to prove the document is well-formed.

## 24. CoT / ATAK — *push the picture to a TAK common operating picture*
**TAK.** Emits Cursor-on-Target events (neutral/unknown air tracks, `a-u-A`) for
ATAK/WinTAK/TAK Server — shared awareness for an operator, not a hostile
designation.

---

Each demo prints clear, narrated output and exits 0, so they double as smoke
tests — `tests/test_demos.py` runs every scenario under `pytest`.
