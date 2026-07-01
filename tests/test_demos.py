"""Tests that the bundled demo scenarios run offline and exit 0.

The demos double as smoke tests: each imports the real adsbwatch API and runs
against a committed sample feed / offline OpenSky snapshot. No network.
"""

import importlib
import os
import sys
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEMO_DIR = os.path.join(REPO_ROOT, "demos")
sys.path.insert(0, REPO_ROOT)
sys.path.insert(0, DEMO_DIR)

SCENARIOS = [
    "01_anomaly_scan",
    "02_callsign_spoofing",
    "03_force_protection",
    "04_intel_export",
    "05_live_feed_offline",
    "06_impossible_kinematics",
    "07_geojson_map",
    "08_stix_tip",
    "09_region_clip",
    "10_airgap_snapshot",
    "11_triage_queue",
    "12_sensor_fusion",
    "13_advisory_playbook",
    "14_malformed_input",
    "15_loiter_tuning",
    "16_full_pipeline",
    "17_clean_feed",
    "18_emergency_response",
    "19_cli_exit_codes",
    "20_spoof_combo",
    "21_airspace_incursion",
    "22_pattern_of_life",
    "23_kml_export",
    "24_cot_atak",
]


class TestDemoScenarios(unittest.TestCase):
    def test_each_scenario_runs(self):
        for name in SCENARIOS:
            with self.subTest(scenario=name):
                mod = importlib.import_module(name)
                self.assertTrue(hasattr(mod, "main"), f"{name} has no main()")
                # main() returns None and must not raise.
                mod.main()

    def test_run_all_exits_zero(self):
        run_all = importlib.import_module("run_all")
        self.assertEqual(run_all.main(), 0)


if __name__ == "__main__":
    unittest.main()
