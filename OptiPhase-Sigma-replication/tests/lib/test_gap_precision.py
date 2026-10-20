"""Tests for the gap-precision recount: Wilson intervals with known values, and the recorded audit it must reproduce."""

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from audit_gap_precision import AUDIT_PATH, SAMPLE_PATH, build_report, differences, load_csv, wilson_interval  # noqa: E402


class WilsonIntervalTests(unittest.TestCase):
    def test_candidate_interval_matches_published_value(self):
        self.assertEqual(wilson_interval(62, 150), [0.3377, 0.4933])

    def test_refined_interval_matches_published_value(self):
        self.assertEqual(wilson_interval(32, 75), [0.321, 0.5395])

    def test_zero_successes_gives_zero_lower_bound(self):
        self.assertEqual(wilson_interval(0, 10)[0], 0.0)


class RecordedAuditTests(unittest.TestCase):
    def test_recount_reproduces_stored_candidate_and_refined_tiers(self):
        stored = json.loads(AUDIT_PATH.read_text(encoding="utf-8"))
        report = build_report(load_csv(SAMPLE_PATH), stored)
        self.assertEqual(differences(report, stored), [])


if __name__ == "__main__":
    unittest.main()
