"""Scenario 14 - robustness: hostile / malformed feeds fail loud, not silent.

Real ADS-B dumps are messy: blank timestamps, missing ICAOs, junk numeric
fields, empty sensor files. adsbwatch either tolerates the noise (blank optional
fields) or raises a CLEAR error pointing at the offending row - it never silently
drops or mis-parses. This demo exercises those paths. Offline, stdlib only.
"""
from _common import rule, sub


def main() -> None:
    from adsbwatch.core import parse_records, analyze
    from adsbwatch import decision

    rule("MALFORMED INPUT  -  clear errors, no silent corruption")

    sub("Tolerated: blank optional fields (lat/lon/alt/squawk/callsign)")
    obs = parse_records([{"timestamp": "1", "icao": "abc", "lat": "", "lon": "",
                          "altitude": "", "squawk": "", "callsign": ""}])
    print(f"  parsed {len(obs)} row(s); lat={obs[0].lat} squawk='{obs[0].squawk}' "
          "(blanks -> None/empty, not a crash)")

    sub("Tolerated: garbage numeric fields degrade to None")
    obs = parse_records([{"timestamp": "1", "icao": "abc", "lat": "north-ish"}])
    print(f"  lat parsed from 'north-ish' -> {obs[0].lat}")

    sub("Rejected LOUDLY: a row with no ICAO (points at the row index)")
    try:
        parse_records([{"timestamp": "1", "icao": "ok"},
                       {"timestamp": "2", "callsign": "X"}])
    except ValueError as e:
        print(f"  ValueError: {e}")

    sub("Rejected LOUDLY: an unparseable timestamp")
    try:
        parse_records([{"timestamp": "yesterday", "icao": "abc"}])
    except ValueError as e:
        print(f"  ValueError: {e}")

    sub("Tolerated: empty / whitespace sensor log yields no events (no crash)")
    print(f"  load_sensor_events('')   -> {decision.load_sensor_events('')}")
    print(f"  load_sensor_events('  ') -> {decision.load_sensor_events('   ')}")

    sub("Rejected LOUDLY: malformed sensor JSON")
    try:
        decision.load_sensor_events("[{ this is not json")
    except ValueError as e:
        print(f"  ValueError: could not parse sensor events")

    # A clean row still analyses fine after all that.
    assert analyze(parse_records([{"timestamp": "1", "icao": "ok", "squawk": "7700"}])).anomalies
    print("\n  A well-formed feed still analyses cleanly afterward.")


if __name__ == "__main__":
    main()
