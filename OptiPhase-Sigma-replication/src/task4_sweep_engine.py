"""Task 4: the sweep campaign. Phase r1-r5 plans regimes R1-R5; phase r6 plans M_pass-guided sequences.

Both phases run on a pool of WORKER_COUNT processes and checkpoint every row to the master CSV, so an
interrupted run resumes without repeating completed sweeps.
"""

import argparse
import csv
import json
import multiprocessing
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path

from lib.crash_replacements import replacement_items, skipped_sweep_ids
from lib.instcount_matrix import instcount_matrix
from lib.kernel_catalog import all_kernels
from lib.kernel_registry import REPO_ROOT
from lib.llvm_tools import ToolError, run_tool
from lib.machine_gate import MachineGate
from lib.pass_catalog import VALIDITY_PATH, canonical_passes, stage_by_name, stage_text
from lib.pipeline_plans import R3_PASSES, REFERENCE_BITCODE, SweepPlan, static_plans
from lib.regime6_planner import plan_regime6
from lib.sweep_executor import canonical_baseline, install_gate, run_sweep

WORKER_COUNT = 8
PROGRESS_INTERVAL = 200
DEFAULT_TELEMETRY_DIR = REPO_ROOT / "data" / "telemetry"
CSV_COLUMNS = (
    "sweep_id", "kernel_id", "suite_name", "regime_id", "pipeline_hash", "pass_sequence_str",
    "pass_count_total", "pass_count_noop_rpb", "rpb_ratio", "compile_wall_ms", "opt_pass_ms",
    "backend_codegen_ms", "ir_inst_before", "ir_inst_after", "ir_delta_inst", "cost_J_before",
    "cost_J_after", "delta_cost_J", "shannon_H_before", "shannon_H_after", "kl_div_from_canon",
    "scev_invalidation_count", "loops_vectorized_count", "binary_text_bytes", "exec_cycles_median",
    "z3_refinement_status",
)
SUBSTITUTES_PATH = REPO_ROOT / "config" / "llvm_newpm_substitutes.json"
SUBSTITUTE_FIRST_INDEX = 82
MASTER_CSV_NAME = "master_sweeps_28800.csv"
BASELINES_NAME = "canonical_baselines.json"
MATRIX_NAME = "m_pass_transition_matrix.csv"


def log(message):
    timestamp = datetime.now(UTC).strftime("%H:%M:%S")
    print(f"[{timestamp}] {message}", file=sys.stderr, flush=True)


def probe_pass(entry):
    stage = stage_text(entry)
    try:
        run_tool("opt", [f"-passes={stage}", str(REFERENCE_BITCODE), "-o", "/dev/null"])
        return {"name": entry["name"], "level": entry["level"], "stage": stage, "valid": True, "error": None}
    except ToolError as error:
        return {"name": entry["name"], "level": entry["level"], "stage": stage, "valid": False, "error": str(error)[:300]}


def refresh_pass_validity():
    """Record which canonical passes LLVM 23 accepts at their nesting level; the sweeps use the valid ones."""
    rows = [probe_pass(entry) for entry in canonical_passes()]
    VALIDITY_PATH.write_text(json.dumps({"passes": rows}, indent=2) + "\n", encoding="utf-8")
    return rows


def plan_sweeps(kernels, plans, first_index=0):
    """Yield (sweep_id, kernel, plan) in a fixed order so that re-runs produce the same IDs.

    first_index keeps the substitute passes' IDs after the canonical R2 IDs (6-81) and before R3 (82+).
    """
    for kernel_index, kernel in enumerate(kernels):
        for offset, plan in enumerate(plans):
            plan_index = first_index + offset
            yield f"K{kernel_index:02d}-{plan.regime_id}-{plan_index:03d}", kernel, plan


def substitute_plans():
    """The eight R2 substitutes named in config/llvm_newpm_substitutes.json, one sweep plan each."""
    config = json.loads(SUBSTITUTES_PATH.read_text(encoding="utf-8"))
    return [SweepPlan("R2", row["name"], row["stage"], row["stage"]) for row in config["passes"]]


def load_rows(csv_path):
    if not csv_path.exists():
        return []
    with csv_path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def load_completed_ids(csv_path):
    return {row["sweep_id"] for row in load_rows(csv_path)}


def open_csv(csv_path):
    is_new = not csv_path.exists()
    handle = csv_path.open("a", encoding="utf-8", newline="")
    writer = csv.DictWriter(handle, fieldnames=CSV_COLUMNS, lineterminator="\n")
    if is_new:
        writer.writeheader()
    return handle, writer


def run_baselines(kernels, pool, audit_handle):
    """Measure every kernel's canonical baseline; a kernel that fails is logged and its sweeps skipped."""
    futures = {pool.submit(canonical_baseline, kernel): kernel for kernel in kernels}
    baselines = {}
    for future in as_completed(futures):
        kernel = futures[future]
        try:
            result = future.result()
        except Exception as error:  # noqa: BLE001 - recorded in the audit file, sweeps for this kernel are skipped
            message = str(error)[:1000]
            audit_handle.write(json.dumps({"kernel_id": kernel.kernel_id, "status": "baseline_failed", "error": message}) + "\n")
            log(f"baseline failed for {kernel.kernel_id}: {message[:200]}")
            continue
        baselines[result["kernel_id"]] = result
    return baselines


def load_or_measure_baselines(kernels, pool, audit_handle, telemetry):
    """Reuse the stored baselines when they cover every kernel, so that rows already written keep their reference."""
    path = telemetry / BASELINES_NAME
    if path.exists():
        baselines = json.loads(path.read_text(encoding="utf-8"))
        if all(kernel.kernel_id in baselines for kernel in kernels):
            return baselines
    baselines = run_baselines(kernels, pool, audit_handle)
    path.write_text(json.dumps(baselines, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return baselines


def run_pending_sweeps(pending, baselines, pool, writer, audit_handle):
    futures = {
        pool.submit(run_sweep, kernel, plan, sweep_id, baselines[kernel.kernel_id]): sweep_id
        for sweep_id, kernel, plan in pending
    }
    done = failed = 0
    for future in as_completed(futures):
        row, audit = future.result()
        audit_handle.write(json.dumps(audit, ensure_ascii=False) + "\n")
        audit_handle.flush()
        if row is None:
            failed += 1
        else:
            writer.writerow(row)
        done += 1
        if done % PROGRESS_INTERVAL == 0:
            log(f"sweeps finished {done}/{len(futures)} (failed {failed})")
    return done, failed


def r6_plans_from_matrix(matrix):
    """Turn the 60 highest-scoring M_pass chains into sweep plans, shared by every kernel."""
    stages = stage_by_name()
    plans = []
    for sequence in plan_regime6(matrix, R3_PASSES):
        pipeline = ",".join(stages[name] for name in sequence)
        plans.append(SweepPlan("R6", ">".join(sequence), pipeline, pipeline))
    return plans


def write_matrix(matrix, path):
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(["first_pass", *R3_PASSES])
        for first in R3_PASSES:
            writer.writerow([first, *(f"{matrix[(first, second)]:.12g}" for second in R3_PASSES)])


def plan_r6_phase(kernels, baselines, telemetry):
    """Choose the R6 chains from the instruction-count transition matrix, which carries no timing noise."""
    rows = load_rows(telemetry / MASTER_CSV_NAME)
    matrix = instcount_matrix(rows, R3_PASSES)
    write_matrix(matrix, telemetry / MATRIX_NAME)
    log(f"instruction-count M_pass from {len(kernels)} kernels")
    return r6_plans_from_matrix(matrix), []


def parse_arguments():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", choices=("r1-r5", "r2x", "r6"), default="r1-r5")
    parser.add_argument("--telemetry-dir", type=Path, default=DEFAULT_TELEMETRY_DIR)
    parser.add_argument("--kernel", default=None, help="limit to one kernel_id (smoke tests)")
    parser.add_argument("--limit", type=int, default=None, help="limit pending sweeps (smoke tests)")
    return parser.parse_args()


def main():
    arguments = parse_arguments()
    telemetry = arguments.telemetry_dir
    telemetry.mkdir(parents=True, exist_ok=True)
    if not VALIDITY_PATH.exists():
        rows = refresh_pass_validity()
        log(f"pass validity: {sum(r['valid'] for r in rows)}/{len(rows)} canonical passes accepted")
    kernels = [kernel for kernel in all_kernels() if arguments.kernel in (None, kernel.kernel_id)]
    csv_path = telemetry / MASTER_CSV_NAME
    completed = load_completed_ids(csv_path)
    context = multiprocessing.get_context("spawn")
    gate = MachineGate(context)
    audit_handle = (telemetry / "sweep_audit.jsonl").open("a", encoding="utf-8")
    with ProcessPoolExecutor(
        max_workers=WORKER_COUNT, mp_context=context, initializer=install_gate, initargs=(gate,)
    ) as pool, audit_handle:
        first_index = 0
        if arguments.phase == "r1-r5":
            plans = static_plans()
            (telemetry / "sweep_plan.json").write_text(
                json.dumps([{"regime_id": p.regime_id, "label": p.label, "pass_sequence": p.pass_sequence} for p in plans], indent=2)
                + "\n",
                encoding="utf-8",
            )
            baselines = load_or_measure_baselines(kernels, pool, audit_handle, telemetry)
        elif arguments.phase == "r2x":
            baselines = json.loads((telemetry / BASELINES_NAME).read_text(encoding="utf-8"))
            plans = substitute_plans()
            first_index = SUBSTITUTE_FIRST_INDEX
        else:
            baselines = json.loads((telemetry / BASELINES_NAME).read_text(encoding="utf-8"))
            plans, excluded = plan_r6_phase(kernels, baselines, telemetry)
            (telemetry / "sweep_plan_r6.json").write_text(
                json.dumps([{"regime_id": p.regime_id, "label": p.label, "pass_sequence": p.pass_sequence} for p in plans], indent=2)
                + "\n",
                encoding="utf-8",
            )
        items = list(plan_sweeps(kernels, plans, first_index))
        if arguments.phase == "r2x":
            items += list(replacement_items(kernels))
        skipped = skipped_sweep_ids()
        pending = [
            item for item in items
            if item[0] not in completed and item[0] not in skipped and item[1].kernel_id in baselines
        ]
        if arguments.limit is not None:
            pending = pending[: arguments.limit]
        log(f"phase={arguments.phase} kernels={len(kernels)} baselines={len(baselines)} plans_per_kernel={len(plans)} pending_sweeps={len(pending)}")
        csv_handle, writer = open_csv(csv_path)
        with csv_handle:
            done, failed = run_pending_sweeps(pending, baselines, pool, writer, audit_handle)
    log(f"finished: {done} sweeps, {failed} failed; rows in {csv_path}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
