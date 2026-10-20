"""The R5 sequence table: spelling variants count as one sequence, and each side of loop-vectorize is counted separately."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from lib.manuscript_tables import logical_pass_names, r5_sequence_table, ruled_table  # noqa: E402

R5_ROWS = [
    {"regime_id": "R5", "pass_sequence_str": "function(simplifycfg),function(loop-vectorize),function(dce)"},
    {"regime_id": "R5",
     "pass_sequence_str": "function(simplifycfg),function(loop-vectorize),function(instcombine<no-verify-fixpoint>)"},
    {"regime_id": "R5", "pass_sequence_str": "function(loop-vectorize)"},
    {"regime_id": "R1", "pass_sequence_str": "default<O2>"},
]


class LogicalPassNameTests(unittest.TestCase):
    def test_a_spelling_marker_is_removed(self):
        self.assertEqual(
            logical_pass_names("function(instcombine<no-verify-fixpoint>),function(loop-vectorize)"),
            ["instcombine", "loop-vectorize"],
        )


class R5SequenceTableTests(unittest.TestCase):
    def setUp(self):
        self.table = r5_sequence_table(R5_ROWS)

    def test_pre_pivot_sequences_are_counted_per_sweep(self):
        self.assertIn("Pre-pivot & simplifycfg & 2 \\\\", self.table)

    def test_an_empty_pre_pivot_side_is_named_none(self):
        self.assertIn("Pre-pivot & none & 1 \\\\", self.table)

    def test_a_retried_spelling_counts_with_its_sequence(self):
        self.assertIn("Post-pivot & instcombine & 1 \\\\", self.table)

    def test_regimes_other_than_r5_are_not_counted(self):
        self.assertNotIn("default", self.table)

    def test_none_is_listed_first_on_each_side(self):
        pre_rows = [line for line in self.table.splitlines() if line.startswith("Pre-pivot")]
        self.assertTrue(pre_rows[0].startswith("Pre-pivot & none"))

    def test_the_table_is_centred(self):
        self.assertIn("\\centering", self.table)


class RuledTableCentringTests(unittest.TestCase):
    def test_every_generated_table_is_centred(self):
        table = ruled_table("A caption.", "tab:example", ["Name"], [["value"]], "l")
        self.assertIn("\\centering", table)


if __name__ == "__main__":
    unittest.main()
