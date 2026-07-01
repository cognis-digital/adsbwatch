"""Scenario 15 - tuning the loiter detector for your site.

Loiter detection has three knobs: minimum track points, maximum orbit radius,
and minimum cumulative turn. This demo runs the same orbiting track through the
real engine at three sensitivities to show how tightening or loosening the knobs
changes what counts as a loiter. Offline, stdlib only.
"""
import math

from _common import rule, sub


def _orbit(icao="ORBIT1", n=12, r=0.01, cx=38.5, cy=-77.0):
    from adsbwatch.core import Observation
    return [Observation(timestamp=i * 30, icao=icao, callsign="N1",
                        lat=cx + r * math.cos(2 * math.pi * i / n),
                        lon=cy + r * math.sin(2 * math.pi * i / n), altitude=4500)
            for i in range(n)]


def _count_loiter(obs, **kw):
    from adsbwatch.core import analyze
    return sum(1 for a in analyze(obs, **kw).anomalies if a.kind == "loiter")


def main() -> None:
    rule("LOITER TUNING  -  three knobs, one orbiting track")

    orbit = _orbit()  # ~0.6 NM radius, full 360deg circle, 12 points

    sub("Default settings (min 6 pts, <=5 NM radius, >=270deg turn)")
    print(f"  loiter detections: {_count_loiter(orbit)}")

    sub("Stricter turn requirement (>=720deg = two full orbits)")
    print(f"  loiter detections: {_count_loiter(orbit, loiter_min_turn_deg=720)}")
    print("  -> a single 360deg orbit no longer qualifies")

    sub("Tighter radius gate (<=0.1 NM) rejects even a small orbit")
    print(f"  loiter detections: {_count_loiter(orbit, loiter_radius_nm=0.1)}")

    sub("Fewer points required (min 4) is more sensitive")
    short = _orbit(n=5)
    print(f"  5-point orbit @ default min-points: "
          f"{_count_loiter(short, loiter_min_points=6)}")
    print(f"  5-point orbit @ min-points=4:       "
          f"{_count_loiter(short, loiter_min_points=4)}")

    sub("Takeaway")
    print("  Same track, same engine - the analyst dials sensitivity to the site.")
    print("  A busy holding stack wants loose knobs; a quiet restricted zone wants")
    print("  tight ones. Nothing is hard-coded to one operational context.")
    assert _count_loiter(orbit) == 1


if __name__ == "__main__":
    main()
