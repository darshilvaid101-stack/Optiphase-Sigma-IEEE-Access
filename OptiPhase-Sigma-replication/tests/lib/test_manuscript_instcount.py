"""Checks for the instruction-count interaction and the self-interaction identity, using hand-built telemetry rows."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from lib.manuscript_instcount import instcount_interactions, self_identity_macros  # noqa: E402
from lib.pass_catalog import stage_by_name  # noqa: E402
from lib.pipeline_plans import R3_PASSES  # noqa: E402

KERNEL = "toy__kernel"
CANONICAL_COUNT = 100
STAGES = stage_by_name()
SINGLE_DELTA = -2


def telemetry_row(regime, sequence, delta):
    return {
        "kernel_id": KERNEL,
        "regime_id": regime,
        "pass_sequence_str": sequence,
        "ir_inst_before": str(CANONICAL_COUNT),
        "ir_delta_inst": str(delta),
    }


def telemetry(pair_delta=None):
    """Single rows for every pass, and a row for every ordered pair. Distinct pairs are additive by default, and a self-pair
    is idempotent by default (its second application changes nothing)."""
    overrides = pair_delta or {}
    rows = [telemetry_row("R2", STAGES[name], SINGLE_DELTA) for name in R3_PASSES]
    for first in R3_PASSES:
        for second in R3_PASSES:
            default = SINGLE_DELTA if first == second else 2 * SINGLE_DELTA
            value = overrides.get((first, second), default)
            rows.append(telemetry_row("R3", f"{STAGES[first]},{STAGES[second]}", value))
    return rows


def idempotent_checks():
    per_pass = {name: {"canonical": {"idempotent_kernels": [KERNEL]}} for name in R3_PASSES}
    return {"per_pass": per_pass}


class InstructionCountTests(unittest.TestCase):
    def test_distinct_additive_pairs_have_zero_interaction(self):
        values = instcount_interactions(telemetry())
        for first in R3_PASSES:
            for second in R3_PASSES:
                if first != second:
                    self.assertEqual(values[(first, second)], [0.0])

    def test_interaction_is_pair_change_minus_single_changes_over_canonical_count(self):
        values = instcount_interactions(telemetry(pair_delta={("licm", "dce"): -3}))
        self.assertAlmostEqual(values[("licm", "dce")][0], (-3 + 2 + 2) / CANONICAL_COUNT)

    def test_idempotent_self_pair_equals_minus_its_single_change(self):
        values = instcount_interactions(telemetry())
        self.assertAlmostEqual(values[("gvn", "gvn")][0], -SINGLE_DELTA / CANONICAL_COUNT)

    def test_identity_macros_report_no_mismatch_when_self_pairs_are_idempotent(self):
        macros = "\n".join(self_identity_macros(telemetry(), idempotent_checks()))
        self.assertIn(f"\\newcommand{{\\InstSelfIdentityCases}}{{{len(R3_PASSES)}}}", macros)
        self.assertIn("\\newcommand{\\InstSelfIdentityMismatches}{0}", macros)

    def test_identity_macros_count_a_self_pair_that_breaks_the_identity(self):
        macros = "\n".join(self_identity_macros(telemetry(pair_delta={("licm", "licm"): -3}), idempotent_checks()))
        self.assertIn("\\newcommand{\\InstSelfIdentityMismatches}{1}", macros)


if __name__ == "__main__":
    unittest.main()
