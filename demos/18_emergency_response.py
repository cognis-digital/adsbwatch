"""Scenario 18 - the 7700: emergency squawk to advisory hand-off.

The headline event on any feed is an emergency squawk (7500 hijack, 7600 radio
failure, 7700 general emergency). This demo isolates the emergency, shows how it
ranks to the top of the triage queue, and prints the ADVISORY hand-off to the
responsible aviation authority - the operator actions it. Offline, stdlib only.
"""
from _common import rule, sub, load_feed, fmt_ts


def main() -> None:
    from adsbwatch.core import analyze, SQUAWK_MEANINGS
    from adsbwatch import decision

    rule("EMERGENCY RESPONSE  -  the 7700 goes to the top")

    sub("Emergency squawk reference")
    for code, meaning in SQUAWK_MEANINGS.items():
        print(f"  {code}  {meaning}")

    result = analyze(load_feed())
    emergencies = [a for a in result.anomalies if a.kind == "emergency_squawk"]
    sub(f"Emergencies on the feed: {len(emergencies)}")
    for a in emergencies:
        print(f"  {a.severity:<8} ICAO {a.icao} {a.callsign or '-'} @ {fmt_ts(a.timestamp)}")
        print(f"    {a.detail}")

    ranked = decision.triage(result.anomalies)
    sub("Triage queue - emergency should rank first")
    top = ranked[0]
    print(f"  top: {top['kind']} {top['icao']} (P{top['priority']}, {top['severity']})")

    sub("Advisory hand-off (the authority actions it, not us)")
    for r in decision.recommend("emergency_squawk", "critical"):
        print(f"    - [{r.urgency}] {r.action}: {r.text}")

    assert emergencies, "sample feed carries a 7700 emergency"
    assert top["kind"] == "emergency_squawk"
    # the hand-off is advisory only
    for r in decision.recommend("emergency_squawk", "critical"):
        assert r.action in decision._ALLOWED_ACTIONS


if __name__ == "__main__":
    main()
