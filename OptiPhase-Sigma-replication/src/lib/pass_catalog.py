"""NewPM pass catalogue: the canonical pass list, nesting wrappers, and per-pass validity on this LLVM."""

import json

from lib.kernel_registry import REPO_ROOT

PASS_LIST_PATH = REPO_ROOT / "config" / "llvm_newpm_84_passes.json"
VALIDITY_PATH = REPO_ROOT / "config" / "llvm_newpm_pass_validity.json"
LEVEL_WRAPPERS = {
    "Function": "function({})",
    "Loop": "function(loop({}))",
    "CGSCC": "cgscc({})",
    "Module": "{}",
}
# LLVM 23 provides MemorySSA to LICM only through the loop-mssa adaptor, which must wrap the loop pipeline.
STAGE_OVERRIDES = {"licm": "function(loop-mssa(loop(licm)))"}
# unify-loop-exits makes opt segfault on two gsm kernels. The campaign runs newgvn in its slot on every kernel, so each
# kernel executes the same R2 passes.
PRE_CAMPAIGN_REPLACEMENTS = {"unify-loop-exits": ("newgvn", "function(newgvn)")}


def canonical_passes():
    return json.loads(PASS_LIST_PATH.read_text(encoding="utf-8"))["passes"]


def stage_text(entry):
    """Return the opt pipeline text that runs one canonical pass at its own nesting level."""
    if entry["name"] in STAGE_OVERRIDES:
        return STAGE_OVERRIDES[entry["name"]]
    return LEVEL_WRAPPERS[entry["level"]].format(entry["name"])


def load_validity():
    return json.loads(VALIDITY_PATH.read_text(encoding="utf-8"))["passes"]


def valid_stages():
    """Return (pass_name, stage_text) for every canonical pass that this LLVM accepts, after the pre-campaign replacements."""
    stages = []
    for row in load_validity():
        if row["valid"]:
            stages.append(PRE_CAMPAIGN_REPLACEMENTS.get(row["name"], (row["name"], row["stage"])))
    return stages


def stage_by_name():
    return {entry["name"]: stage_text(entry) for entry in canonical_passes()}
