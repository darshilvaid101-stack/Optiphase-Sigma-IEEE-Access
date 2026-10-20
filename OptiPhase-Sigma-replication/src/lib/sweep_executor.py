"""One sweep: optimize a canonical kernel with a pipeline, lower it, time it, and record telemetry.

Timing is paired: each sweep times the canonical lowering and its own lowering back to back inside
one exclusive window, and cost_J_before is the paired canonical median. A baseline measured at a
different moment (for example, at the start of the pool) carries a systematic offset of its own.
"""

import hashlib
import os
import shutil
import statistics
import time

from lib.build_layout import BUILD_ROOT, NATIVE_DIRECTORY_NAME, kernel_build_directory, kernel_directory_name
from lib.fixpoint_retry import compile_with_fixpoint_retry
from lib.kernel_execution import digest_run, invoke, list_files, native_launcher, read_new_files, stage_run_directory
from lib.machine_gate import NullGate
from lib.sweep_compile import canonical_listing, compile_phase, lower, text_section_bytes
from lib.telemetry_metrics import (
    instruction_count,
    kl_divergence_bits,
    opcode_histogram,
    scev_invalidations,
    shannon_entropy_bits,
    vectorized_loop_count,
)

SWEEP_ROOT = BUILD_ROOT / "sweeps"
RUN_ROOT = BUILD_ROOT / "sweep-runs"
CANONICAL_LOWERED_DIRECTORY_NAME = "llc-canonical"
WARMUP_RUNS = 3
TIMING_REPETITIONS = 15
PENDING_Z3_STATUS = "PENDING"
FAILURE_HEAD_CHARACTERS = 300
FAILURE_TAIL_CHARACTERS = 700

# Installed once per worker process. Compilation runs under the shared side of the gate and
# timed executions under the exclusive side, so that no compile overlaps a measurement.
GATE = NullGate()
PREPARED_RUN_DIRECTORIES = {}


def install_gate(gate):
    global GATE
    GATE = gate






def canonical_native_executable(spec):
    """The -O0 clang build from Task 3; used only to produce the reference digest of the kernel."""
    return kernel_build_directory(spec) / NATIVE_DIRECTORY_NAME / spec.program_name


def canonical_lowered_executable(spec):
    """The canonical IR lowered through the same llc -O0 backend as every sweep."""
    return kernel_build_directory(spec) / CANONICAL_LOWERED_DIRECTORY_NAME / spec.program_name


def prepared_run_directory(spec):
    """Stage the kernel's inputs once per worker process and record the post-setup file set."""
    cached = PREPARED_RUN_DIRECTORIES.get(spec.kernel_id)
    if cached is not None:
        return cached
    scratch = RUN_ROOT / str(os.getpid()) / kernel_directory_name(spec)
    shutil.rmtree(scratch, ignore_errors=True)
    run_directory = stage_run_directory(spec, scratch)
    for setup in spec.setup_arguments:
        invoke(native_launcher(canonical_native_executable(spec)), setup, run_directory, "")
    PREPARED_RUN_DIRECTORIES[spec.kernel_id] = (run_directory, list_files(run_directory))
    return PREPARED_RUN_DIRECTORIES[spec.kernel_id]


def remove_extra_files(run_directory, baseline_files):
    for relative in list_files(run_directory) - baseline_files:
        (run_directory / relative).unlink()


def summarize(durations, digest):
    return {
        "median_ns": statistics.median(durations),
        "min_ns": min(durations),
        "max_ns": max(durations),
        "digest": digest,
    }


def timed_run(spec, executable, run_directory, baseline_files):
    """Run once after removing files left by earlier runs; return (elapsed ns, digest of this run)."""
    remove_extra_files(run_directory, baseline_files)
    started = time.perf_counter_ns()
    completed = invoke(native_launcher(executable), spec.arguments, run_directory, spec.stdin_file)
    elapsed = time.perf_counter_ns() - started
    return elapsed, digest_run(spec, completed, read_new_files(run_directory, baseline_files))


def time_executable(spec, executable, run_directory, baseline_files):
    """Time one executable after warm-up runs. Callers must hold the exclusive gate."""
    durations, digest = [], None
    for run_index in range(WARMUP_RUNS + TIMING_REPETITIONS):
        elapsed, run_digest = timed_run(spec, executable, run_directory, baseline_files)
        if run_index == 0:
            digest = run_digest
        if run_index >= WARMUP_RUNS:
            durations.append(elapsed)
    return summarize(durations, digest)


def time_interleaved(spec, first, second, run_directory, baseline_files):
    """Time two executables in alternating order within one window, so drift and order bias cancel.

    Returns (summary for first, summary for second). Callers must hold the exclusive gate.
    """
    durations = {"first": [], "second": []}
    digests = {}
    for run_index in range(WARMUP_RUNS + TIMING_REPETITIONS):
        order = (("first", first), ("second", second))
        if run_index % 2:
            order = (("second", second), ("first", first))
        for label, executable in order:
            elapsed, run_digest = timed_run(spec, executable, run_directory, baseline_files)
            if run_index == 0:
                digests[label] = run_digest
            if run_index >= WARMUP_RUNS:
                durations[label].append(elapsed)
    return summarize(durations["first"], digests["first"]), summarize(durations["second"], digests["second"])






def canonical_baseline(spec):
    """Lower the canonical IR through the sweep backend, keep it for paired timing, and record it."""
    listing = canonical_listing(spec)
    lowered = canonical_lowered_executable(spec)
    lowered.parent.mkdir(parents=True, exist_ok=True)
    with GATE.shared():
        lower(listing, lowered, spec)
        text_bytes = text_section_bytes(lowered)
        run_directory, baseline_files = prepared_run_directory(spec)
    with GATE.exclusive():
        timing = time_executable(spec, lowered, run_directory, baseline_files)
    histogram = opcode_histogram(listing.read_text(encoding="utf-8"))
    return {
        "kernel_id": spec.kernel_id,
        "median_ns": timing["median_ns"],
        "min_ns": timing["min_ns"],
        "max_ns": timing["max_ns"],
        "digest": timing["digest"],
        "histogram": dict(histogram),
        "instruction_count": sum(histogram.values()),
        "entropy_bits": shannon_entropy_bits(histogram),
        "text_bytes": text_bytes,
    }


def pipeline_hash(pass_sequence):
    return hashlib.sha256(pass_sequence.encode("utf-8")).hexdigest()[:16]






def sweep_row(spec, plan, sweep_id, baseline, measured):
    trace = measured["trace"]
    total = trace["pass_events"]
    noop = trace["noop_events"]
    before_ns = measured["paired_canonical_median_ns"]
    after_ns = measured["median_ns"]
    return {
        "sweep_id": sweep_id,
        "kernel_id": spec.kernel_id,
        "suite_name": spec.suite,
        "regime_id": plan.regime_id,
        "pipeline_hash": pipeline_hash(plan.pass_sequence),
        "pass_sequence_str": plan.pass_sequence,
        "pass_count_total": total,
        "pass_count_noop_rpb": noop,
        "rpb_ratio": (noop / total) if total else 0.0,
        "compile_wall_ms": measured["compile_ms"],
        "opt_pass_ms": measured["pass_ms"],
        "backend_codegen_ms": measured["backend_ms"],
        "ir_inst_before": baseline["instruction_count"],
        "ir_inst_after": measured["instruction_count"],
        "ir_delta_inst": measured["instruction_count"] - baseline["instruction_count"],
        "cost_J_before": before_ns,
        "cost_J_after": after_ns,
        "delta_cost_J": after_ns - before_ns,
        "shannon_H_before": baseline["entropy_bits"],
        "shannon_H_after": measured["entropy_bits"],
        "kl_div_from_canon": measured["kl_bits"],
        "scev_invalidation_count": scev_invalidations(trace),
        "loops_vectorized_count": measured["loops_vectorized"],
        "binary_text_bytes": measured["text_bytes"],
        "exec_cycles_median": after_ns,
        "z3_refinement_status": PENDING_Z3_STATUS,
    }




def failure_summary(error):
    """Keep the start of the message (the command) and its end (the diagnostic, which LLVM prints last)."""
    text = str(error)
    if len(text) <= FAILURE_HEAD_CHARACTERS + FAILURE_TAIL_CHARACTERS:
        return text
    return f"{text[:FAILURE_HEAD_CHARACTERS]} ... {text[-FAILURE_TAIL_CHARACTERS:]}"


def run_sweep(spec, plan, sweep_id, baseline):
    """Execute one sweep and return (telemetry row, audit record). Failures are returned, not raised."""
    work_dir = SWEEP_ROOT / kernel_directory_name(spec) / sweep_id
    shutil.rmtree(work_dir, ignore_errors=True)
    work_dir.mkdir(parents=True)
    requested_pass_sequence = plan.pass_sequence
    try:
        with GATE.shared():
            plan, compiled = compile_with_fixpoint_retry(lambda used: compile_phase(spec, used, work_dir), plan)
            run_directory, baseline_files = prepared_run_directory(spec)
        with GATE.exclusive():
            canonical, sweep = time_interleaved(
                spec, canonical_lowered_executable(spec), compiled["executable"], run_directory, baseline_files
            )
        histogram = opcode_histogram(compiled["listing"])
        measured = {
            "trace": compiled["trace"],
            "compile_ms": compiled["compile_ms"],
            "pass_ms": compiled["pass_ms"],
            "loops_vectorized": vectorized_loop_count(compiled["listing"]),
            "backend_ms": compiled["backend_ms"],
            "instruction_count": instruction_count(compiled["listing"]),
            "entropy_bits": shannon_entropy_bits(histogram),
            "kl_bits": kl_divergence_bits(histogram, baseline["histogram"]),
            "text_bytes": compiled["text_bytes"],
            "median_ns": sweep["median_ns"],
            "paired_canonical_median_ns": canonical["median_ns"],
        }
        row = sweep_row(spec, plan, sweep_id, baseline, measured)
        audit = {
            "sweep_id": sweep_id,
            "digest_matches_canonical": sweep["digest"] == baseline["digest"],
            "canonical_paired_digest_matches": canonical["digest"] == baseline["digest"],
            "sweep_timing_min_ns": sweep["min_ns"],
            "sweep_timing_max_ns": sweep["max_ns"],
            "canonical_paired_min_ns": canonical["min_ns"],
            "canonical_paired_max_ns": canonical["max_ns"],
            "pipeline_spelling": "default" if plan.pass_sequence == requested_pass_sequence else "no-verify-fixpoint",
            "status": "ok",
        }
        return row, audit
    except Exception as error:  # noqa: BLE001 - every failure is recorded against its sweep
        audit = {"sweep_id": sweep_id, "status": "failed", "error": failure_summary(error)}
        return None, audit
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)
