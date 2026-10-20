"""Exact-arithmetic checks for the hypervolume, Pareto, and M_pass operators, using closed-form answers."""

import sys
import unittest
from fractions import Fraction
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from lib.pass_algebra import hypervolume_3d, lie_bracket, m_pass_matrix, pareto_front  # noqa: E402

REFERENCE = (0.5, 0.5, 0.5)


class HypervolumeTests(unittest.TestCase):
    def test_single_point_volume_is_the_box_to_the_reference(self):
        self.assertEqual(hypervolume_3d([(1.0, 1.0, 1.0)], REFERENCE), Fraction(1, 8))

    def test_overlapping_boxes_match_inclusion_exclusion(self):
        volume = hypervolume_3d([(1.0, 1.0, 0.75), (0.75, 0.75, 1.0)], REFERENCE)
        self.assertEqual(volume, Fraction(5, 64))

    def test_points_on_the_reference_plane_contribute_nothing(self):
        volume = hypervolume_3d([(1.0, 0.5, 0.5), (0.5, 1.0, 0.5)], REFERENCE)
        self.assertEqual(volume, Fraction(0))

    def test_dominated_point_does_not_change_the_volume(self):
        single = hypervolume_3d([(1.0, 1.0, 1.0)], REFERENCE)
        with_dominated = hypervolume_3d([(1.0, 1.0, 1.0), (0.6, 0.6, 0.6)], REFERENCE)
        self.assertEqual(single, with_dominated)


class ParetoTests(unittest.TestCase):
    def test_dominated_point_is_removed(self):
        self.assertEqual(pareto_front([(1, 1, 1), (0.5, 0.5, 0.5)]), [(1, 1, 1)])

    def test_incomparable_points_are_both_kept(self):
        front = pareto_front([(1, 0, 0), (0, 1, 0)])
        self.assertEqual(sorted(front), [(0, 1, 0), (1, 0, 0)])


class MPassTests(unittest.TestCase):
    def test_passes_without_effect_give_a_zero_matrix(self):
        observation = {
            "single": {"a": 0.0, "b": 0.0},
            "pair": {("a", "a"): 0.0, ("a", "b"): 0.0, ("b", "a"): 0.0, ("b", "b"): 0.0},
        }
        matrix = m_pass_matrix([observation], ["a", "b"])
        self.assertTrue(all(value == 0.0 for value in matrix.values()))

    def test_additive_pair_gives_zero_transition(self):
        observation = {
            "single": {"a": 10.0, "b": 5.0},
            "pair": {("a", "a"): 20.0, ("a", "b"): 15.0, ("b", "a"): 15.0, ("b", "b"): 10.0},
        }
        matrix = m_pass_matrix([observation], ["a", "b"])
        self.assertAlmostEqual(matrix[("a", "b")], 0.0)

    def test_interfering_pair_gives_the_normalised_transition(self):
        observation = {
            "single": {"a": 10.0, "b": 5.0},
            "pair": {("a", "a"): 20.0, ("a", "b"): 12.0, ("b", "a"): 15.0, ("b", "b"): 10.0},
        }
        matrix = m_pass_matrix([observation], ["a", "b"])
        # dJ(b | a(G)) = 12 - 10 = 2 and dJ(b | G) = 5, so the numerator is -3; the denominator is 10 + 5.
        self.assertAlmostEqual(matrix[("a", "b")], -3.0 / 15.0)

    def test_lie_bracket_of_commuting_passes_is_zero(self):
        self.assertEqual(lie_bracket(90.0, 90.0, 100.0), 0.0)

    def test_lie_bracket_is_normalised_by_the_canonical_cost(self):
        self.assertAlmostEqual(lie_bracket(90.0, 80.0, 100.0), 0.1)


if __name__ == "__main__":
    unittest.main()
