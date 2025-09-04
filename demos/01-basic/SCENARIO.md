# Demo 01 - Basic anomaly scan

This demo runs ADSBWATCH over a small synthetic ADS-B feed (`feed.csv`) that
contains three planted anomalies plus normal traffic.

## The feed

`feed.csv` holds position reports for four aircraft:

| ICAO   | What it is | Anomaly |
|--------|------------|---------|
| A1B2C3 | Airliner declaring an emergency | Squawk **7700** (general emergency) |
| DDEEFF | Same hardware address, two callsigns | **Callsign spoof** (UAL123 then DAL999) |
| 100200 | Aircraft circling a fixed point | **Loiter** (tight radius, >270 deg of turn) |
| ABCDEF | Normal transiting flight | none (control) |

## Run it

```sh
python -m adsbwatch scan demos/01-basic/feed.csv
```

Human-readable table by default. For piping into other tools:

```sh
python -m adsbwatch scan demos/01-basic/feed.csv --format json
```

## Expected result

Three anomalies: one `emergency_squawk` (critical), one `callsign_spoof`
(high), and one `loiter` (medium). The normal flight `ABCDEF` produces no
findings.

Exit code is **2** because anomalies were found (0 = clean, 1 = error), so you
can wire it into a monitor:

```sh
python -m adsbwatch scan feed.csv --format json || echo "ANOMALIES — investigate"
```

## Defensive use only

ADSBWATCH is for monitoring, compliance, and OSINT situational awareness. It
has no targeting or aircraft-control capability and only reads public ADS-B
broadcast data.
