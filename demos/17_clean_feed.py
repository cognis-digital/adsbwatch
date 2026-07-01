"""Scenario 17 - the quiet-day baseline: a clean feed says so.

A detector is only trustworthy if it stays silent when nothing is wrong. This
demo builds a feed of ordinary transiting traffic - normal squawks, consistent
callsigns, straight-line tracks, sane speeds - and shows the engine reports zero
anomalies and a clean decision-support assessment. Offline, stdlib only.
"""
from _common import rule, sub


def main() -> None:
    from adsbwatch.core import Observation, analyze
    from adsbwatch import decision

    rule("CLEAN FEED  -  no false positives on ordinary traffic")

    # Three airliners transiting normally: single callsign each, 1200 squawk,
    # straight tracks, ~450 kt.
    obs = []
    tracks = [("AAA001", "UAL10", 40.0, -74.0),
              ("BBB002", "DAL20", 33.5, -84.4),
              ("CCC003", "SWA30", 41.9, -87.9)]
    for icao, cs, lat0, lon0 in tracks:
        for i in range(6):
            obs.append(Observation(timestamp=i * 60, icao=icao, callsign=cs,
                                   lat=lat0 + i * 0.1, lon=lon0 - i * 0.1,
                                   altitude=37000, squawk="1200"))

    result = analyze(obs)
    sub("Analysis of ordinary traffic")
    print(f"  {result.observations} reports / {result.aircraft} aircraft -> "
          f"{len(result.anomalies)} anomaly/anomalies")

    report = decision.assess(result)
    sub("Decision support on a clean scan")
    print(f"  incidents: {report['incident_count']}")

    sub("Why this scenario matters")
    print("  Emergency-squawk, callsign-spoof, loiter and impossible-kinematics")
    print("  detectors all stay silent here. A tool that cried wolf on normal")
    print("  transits would be useless at a busy site - this is the baseline.")
    assert len(result.anomalies) == 0
    assert report["incident_count"] == 0


if __name__ == "__main__":
    main()
