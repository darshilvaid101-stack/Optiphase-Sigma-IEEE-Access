"""The R6 planner must pick the highest-scoring chains, break ties deterministically, and return the requested count."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from lib.regime6_planner import plan_regime6, score_sequence  # noqa: E402


def uniform_matrix(passes, value):
    return {(first, second): value for first in passes for second in passes}


class PlannerTests(unittest.TestCase):
    def test_highest_scoring_chain_comes_first(self):
        passes = ["a", "b", "c", "d"]
        matrix = uniform_matrix(passes, 0.0)
        matrix[("a", "b")] = 5.0
        matrix[("b", "c")] = 5.0
        self.assertEqual(plan_regime6(matrix, passes, count=1, length=3), [("a", "b", "c")])

    def test_ties_are_broken_lexicographically_and_repeatably(self):
        passes = ["a", "b", "c"]
        matrix = uniform_matrix(passes, 1.0)
        first_run = plan_regime6(matrix, passes, count=3, length=2)
        second_run = plan_regime6(matrix, passes, count=3, length=2)
        self.assertEqual(first_run, second_run)
        self.assertEqual(first_run[0], ("a", "b"))

    def test_requested_count_is_returned_when_enough_chains_exist(self):
        passes = [f"p{i}" for i in range(15)]
        matrix = uniform_matrix(passes, 0.0)
        self.assertEqual(len(plan_regime6(matrix, passes, count=60, length=3)), 60)

    def test_score_sums_consecutive_transitions(self):
        matrix = {("a", "b"): 2.0, ("b", "c"): 3.0}
        self.assertEqual(score_sequence(("a", "b", "c"), matrix), 5.0)


if __name__ == "__main__":
    unittest.main()
