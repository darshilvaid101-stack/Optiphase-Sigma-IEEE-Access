"""Every SAT witness class belongs to exactly one category, and a class without a category is an error, not a dropped witness."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

import analyze_sat_witnesses as analysis  # noqa: E402


def sweep_with(*classes):
    return {"witnesses": [{"class": witness_class} for witness_class in classes]}


class WitnessCategoryTests(unittest.TestCase):
    def test_flag_gain_is_category_a(self):
        counts = analysis.category_counts([sweep_with(analysis.CLASS_FLAG_GAIN)])
        self.assertEqual(counts["A"], 1)

    def test_flag_swap_is_category_a(self):
        counts = analysis.category_counts([sweep_with(analysis.CLASS_FLAG_SWAP)])
        self.assertEqual(counts["A"], 1)

    def test_flag_loss_is_category_b(self):
        counts = analysis.category_counts([sweep_with(analysis.CLASS_FLAG_LOSS)])
        self.assertEqual(counts["B"], 1)

    def test_unchanged_text_is_category_c(self):
        counts = analysis.category_counts([sweep_with(analysis.CLASS_UNCHANGED)])
        self.assertEqual(counts["C"], 1)

    def test_other_change_is_category_c(self):
        counts = analysis.category_counts([sweep_with(analysis.CLASS_OTHER)])
        self.assertEqual(counts["C"], 1)

    def test_total_counts_every_witness_across_sweeps(self):
        records = [
            sweep_with(analysis.CLASS_FLAG_GAIN, analysis.CLASS_OTHER),
            sweep_with(analysis.CLASS_FLAG_LOSS),
            sweep_with(),
        ]
        self.assertEqual(analysis.category_counts(records)["total"], 3)

    def test_unmapped_class_raises_instead_of_being_dropped(self):
        with self.assertRaises(KeyError):
            analysis.category_counts([sweep_with("unclassified")])


if __name__ == "__main__":
    unittest.main()
