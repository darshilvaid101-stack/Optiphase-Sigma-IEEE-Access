"""Re-verify the output digests of the bitcount sweeps under the corrected masking rule.

The first campaign masked only bitcount's timing values. The benchmark also names its fastest and slowest algorithm,
which depends on the same timings, so the digests of canonical runs themselves disagreed.
The rule now also masks those two lines (kernel_registry.BITCOUNT_RANKING). This script rebuilds every bitcount sweep
from its recorded pass sequence, runs it once through the engine's own run path, and compares the digest with the
canonical digest recomputed under the same rule. Timing is not measured here, and the telemetry is not changed.

Writes data/telemetry/bitcount_output_check.json.
"""

import csv
import json
import shutil
import sys
from pathlib import Path

from lib.kernel_catalog import all_kernels
from lib.kernel_registry import REPO_ROOT
from lib.pipeline_plans import SweepPlan
from lib.sweep_compile import compile_phase
from lib.sweep_executor import SWEEP_ROOT, canonical_lowered_executable, prepared_run_directory, timed_run
from task5_z3_verifier_and_math import split_pass_sequence

KERNEL_ID = "mibench/bitcount"
MASTER_PATH = REPO_ROOT / "data" / "telemetry" / "master_sweeps_28800.csv"
REPORT_PATH = REPO_ROOT / "data" / "telemetry" / "bitcount_output_check.json"
CANONICAL_RUNS = 3


def plan_from_row(row):
    pipeline, arguments, attribute = split_pass_sequence(row["pass_sequence_str"])
    return SweepPlan(row["regime_id"], row["sweep_id"], row["pass_sequence_str"], pipeline, attribute, arguments)


def canonical_digest(spec):
    executable = canonical_lowered_executable(spec)
    run_directory, baseline_files = prepared_run_directory(spec)
    digests = [timed_run(spec, executable, run_directory, baseline_files)[1] for _ in range(CANONICAL_RUNS)]
    if len(set(digests)) != 1:
        raise RuntimeError(f"canonical digest is not stable across {CANONICAL_RUNS} runs")
    return digests[0]


def sweep_digest(spec, row):
    plan = plan_from_row(row)
    work_dir = SWEEP_ROOT / "verify" / row["sweep_id"]
    shutil.rmtree(work_dir, ignore_errors=True)
    work_dir.mkdir(parents=True)
    try:
        executable = compile_phase(spec, plan, work_dir)["executable"]
        run_directory, baseline_files = prepared_run_directory(spec)
        return timed_run(spec, executable, run_directory, baseline_files)[1]
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


def main():
    spec = next(kernel for kernel in all_kernels() if kernel.kernel_id == KERNEL_ID)
    rows = [row for row in csv.DictReader(MASTER_PATH.open(encoding="utf-8", newline="")) if row["kernel_id"] == KERNEL_ID]
    reference = canonical_digest(spec)
    matches, mismatches = {}, []
    for row in rows:
        digest = sweep_digest(spec, row)
        matches[row["sweep_id"]] = digest == reference
        if digest != reference:
            mismatches.append(row["sweep_id"])
    report = {
        "kernel_id": KERNEL_ID,
        "rule": "bitcount volatile patterns: Time values, and the Best and Worst algorithm lines",
        "canonical_runs": CANONICAL_RUNS,
        "sweeps_checked": len(rows),
        "sweeps_matching_canonical": sum(matches.values()),
        "mismatched_sweep_ids": mismatches,
        "matches": matches,
    }
    REPORT_PATH.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({key: report[key] for key in ("sweeps_checked", "sweeps_matching_canonical")}))
    return 0 if not mismatches else 1


if __name__ == "__main__":
    sys.exit(main())
