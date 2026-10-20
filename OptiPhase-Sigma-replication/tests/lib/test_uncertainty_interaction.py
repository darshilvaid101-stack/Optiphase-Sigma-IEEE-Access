"""Checks for the pairwise interaction normalized by the canonical cost, using hand-computed values."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from lib.uncertainty import interaction_per_kernel  # noqa: E402

PASSES = ("a", "b")
KERNEL = "kernel"
BASELINE_NS = 1000.0


def observation(singles, pairs, kernel=KERNEL):
    """One kernel's deltas; pair deltas not given in `pairs` are zero."""
    return {
        "kernel": kernel,
        "single": singles,
        "pair": {(first, second): pairs.get((first, second), 0.0) for first in PASSES for second in PASSES},
    }


class InteractionTests(unittest.TestCase):
    def test_interaction_is_pair_delta_minus_both_single_deltas_over_baseline(self):
        values = interaction_per_kernel(
            [observation({"a": 10.0, "b": 20.0}, {("a", "b"): 50.0})], PASSES, {KERNEL: BASELINE_NS},
        )
        self.assertAlmostEqual(values[("a", "b")][0], (50.0 - 10.0 - 20.0) / BASELINE_NS)

    def test_additive_pair_has_zero_interaction(self):
        values = interaction_per_kernel(
            [observation({"a": 10.0, "b": 20.0}, {("a", "b"): 30.0})], PASSES, {KERNEL: BASELINE_NS},
        )
        self.assertEqual(values[("a", "b")][0], 0.0)

    def test_idempotent_self_pair_has_minus_its_single_effect(self):
        values = interaction_per_kernel(
            [observation({"a": -30.0, "b": 0.0}, {("a", "a"): -30.0})], PASSES, {KERNEL: BASELINE_NS},
        )
        self.assertAlmostEqual(values[("a", "a")][0], 30.0 / BASELINE_NS)

    def test_each_kernel_is_normalized_by_its_own_baseline(self):
        observations = [
            observation({"a": 10.0, "b": 20.0}, {("a", "b"): 50.0}, kernel="small"),
            observation({"a": 10.0, "b": 20.0}, {("a", "b"): 50.0}, kernel="large"),
        ]
        values = interaction_per_kernel(observations, PASSES, {"small": 1000.0, "large": 2000.0})
        self.assertAlmostEqual(values[("a", "b")][1], values[("a", "b")][0] / 2)


if __name__ == "__main__":
    unittest.main()
