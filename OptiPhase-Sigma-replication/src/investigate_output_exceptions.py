"""Reproduce the output exceptions of the rerun.

The sweep audit lists the sweeps whose output digest differs from the canonical digest. For each one, this script rebuilds the
sweep binary with the sweep's own pipeline and runs it and the canonical binary in the same staged run directory. It compares
every file that each run creates. It repeats the comparison for each stage of the pipeline alone, for the optimized IR
interpreted with lli, and for the optimized IR lowered at -O2. The result is written to
data/telemetry/output_exceptions.json.
"""

import csv
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from lib.build_layout import BUILD_ROOT, CANONICAL_NAME, kernel_build_directory  # noqa: E402
from lib.kernel_catalog import all_kernels  # noqa: E402
from lib.kernel_execution import digest_run, invoke, lli_launcher, native_launcher, read_new_files  # noqa: E402
from lib.llvm_tools import run_tool  # noqa: E402
from lib.pipeline_plans import SweepPlan  # noqa: E402
from lib.sweep_compile import compile_phase  # noqa: E402
from lib.sweep_executor import canonical_lowered_executable, prepared_run_directory, remove_extra_files  # noqa: E402

AUDIT_PATH = REPO_ROOT / "data/telemetry/sweep_audit.jsonl"
MASTER_PATH = REPO_ROOT / "data/telemetry/master_sweeps_28800.csv"
OUTPUT_PATH = REPO_ROOT / "data/telemetry/output_exceptions.json"
WORK_ROOT = BUILD_ROOT / "output-exceptions"
OPTIMIZED_LISTING = "opt.ll"
LOWERING_FLAGS = ("-O2", "-filetype=obj")
PIPELINE_SEPARATOR = ","


def exception_rows():
    """The campaign rows of the sweeps whose audit record reports a digest that differs from the canonical digest."""
    sweep_ids = set()
    with AUDIT_PATH.open(encoding="utf-8") as handle:
        for line in handle:
            record = json.loads(line)
            if record.get("status") == "ok" and record.get("digest_matches_canonical") is False:
                sweep_ids.add(record["sweep_id"])
    with MASTER_PATH.open(encoding="utf-8", newline="") as handle:
        rows = [row for row in csv.DictReader(handle) if row["sweep_id"] in sweep_ids]
    return sorted(rows, key=lambda row: row["sweep_id"])


def compare_outputs(first, second):
    """Per-file comparison of the files two runs created: identity, differing bytes, and the largest byte difference."""
    report = {}
    for name in sorted(set(first) | set(second)):
        a, b = first.get(name, b""), second.get(name, b"")
        differing = [index for index in range(min(len(a), len(b))) if a[index] != b[index]]
        report[name] = {
            "identical": a == b,
            "bytes": [len(a), len(b)],
            "differing_bytes": len(differing) + abs(len(a) - len(b)),
            "max_byte_difference": max((abs(a[i] - b[i]) for i in differing), default=0),
        }
    return report


def run_binary(spec, launcher, run_directory, baseline_files):
    """Run one executable (or interpret one IR file) in the staged directory and return its output and created files."""
    remove_extra_files(run_directory, baseline_files)
    completed = invoke(launcher, spec.arguments, run_directory, spec.stdin_file)
    return completed, read_new_files(run_directory, baseline_files)


def lower_at_o2(spec, source, work):
    """Lower a bitcode or IR file at -O2 with the same backend and link step as the sweeps, and return the executable."""
    work.mkdir(parents=True, exist_ok=True)
    object_file = work / "module.o"
    executable = work / spec.program_name
    run_tool("llc", [*LOWERING_FLAGS, str(source), "-o", str(object_file)])
    run_tool("clang", [str(object_file), "-o", str(executable), *spec.link_libraries])
    return executable


def stage_checks(spec, row, canonical_files, run_directory, baseline_files, work):
    """Compare each stage of the pipeline run alone with the canonical output."""
    results = {}
    stages = row["pass_sequence_str"].split(PIPELINE_SEPARATOR)
    for index, stage in enumerate(stages):
        plan = SweepPlan(row["regime_id"], f"{row['sweep_id']}-stage{index}", stage, stage)
        stage_work = work / f"stage{index}"
        stage_work.mkdir(parents=True, exist_ok=True)
        compiled = compile_phase(spec, plan, stage_work)
        completed, files = run_binary(spec, native_launcher(compiled["executable"]), run_directory, baseline_files)
        results[stage] = all(entry["identical"] for entry in compare_outputs(canonical_files, files).values())
    return results


def investigate(row, specs):
    spec = specs[row["kernel_id"]]
    work = WORK_ROOT / row["sweep_id"]
    work.mkdir(parents=True, exist_ok=True)
    plan = SweepPlan(row["regime_id"], row["sweep_id"], row["pass_sequence_str"], row["pass_sequence_str"])
    compiled = compile_phase(spec, plan, work)
    run_directory, baseline_files = prepared_run_directory(spec)
    canonical_completed, canonical_files = run_binary(
        spec, native_launcher(canonical_lowered_executable(spec)), run_directory, baseline_files)
    sweep_completed, sweep_files = run_binary(spec, native_launcher(compiled["executable"]), run_directory, baseline_files)
    canonical_bitcode = kernel_build_directory(spec) / CANONICAL_NAME
    optimized_ir = work / OPTIMIZED_LISTING
    _, lli_canonical_files = run_binary(spec, lli_launcher(canonical_bitcode), run_directory, baseline_files)
    _, lli_optimized_files = run_binary(spec, lli_launcher(optimized_ir), run_directory, baseline_files)
    o2_canonical = lower_at_o2(spec, canonical_bitcode, work / "canonical-O2")
    o2_optimized = lower_at_o2(spec, optimized_ir, work / "optimized-O2")
    _, o2_canonical_files = run_binary(spec, native_launcher(o2_canonical), run_directory, baseline_files)
    _, o2_optimized_files = run_binary(spec, native_launcher(o2_optimized), run_directory, baseline_files)
    return {
        "sweep_id": row["sweep_id"],
        "kernel_id": row["kernel_id"],
        "pipeline": row["pass_sequence_str"],
        "digest_equal_to_canonical": digest_run(spec, sweep_completed, sweep_files) == digest_run(
            spec, canonical_completed, canonical_files),
        "sweep_vs_canonical": compare_outputs(canonical_files, sweep_files),
        "lli_canonical_vs_native": compare_outputs(canonical_files, lli_canonical_files),
        "lli_optimized_vs_native": compare_outputs(canonical_files, lli_optimized_files),
        "llc_O2_canonical_vs_native": compare_outputs(canonical_files, o2_canonical_files),
        "llc_O2_optimized_vs_native": compare_outputs(canonical_files, o2_optimized_files),
        "single_stage_identical": stage_checks(spec, row, canonical_files, run_directory, baseline_files, work),
    }


def main():
    specs = {spec.kernel_id: spec for spec in all_kernels()}
    results = [investigate(row, specs) for row in exception_rows()]
    OUTPUT_PATH.write_text(json.dumps({"exceptions": results}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"exceptions": len(results), "output": str(OUTPUT_PATH)}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
