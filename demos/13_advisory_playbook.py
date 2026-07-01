"""Scenario 13 - the human-in-the-loop boundary, made explicit.

For every anomaly kind, adsbwatch can only ever recommend SENSING, NOTIFICATION,
ESCALATION or EVIDENCE actions - things a person does. It has no interface to any
effector and never acts on its own. This demo prints the advisory playbook for
each anomaly kind and asserts every action is on the allow-list. Offline.
"""
from _common import rule, sub


def main() -> None:
    from adsbwatch import decision

    rule("ADVISORY PLAYBOOK  -  the operator decides, always")

    print(f"\n  scope: {decision.SCOPE}\n")
    print(f"  allow-listed actions: {sorted(decision._ALLOWED_ACTIONS)}")

    for kind in ("emergency_squawk", "callsign_spoof", "loiter",
                 "impossible_kinematics"):
        sub(f"kind = {kind}  (severity=high)")
        recs = decision.recommend(kind, "high")
        for r in recs:
            print(f"    - [{r.urgency:<9}] {r.action:<24} {r.text}")
        # Hard line: nothing outside the advisory allow-list, ever.
        for r in recs:
            assert r.action in decision._ALLOWED_ACTIONS, r.action

    sub("The boundary is enforced, not just documented")
    print("  `decision._assert_advisory` rejects any recommendation whose action is")
    print("  not on the allow-list, and the test-suite proves no effector term")
    print("  (engage/fire/jam/intercept/strike/...) can appear in an assessment.")
    try:
        decision._assert_advisory([decision.Recommendation("engage_target", "x", "immediate")])
        raise SystemExit("scope guard failed to reject an effector action!")
    except ValueError:
        print("  confirmed: an 'engage_target' recommendation is rejected.")


if __name__ == "__main__":
    main()
