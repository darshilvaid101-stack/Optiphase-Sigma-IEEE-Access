"""The Z3 encoder agrees with the reference semantics on every case of widths 1 to 3."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from lib.z3_encoding_agreement import run_agreement  # noqa: E402

TESTED_WIDTH = 3


class EncodingAgreementTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result = run_agreement(TESTED_WIDTH)

    def test_every_case_agrees_with_the_reference(self):
        self.assertEqual(self.result["total_mismatches"], 0, self.result["first_mismatches"])

    def test_multiplication_overflow_is_covered(self):
        self.assertIn("mul nsw", self.result["families"])

    def test_shift_exactness_is_covered(self):
        self.assertIn("lshr exact", self.result["families"])

    def test_disjoint_or_is_covered(self):
        self.assertIn("or disjoint", self.result["families"])

    def test_non_negative_zext_is_covered(self):
        self.assertIn("zext nneg", self.result["families"])

    def test_samesign_comparison_is_covered(self):
        self.assertIn("icmp samesign", self.result["families"])


if __name__ == "__main__":
    unittest.main()
