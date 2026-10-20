"""Task 5: Z3 block validation for every sweep, Pareto fronts with exact hypervolume, and pass algebra summaries.

Reads the master sweep table, recomputes each sweep's optimized IR with the sweep's own pipeline and
arguments, validates it block by block against the canonical IR, and writes:
  data/telemetry/z3_verification_proofs.csv    per-sweep Z3 outcome and timing
  data/telemetry/pareto_3d_frontiers.csv       non-dominated sweeps per kernel with exact hypervolume
  data/telemetry/rpb_summary.json             redundant-pass-bloat and compile-waste summaries
  data/telemetry/lie_bracket_mean.csv          mean commutator matrix over kernels
The master table's z3_refinement_status column is updated in place (atomic replace).
"""

import csv
import json
import os
import shutil
import sys
import tempfile
import time
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path

from lib.build_layout import BUILD_ROOT, CANONICAL_LISTING_NAME, CANONICAL_NAME, kernel_directory_name
from lib.fixpoint_retry import canonical_spelling
from lib.kernel_catalog import all_kernels
from lib.kernel_registry import REPO_ROOT
from lib.llvm_tools import run_tool
from lib.objectives import REFERENCE_POINT, objective_vector
from lib.pass_algebra import hypervolume_3d, lie_bracket, pareto_front, rpb_ratio, waste_cycle
from lib.pass_catalog import stage_by_name
from lib.pipeline_plans import R3_PASSES
from lib.telemetry_metrics import defined_functions, instruction_count
from lib.z3_block_check import empty_summary, sweep_status, validate_listings

WORKER_COUNT = 8
Z3_TIMEOUT_MS = 5000
DEFAULT_TELEMETRY_DIR = REPO_ROOT / "data" / "telemetry"
MASTER_CSV_NAME = "master_sweeps_28800.csv"
PROOFS_NAME = "z3_verification_proofs.csv"
PARETO_NAME = "pareto_3d_frontiers.csv"
RPB_NAME = "rpb_summary.json"
LIE_NAME = "lie_bracket_mean.csv"
FORCE_PREFIX = "force-attribute="
BRACKET_PATTERN_START = "["
STATUS_IR_NOT_REPRODUCED = "IR_NOT_REPRODUCED"
PROOF_COLUMNS = (
    "sweep_id", "kernel_id", "regime_id", "z3_refinement_status", "ir_reproduced", "ir_identical_to_canonical",
    "blocks_matched", "blocks_compared", "blocks_not_encodable", "names_refines", "names_violated", "names_unknown",
    "check_seconds",
)
COMMENT_PREFIX = ";"


def log(message):
    timestamp = datetime.now(UTC).strftime("%H:%M:%S")
    print(f"[{timestamp}] {message}", file=sys.stderr, flush=True)


def split_pass_sequence(pass_sequence):
    """Return (opt pipeline, extra opt arguments, forced attribute or '') for a telemetry pass string."""
    if BRACKET_PATTERN_START not in pass_sequence:
        return pass_sequence, (), ""
    pipeline, bracket = pass_sequence.split(BRACKET_PATTERN_START, 1)
    bracket = bracket.rstrip("]")
    if bracket.startswith(FORCE_PREFIX):
        return pipeline, (), bracket[len(FORCE_PREFIX):]
    return pipeline, tuple(bracket.split()), ""


def optimized_listing(kernel_directory, pass_sequence, scratch):
    """Re-run the sweep's opt command (no traces) and return the optimized listing text."""
    pipeline, arguments, attribute = split_pass_sequence(pass_sequence)
    canonical = BUILD_ROOT / kernel_directory / CANONICAL_NAME
    extra = list(arguments)
    if attribute:
        names = defined_functions((BUILD_ROOT / kernel_directory / CANONICAL_LISTING_NAME).read_text(encoding="utf-8"))
        extra = [f"-force-attribute={name}:{attribute}" for name in names]
    output = scratch / "optimized.ll"
    run_tool("opt", [f"-passes={pipeline}", *extra, str(canonical), "-S", "-o", str(output)])
    return output.read_text(encoding="utf-8")


def body_lines(listing):
    """The listing without comments, headers, and blank lines, so that two prints of one module compare equal."""
    return [line for line in listing.splitlines() if line.strip() and not line.startswith(COMMENT_PREFIX)]


def verify_row(job):
    """Validate one sweep. Returns a proof record; errors are recorded, never raised."""
    scratch = Path(tempfile.mkdtemp(prefix="z3-", dir=BUILD_ROOT))
    started = time.perf_counter()
    reproduced = False
    identical = False
    try:
        canonical_text = (BUILD_ROOT / job["kernel_directory"] / CANONICAL_LISTING_NAME).read_text(encoding="utf-8")
        optimized_text = optimized_listing(job["kernel_directory"], job["pass_sequence"], scratch)
        reproduced = instruction_count(optimized_text) == int(job["ir_inst_after"])
        identical = body_lines(optimized_text) == body_lines(canonical_text)
        summary = validate_listings(canonical_text, optimized_text, Z3_TIMEOUT_MS) if reproduced else empty_summary()
        status = sweep_status(summary) if reproduced else STATUS_IR_NOT_REPRODUCED
        error = ""
    except Exception as failure:  # noqa: BLE001 - recorded per sweep so that the table stays complete
        summary = empty_summary()
        status = "ERROR"
        error = str(failure)[:300]
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
    return {
        "sweep_id": job["sweep_id"],
        "kernel_id": job["kernel_id"],
        "regime_id": job["regime_id"],
        "z3_refinement_status": status,
        "ir_reproduced": reproduced,
        "ir_identical_to_canonical": identical,
        **summary,
        "check_seconds": round(time.perf_counter() - started, 6),
        "error": error,
    }


def load_rows(path):
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def write_rows(path, fieldnames, rows):
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n", extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    os.replace(temporary, path)


def validate_all(rows):
    directories = {kernel.kernel_id: kernel_directory_name(kernel) for kernel in all_kernels()}
    jobs = [
        {
            "sweep_id": row["sweep_id"],
            "kernel_id": row["kernel_id"],
            "regime_id": row["regime_id"],
            "pass_sequence": row["pass_sequence_str"],
            "ir_inst_after": row["ir_inst_after"],
            "kernel_directory": directories[row["kernel_id"]],
        }
        for row in rows
    ]
    proofs = []
    with ProcessPoolExecutor(max_workers=WORKER_COUNT) as pool:
        futures = [pool.submit(verify_row, job) for job in jobs]
        for index, future in enumerate(as_completed(futures), start=1):
            proofs.append(future.result())
            if index % 500 == 0:
                log(f"validated {index}/{len(jobs)} sweeps")
    return {proof["sweep_id"]: proof for proof in proofs}


def pareto_and_hypervolume(rows, baselines):
    """Per kernel: non-dominated normalised objective vectors and their exact hypervolume."""
    by_kernel = defaultdict(list)
    for row in rows:
        by_kernel[row["kernel_id"]].append(row)
    reference_compile = {}
    for kernel_id, kernel_rows in by_kernel.items():
        o0 = next((r for r in kernel_rows if r["sweep_id"].endswith("-R1-000")), None)
        reference_compile[kernel_id] = float(o0["compile_wall_ms"]) if o0 else None
    frontier_rows, summary = [], {}
    for kernel_id, kernel_rows in by_kernel.items():
        if reference_compile[kernel_id] is None:
            continue
        text_reference = baselines[kernel_id]["text_bytes"]
        vectors = {}
        for row in kernel_rows:
            vector = objective_vector(
                float(row["cost_J_before"]), float(row["cost_J_after"]),
                text_reference, float(row["binary_text_bytes"]),
                reference_compile[kernel_id], float(row["compile_wall_ms"]),
            )
            vectors.setdefault(vector, row)
        front = pareto_front(list(vectors))
        volume = hypervolume_3d(front, REFERENCE_POINT)
        summary[kernel_id] = {"front_size": len(front), "hypervolume": float(volume)}
        for vector in front:
            frontier_rows.append({
                "kernel_id": kernel_id,
                "sweep_id": vectors[vector]["sweep_id"],
                "regime_id": vectors[vector]["regime_id"],
                "pass_sequence_str": vectors[vector]["pass_sequence_str"],
                "speedup_objective": vector[0],
                "size_objective": vector[1],
                "compile_objective": vector[2],
                "hypervolume_kernel": float(volume),
            })
    return frontier_rows, summary


def rpb_and_waste(rows):
    by_regime = defaultdict(lambda: {"sweeps": 0, "rpb_sum": 0.0, "waste_ms": 0.0})
    for row in rows:
        bucket = by_regime[row["regime_id"]]
        ratio = rpb_ratio(float(row["pass_count_noop_rpb"]), float(row["pass_count_total"]))
        bucket["sweeps"] += 1
        bucket["rpb_sum"] += ratio
        bucket["waste_ms"] += waste_cycle(float(row["compile_wall_ms"]), ratio)
    return {
        regime: {
            "sweeps": values["sweeps"],
            "mean_rpb_ratio": values["rpb_sum"] / values["sweeps"],
            "total_waste_cycle_ms": values["waste_ms"],
        }
        for regime, values in sorted(by_regime.items())
    }


def lie_bracket_mean(rows, baselines):
    """Mean commutator over kernels for every ordered pair of the R3 passes, from paired R3 deltas."""
    pass_of_stage = {stage: name for name, stage in stage_by_name().items()}
    pair_deltas = {}
    for row in rows:
        if row["regime_id"] != "R3":
            continue
        first_stage, second_stage = canonical_spelling(row["pass_sequence_str"]).split(",")
        pair_deltas[(row["kernel_id"], pass_of_stage[first_stage], pass_of_stage[second_stage])] = float(row["delta_cost_J"])
    kernels = sorted({kernel_id for kernel_id, _, _ in pair_deltas})
    totals = {(first, second): [] for first in R3_PASSES for second in R3_PASSES}
    for kernel_id in kernels:
        j0 = baselines[kernel_id]["median_ns"]
        for first in R3_PASSES:
            for second in R3_PASSES:
                forward = pair_deltas.get((kernel_id, first, second))
                backward = pair_deltas.get((kernel_id, second, first))
                if forward is not None and backward is not None:
                    totals[(first, second)].append(lie_bracket(forward, backward, j0))
    return {key: (sum(values) / len(values) if values else 0.0) for key, values in totals.items()}


def main():
    telemetry = DEFAULT_TELEMETRY_DIR
    master_path = telemetry / MASTER_CSV_NAME
    rows = load_rows(master_path)
    baselines = json.loads((telemetry / "canonical_baselines.json").read_text(encoding="utf-8"))
    log(f"sweeps in master table: {len(rows)}")
    proofs = validate_all(rows)
    proof_fields = PROOF_COLUMNS + ("error",)
    write_rows(telemetry / PROOFS_NAME, proof_fields, [proofs[row["sweep_id"]] for row in rows if row["sweep_id"] in proofs])
    for row in rows:
        row["z3_refinement_status"] = proofs[row["sweep_id"]]["z3_refinement_status"] if row["sweep_id"] in proofs else row["z3_refinement_status"]
    write_rows(master_path, list(rows[0].keys()), rows)
    frontier_rows, frontier_summary = pareto_and_hypervolume(rows, baselines)
    write_rows(telemetry / PARETO_NAME, list(frontier_rows[0].keys()) if frontier_rows else ["kernel_id"], frontier_rows)
    (telemetry / RPB_NAME).write_text(json.dumps({"by_regime": rpb_and_waste(rows), "pareto_per_kernel": frontier_summary}, indent=2) + "\n", encoding="utf-8")
    lie = lie_bracket_mean(rows, baselines)
    with (telemetry / LIE_NAME).open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(["first_pass", *R3_PASSES])
        for first in R3_PASSES:
            writer.writerow([first, *(f"{lie[(first, second)]:.12g}" for second in R3_PASSES)])
    statuses = defaultdict(int)
    for proof in proofs.values():
        statuses[proof["z3_refinement_status"]] += 1
    log(f"z3 statuses: {dict(statuses)}; pareto points: {len(frontier_rows)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
