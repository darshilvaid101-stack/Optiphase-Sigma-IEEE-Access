"""Checks behind the two sweep-level deviations: the standalone-instcombine spelling and the crash replacements.

1. Spelling equivalence. For every completed sweep whose pipeline contains a standalone instcombine, opt is run with
   the default spelling and with the spelling of lib.fixpoint_retry. The SHA-256 of the two outputs must match, so the
   retry cannot change any completed result.
2. Crash evidence. Each crashed pass is run alone on its kernel and must terminate with a signal. Each replacement is
   run alone on its kernel and must succeed.

Writes data/telemetry/sweep_variant_checks.json. The run fails if a spelling pair differs, a crash does not reproduce,
or a replacement does not run. It is CPU-heavy, so it must not run while a timed campaign is running.
"""

import csv
import hashlib
import json
import subprocess
import sys
from pathlib import Path

from lib.build_layout import BUILD_ROOT, kernel_directory_name
from lib.fixpoint_retry import STANDALONE_INSTCOMBINE, fixpoint_variant
from lib.kernel_catalog import all_kernels
from lib.kernel_registry import REPO_ROOT
from lib.pipeline_plans import SweepPlan

OPT_PATH = "/opt/homebrew/opt/llvm/bin/opt"
MASTER_PATH = REPO_ROOT / "data" / "telemetry" / "master_sweeps_28800.csv"
REPORT_PATH = REPO_ROOT / "data" / "telemetry" / "sweep_variant_checks.json"
SCRATCH_ROOT = BUILD_ROOT / "variant-checks"
SIGNAL_RETURN_CODES = (-11, 139)
MISMATCH_LIMIT = 50
ARCHIVED_CRASHES_PATH = REPO_ROOT / "config" / "archive_v1" / "llvm_newpm_crash_replacements_v1.json"
LINKED_NAME = "linked.bc"


def canonical_path(kernel_id, directories):
    return BUILD_ROOT / directories[kernel_id] / "canon.bc"


def archived_crash_evidence():
    """The crashes of the first campaign, which are the evidence for the crash replacements."""
    return json.loads(ARCHIVED_CRASHES_PATH.read_text(encoding="utf-8"))["replacements"]


def mem2reg_only_module(kernel_id, directories):
    """The first campaign's canonical module: mem2reg alone on the linked bitcode, where its crashes were recorded."""
    SCRATCH_ROOT.mkdir(parents=True, exist_ok=True)
    output = SCRATCH_ROOT / f"{directories[kernel_id]}-mem2reg.ll"
    result = run_opt("mem2reg", BUILD_ROOT / directories[kernel_id] / LINKED_NAME, output)
    if result.returncode != 0:
        raise RuntimeError(f"mem2reg failed for {kernel_id}: {result.stderr[-300:]}")
    return output


def run_opt(passes, source, output):
    return subprocess.run(
        [OPT_PATH, f"-passes={passes}", str(source), "-S", "-o", str(output)],
        capture_output=True, text=True, check=False,
    )


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def spelling_report(directories):
    rows = list(csv.DictReader(MASTER_PATH.open(encoding="utf-8", newline="")))
    candidates = [
        row for row in rows
        if STANDALONE_INSTCOMBINE.search(row["pass_sequence_str"]) and "[" not in row["pass_sequence_str"]
    ]
    SCRATCH_ROOT.mkdir(parents=True, exist_ok=True)
    identical, differing, run_failures = 0, [], []
    for row in candidates:
        default_plan = SweepPlan(row["regime_id"], row["sweep_id"], row["pass_sequence_str"], row["pass_sequence_str"])
        variant_plan = fixpoint_variant(default_plan)
        source = canonical_path(row["kernel_id"], directories)
        outputs = {}
        for label, plan in (("default", default_plan), ("variant", variant_plan)):
            output = SCRATCH_ROOT / f"{row['sweep_id']}-{label}.ll"
            result = run_opt(plan.opt_pipeline, source, output)
            if result.returncode != 0:
                run_failures.append({"sweep_id": row["sweep_id"], "spelling": label, "returncode": result.returncode})
                break
            outputs[label] = digest(output)
            output.unlink()
        if len(outputs) == 2:
            if outputs["default"] == outputs["variant"]:
                identical += 1
            else:
                differing.append(row["sweep_id"])
    return {
        "candidates": len(candidates),
        "identical": identical,
        "differing": differing[:MISMATCH_LIMIT],
        "differing_count": len(differing),
        "run_failures": run_failures[:MISMATCH_LIMIT],
        "run_failure_count": len(run_failures),
    }


def crash_report(directories):
    crashes, replacements = [], []
    for entry in archived_crash_evidence():
        source = mem2reg_only_module(entry["kernel_id"], directories)
        SCRATCH_ROOT.mkdir(parents=True, exist_ok=True)
        crash = run_opt(f"function({entry['crashed_pass']})", source, SCRATCH_ROOT / f"{entry['crashed_sweep_id']}-crash.ll")
        crashes.append({
            "sweep_id": entry["crashed_sweep_id"], "kernel_id": entry["kernel_id"],
            "pass": entry["crashed_pass"], "returncode": crash.returncode,
            "reproduced": crash.returncode in SIGNAL_RETURN_CODES,
        })
        replacement = run_opt(entry["replacement_stage"], source, SCRATCH_ROOT / f"{entry['replacement_sweep_id']}.ll")
        replacements.append({
            "sweep_id": entry["replacement_sweep_id"], "kernel_id": entry["kernel_id"],
            "pass": entry["replacement_pass"], "returncode": replacement.returncode,
            "runs": replacement.returncode == 0,
        })
    return crashes, replacements


def main():
    kernels = all_kernels()
    directories = {kernel.kernel_id: kernel_directory_name(kernel) for kernel in kernels}
    spelling = spelling_report(directories)
    crashes, replacements = crash_report(directories)
    passed = (
        spelling["differing_count"] == 0
        and spelling["run_failure_count"] == 0
        and all(entry["reproduced"] for entry in crashes)
        and all(entry["runs"] for entry in replacements)
    )
    report = {"instcombine_spelling": spelling, "crashes": crashes, "replacements": replacements, "passed": passed}
    REPORT_PATH.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    summary = {"passed": passed, "candidates": spelling["candidates"], "identical": spelling["identical"],
               "differing": spelling["differing_count"]}
    print(json.dumps(summary))
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
