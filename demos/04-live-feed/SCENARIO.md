# Demo 04 — Live ADS-B feed ingestion (OpenSky), air-gap-ready

adsbwatch can pull **live ADS-B state vectors** from the OpenSky Network instead
of reading a CSV, cache them to disk, and re-serve that snapshot **offline** on
disconnected / edge / air-gapped gear. The cached states are converted straight
into the same `Observation` rows the anomaly engine already scans.

Only the `opensky-states` catalog feed is wired in — it is the one authoritative,
keyless feed relevant to aircraft tracking. Endpoints come from the bundled
`adsbwatch/data_feeds_2026.json`; nothing is invented.

## Online (connected sensor)

```bash
# See the wired feed + cache freshness
adsbwatch feeds list

# Fetch the live snapshot and cache it
adsbwatch feeds update opensky-states

# Ingest live airspace and run the full anomaly scan
adsbwatch scan --live --format table

# Clip to a bounding box (LAT0,LON0,LAT1,LON1)
adsbwatch scan --live --region 24,-125,49,-66          # CONUS
```

## Offline / air-gap

```bash
# On the connected box: build a snapshot for sneakernet transfer
COGNIS_FEEDS_CACHE=./snap adsbwatch feeds update opensky-states
python -m adsbwatch.datafeeds snapshot-export feeds.tar.gz

# On the air-gapped box: import + scan with NO network
python -m adsbwatch.datafeeds snapshot-import feeds.tar.gz
adsbwatch scan --live --offline --format table
```

`--offline` serves the cache only and never touches the network — the tool keeps
hunting emergency squawks (7500/7600/7700), callsign spoofing and loiter patterns
over the last cached snapshot.

## Try it against the committed fixture

```bash
export COGNIS_FEEDS_CACHE=$PWD/tests/fixtures/feeds_cache
adsbwatch feeds get opensky-states --offline
adsbwatch scan --live --offline --format table   # surfaces a 7700 emergency
```
