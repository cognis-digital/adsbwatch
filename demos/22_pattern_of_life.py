"""Scenario 22 - pattern-of-life analytics over the observation stream.

Rolls the raw position reports up into per-aircraft profiles (first/last seen,
dwell, distinct callsigns/squawks, altitude range, track length) and looks for
aircraft that make recurring visits near a point of interest - the situational
picture an analyst reasons about. Purely descriptive and defensive. Offline.
"""
from _common import rule, sub, load_feed, fmt_ts


def main() -> None:
    from adsbwatch import patterns

    rule("PATTERN OF LIFE  -  per-aircraft profiles + recurring visits")

    observations = load_feed()
    summary = patterns.summarize(observations)

    sub(f"{summary['aircraft']} aircraft over "
        f"{fmt_ts(summary['window']['start'])} -> {fmt_ts(summary['window']['end'])}")
    for p in summary["profiles"]:
        cs = ",".join(p["callsigns"]) or "-"
        print(f"    {p['icao']:<8} {p['reports']:>2} reports  dwell {p['dwell_s']:>5.0f}s "
              f"track {p['track_nm']:>6.1f} NM  callsigns={cs}")

    # Recurring visits near a POI (e.g. a monitored site).
    poi_lat, poi_lon = 40.65, -73.77
    visits = patterns.recurring_visits(observations, poi_lat, poi_lon,
                                       radius_nm=10, min_visits=1)
    sub(f"Aircraft seen near POI ({poi_lat}, {poi_lon}): {len(visits)}")
    for v in visits:
        print(f"    {v['icao']} {v['callsign'] or '-':<8} {v['visits']} visit(s), "
              f"closest {v['closest_nm']} NM")

    assert summary["aircraft"] >= 1


if __name__ == "__main__":
    main()
