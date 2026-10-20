"""Retry a compile with the spelling of standalone instcombine that skips LLVM's fixpoint check.

LLVM 23 aborts a standalone `instcombine` on some functions after one iteration, with "did not reach a fixpoint".
The `no-verify-fixpoint` option removes that abort and nothing else. The default spelling is always tried first, and
the variant is used only after the abort. Over the 2,864 completed sweeps that contain a standalone instcombine, the two
spellings produced byte-identical IR in every case.
"""

import dataclasses
import re

from lib.llvm_tools import ToolError

FIXPOINT_FAILURE_TEXT = "did not reach a fixpoint"
VARIANT_SPELLING = "instcombine<no-verify-fixpoint>"
STANDALONE_INSTCOMBINE = re.compile(r"(?<![\w-])instcombine(?![\w<-])")


def fixpoint_variant(plan):
    """The same plan with every standalone instcombine spelled so that the fixpoint check is skipped."""
    return dataclasses.replace(
        plan,
        pass_sequence=STANDALONE_INSTCOMBINE.sub(VARIANT_SPELLING, plan.pass_sequence),
        opt_pipeline=STANDALONE_INSTCOMBINE.sub(VARIANT_SPELLING, plan.opt_pipeline),
    )


def canonical_spelling(pass_sequence):
    """The pass sequence with the retry spelling mapped back to the plan's canonical text, for name lookups."""
    return pass_sequence.replace(VARIANT_SPELLING, "instcombine")


def compile_with_fixpoint_retry(compile_plan, plan):
    """Return (plan_used, compiled). compile_plan(plan) is tried first; the variant is tried only after LLVM's abort."""
    try:
        return plan, compile_plan(plan)
    except ToolError as failure:
        if FIXPOINT_FAILURE_TEXT not in str(failure):
            raise
    variant = fixpoint_variant(plan)
    return variant, compile_plan(variant)
