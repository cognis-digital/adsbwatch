"""Scenario 19 - scripting adsbwatch: exit codes drive automation.

adsbwatch is built to sit inside a pipeline: exit 0 = ran, nothing found; exit 2
= anomalies present (the tool's notion of a 'finding'); exit 1 = usage/parse
error. This demo calls the real CLI entrypoint on clean and dirty feeds and shows
the exit code you'd branch on in a cron job or CI gate. Offline, stdlib only.
"""
import os
import tempfile

from _common import rule, sub, FEED_CSV


def main() -> None:
    from adsbwatch.cli import main as cli_main

    rule("CLI EXIT CODES  -  wire adsbwatch into a pipeline")

    # A clean feed (no anomalies) -> exit 0
    clean = os.path.join(tempfile.mkdtemp(), "clean.csv")
    with open(clean, "w", encoding="utf-8") as fh:
        fh.write("timestamp,icao,callsign,lat,lon,squawk\n")
        fh.write("1,ABC001,UAL10,40.0,-74.0,1200\n")

    sub("scan a CLEAN feed")
    rc = cli_main(["scan", clean, "--format", "json"])
    print(f"  exit code = {rc}  (0 = ran, no findings)")
    assert rc == 0

    sub("scan the SAMPLE feed (contains anomalies)")
    rc = cli_main(["scan", FEED_CSV, "--format", "json"])
    print(f"  exit code = {rc}  (2 = anomalies present -> alert)")
    assert rc == 2

    sub("scan a MISSING file")
    rc = cli_main(["scan", os.path.join(os.sep, "no", "such", "feed.csv")])
    print(f"  exit code = {rc}  (1 = usage / parse error)")
    assert rc == 1

    sub("Shell idiom")
    print("  adsbwatch scan feed.csv --format json > out.json")
    print("  case $? in 0) echo clean;; 2) alert out.json;; *) echo error;; esac")


if __name__ == "__main__":
    main()
