"""Replacements for R2 passes that crash LLVM 23 on a specific kernel. The table is config/llvm_newpm_crash_replacements.json.

The crashed sweep is skipped, and a single replacement sweep takes its place under a new index. Nothing is substituted
silently: the audit keeps the crash, and the table keeps the evidence.
"""

import json

from lib.kernel_registry import REPO_ROOT
from lib.pipeline_plans import SweepPlan

CRASH_REPLACEMENTS_PATH = REPO_ROOT / "config" / "llvm_newpm_crash_replacements.json"


def load_replacements():
    return json.loads(CRASH_REPLACEMENTS_PATH.read_text(encoding="utf-8"))["replacements"]


def skipped_sweep_ids():
    """Sweep IDs of the crashed passes; they are never run again."""
    return {entry["crashed_sweep_id"] for entry in load_replacements()}


def replacement_items(kernels):
    """Yield (sweep_id, kernel, plan) for each replacement whose kernel is among `kernels`."""
    by_kernel_id = {kernel.kernel_id: kernel for kernel in kernels}
    for entry in load_replacements():
        kernel = by_kernel_id.get(entry["kernel_id"])
        if kernel is None:
            continue
        plan = SweepPlan("R2", entry["replacement_pass"], entry["replacement_stage"], entry["replacement_stage"])
        yield entry["replacement_sweep_id"], kernel, plan
