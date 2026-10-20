"""Compile side of one sweep: optimize with opt, lower with llc, link, and size the executable.

Compile time is telemetry only. The paired timing of the executables is done in sweep_executor under the exclusive
side of the gate, and nothing in this module is timed for that purpose.

Each variant is optimized twice. The traced run supplies the redundancy counts and the instruction count. The clean run
carries only -time-passes, so its compile time and pass time exclude the serialization that -print-changed performs. The
two runs must produce identical IR, and a mismatch fails the sweep.
"""

import re
import time

from lib.build_layout import CANONICAL_LISTING_NAME, CANONICAL_NAME, kernel_build_directory
from lib.llvm_tools import run_tool
from lib.telemetry_metrics import defined_functions, parse_trace

LLC_ARGUMENTS = ("-O0", "-filetype=obj")
OPT_TRACE_ARGUMENTS = ("-print-changed", "-debug-pass-manager", "-time-passes")
CLEAN_OPT_ARGUMENTS = ("-time-passes",)
TEXT_SECTION_PATTERN = re.compile(r"Section __text: (\d+)")
NANOSECONDS_PER_MILLISECOND = 1_000_000.0
MILLISECONDS_PER_SECOND = 1_000.0
TRACED_LISTING_NAME = "opt.ll"
CLEAN_LISTING_NAME = "opt_clean.ll"


def canonical_bitcode(spec):
    return kernel_build_directory(spec) / CANONICAL_NAME


def canonical_listing(spec):
    return kernel_build_directory(spec) / CANONICAL_LISTING_NAME


def lower(listing, executable, spec):
    """Lower optimized IR with the fixed backend (llc -O0) and link; return (path, milliseconds)."""
    started = time.perf_counter_ns()
    object_file = executable.with_suffix(".o")
    run_tool("llc", [*LLC_ARGUMENTS, str(listing), "-o", str(object_file)])
    run_tool("clang", [str(object_file), "-o", str(executable), *spec.link_libraries])
    elapsed_ms = (time.perf_counter_ns() - started) / NANOSECONDS_PER_MILLISECOND
    return executable, elapsed_ms


def text_section_bytes(executable):
    output = run_tool("llvm_size", ["-m", str(executable)]).stdout
    match = TEXT_SECTION_PATTERN.search(output)
    if match is None:
        raise ValueError(f"no __text section reported for {executable}")
    return int(match.group(1))


def force_arguments(spec, plan):
    """Forced function attributes for the Os and Oz baselines, applied to every defined function."""
    if not plan.force_attribute:
        return []
    names = defined_functions(canonical_listing(spec).read_text(encoding="utf-8"))
    return [f"-force-attribute={name}:{plan.force_attribute}" for name in names]


def opt_command(spec, plan, output, traces):
    """The opt invocation of one variant. The traced and the clean runs share it and differ only in the trace flags."""
    return [
        f"-passes={plan.opt_pipeline}",
        *plan.opt_arguments,
        *force_arguments(spec, plan),
        *traces,
        str(canonical_bitcode(spec)),
        "-S",
        "-o",
        str(output),
    ]


def optimize(spec, plan, work_dir):
    """Run opt with the traces needed for telemetry; return its trace text."""
    completed = run_tool("opt", opt_command(spec, plan, work_dir / TRACED_LISTING_NAME, OPT_TRACE_ARGUMENTS))
    return completed.stderr


def optimize_clean(spec, plan, work_dir):
    """Run opt again with only -time-passes; return (its report text, wall milliseconds of the process)."""
    started = time.perf_counter_ns()
    completed = run_tool("opt", opt_command(spec, plan, work_dir / CLEAN_LISTING_NAME, CLEAN_OPT_ARGUMENTS))
    return completed.stderr, (time.perf_counter_ns() - started) / NANOSECONDS_PER_MILLISECOND


def compile_phase(spec, plan, work_dir):
    """Optimize twice, lower, and size one variant. Runs under the shared gate; holds no timing."""
    trace_text = optimize(spec, plan, work_dir)
    clean_text, compile_ms = optimize_clean(spec, plan, work_dir)
    listing_path = work_dir / TRACED_LISTING_NAME
    if listing_path.read_bytes() != (work_dir / CLEAN_LISTING_NAME).read_bytes():
        raise RuntimeError(f"traced and clean optimizer runs disagree for {plan.label}")
    executable, backend_ms = lower(listing_path, work_dir / spec.program_name, spec)
    return {
        "trace": parse_trace(trace_text),
        "compile_ms": compile_ms,
        "pass_ms": parse_trace(clean_text)["pass_time_seconds"] * MILLISECONDS_PER_SECOND,
        "backend_ms": backend_ms,
        "text_bytes": text_section_bytes(executable),
        "listing": listing_path.read_text(encoding="utf-8"),
        "executable": executable,
    }
