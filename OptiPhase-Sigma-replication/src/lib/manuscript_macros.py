"""LaTeX macros for every quantity the manuscript reports, each computed from the stored outputs.

Macro names contain letters only, because LaTeX stops a macro name at the first digit. Each builder returns
\\newcommand lines; the caller decides where they are written.
"""

import math
import re
from collections import Counter

from lib.constants import CROSSREF_TITLE_MIN_SIMILARITY, TITLE_DEDUPE_MIN_SIMILARITY
from lib.fixpoint_retry import VARIANT_SPELLING
from lib.objectives import REFERENCE_POINT
from lib.pass_algebra import M_PASS_EPSILON
from lib.pipeline_plans import R3_PASSES, R4_PREFIX_STAGES, R5_AFTER, R5_BEFORE
from lib.regime6_planner import R6_SEQUENCE_LENGTH, R6_SEQUENCES_PER_KERNEL
from lib.sweep_executor import TIMING_REPETITIONS, WARMUP_RUNS

PERCENT_PLACES = 1
REGIME_WORDS = {"R1": "One", "R2": "Two", "R3": "Three", "R4": "Four", "R5": "Five", "R6": "Six"}
STATUS_WORDS = (
    ("UNSAT", "Unsat"),
    ("SAT", "Sat"),
    ("UNKNOWN", "Unknown"),
    ("NOT_COMPARABLE", "NotComparable"),
    ("ERROR", "Error"),
    ("IR_NOT_REPRODUCED", "IrNotReproduced"),
)


def macro(name, value):
    if not name.isalpha():
        raise ValueError(f"macro name must be letters only: {name}")
    return f"\\newcommand{{\\{name}}}{{{value}}}"


def integer(value):
    return f"{int(value):,}"


def decimal(value, places=2):
    return f"{float(value):.{places}f}"


def percent(numerator, denominator):
    if denominator == 0:
        return "0"
    return f"{100.0 * numerator / denominator:.{PERCENT_PLACES}f}"


def constant_macros():
    return [
        macro("CrossrefTitleMin", decimal(CROSSREF_TITLE_MIN_SIMILARITY, 2)),
        macro("DedupeTitleMin", decimal(TITLE_DEDUPE_MIN_SIMILARITY, 2)),
        macro("ConfidenceLevelPct", 95),
    ]


def llvm_version(toolchain_text):
    match = re.search(r"(\d+\.\d+\.\d+)", toolchain_text)
    if not match:
        raise ValueError(f"no LLVM version in {toolchain_text!r}")
    return match.group(1)


def benchmark_macros(kernels, manifest):
    suites = Counter(kernel["suite"] for kernel in kernels)
    return [
        macro("NumKernels", len(kernels)),
        macro("NumPolyBenchKernels", suites["polybench"]),
        macro("NumMiBenchKernels", suites["mibench"]),
        macro("NumTSVCCoreMarkKernels", suites["tsvc_coremark"]),
        macro("NumVerifiedKernels", manifest["gate3"]["verifiedKernels"]),
        macro("LLVMVersion", llvm_version(manifest["toolchain"]["opt"])),
    ]


def protocol_macros(z3_timeout_ms, passes, substitutes):
    return [
        macro("WarmupRuns", WARMUP_RUNS),
        macro("TimedRuns", TIMING_REPETITIONS),
        macro("ZThreeTimeoutSeconds", decimal(z3_timeout_ms / 1000.0, 0)),
        macro("MpassEpsilonNs", decimal(M_PASS_EPSILON, 0)),
        macro("ReferencePoint", decimal(REFERENCE_POINT[0], 1)),
        macro("NumThreePasses", len(R3_PASSES)),
        macro("NumThreeCombinations", len(R3_PASSES) ** 2),
        macro("FourPrefixStages", R4_PREFIX_STAGES),
        macro("NumFivePreSequences", len(R5_BEFORE)),
        macro("NumFivePostSequences", len(R5_AFTER)),
        macro("NumFiveCombinations", len(R5_BEFORE) * len(R5_AFTER)),
        macro("SixSequencesPerKernel", R6_SEQUENCES_PER_KERNEL),
        macro("SixSequenceLength", R6_SEQUENCE_LENGTH),
        macro("SixCandidates", math.perm(len(R3_PASSES), R6_SEQUENCE_LENGTH)),
        macro("CanonicalPassCount", len(passes)),
        macro("ValidCanonicalPassCount", sum(1 for row in passes if row["valid"])),
        macro("SubstituteCount", len(substitutes["passes"])),
        macro("RejectedCanonicalCount", len(substitutes["rejected_canonical_passes"])),
    ]


def sweep_macros(master_rows, kernel_count):
    regimes = Counter(row["regime_id"] for row in master_rows)
    lines = [
        macro("NumSweeps", integer(len(master_rows))),
        macro("NumColumns", len(master_rows[0])),
        macro("SweepsPerKernel", len(master_rows) // kernel_count),
    ]
    for regime, word in REGIME_WORDS.items():
        lines.append(macro(f"Num{word}Sweeps", integer(regimes.get(regime, 0))))
    return lines


def status_macros(prefix, rows, status_column):
    counts = Counter(row[status_column] for row in rows)
    lines = [macro(f"{prefix}Rows", integer(len(rows)))]
    for status, word in STATUS_WORDS:
        lines.append(macro(f"{prefix}{word}Count", integer(counts.get(status, 0))))
        lines.append(macro(f"{prefix}{word}Pct", percent(counts.get(status, 0), len(rows))))
    return lines


def pareto_macros(pareto_rows, proof_rows):
    status_by_sweep = {row["sweep_id"]: row["z3_refinement_status"] for row in proof_rows}
    members = [row for row in pareto_rows if row["sweep_id"] in status_by_sweep]
    kernels = {row["kernel_id"] for row in pareto_rows}
    hypervolumes = {row["kernel_id"]: float(row["hypervolume_kernel"]) for row in pareto_rows}
    lines = [
        macro("ParetoPoints", integer(len(pareto_rows))),
        macro("ParetoKernels", len(kernels)),
        macro("MeanHypervolume", decimal(sum(hypervolumes.values()) / len(hypervolumes), 4)),
        macro("MeanHypervolumeMicro", decimal(sum(hypervolumes.values()) / len(hypervolumes) * 1e6, 2)),
    ]
    member_statuses = Counter(status_by_sweep[row["sweep_id"]] for row in members)
    lines.append(macro("ParetoMemberRows", integer(len(members))))
    for status, word in STATUS_WORDS:
        lines.append(macro(f"ParetoMember{word}Pct", percent(member_statuses.get(status, 0), len(members))))
    return lines


def nearest_rank(sorted_values, fraction):
    index = max(0, math.ceil(fraction * len(sorted_values)) - 1)
    return sorted_values[index]


def noise_macros(master_rows, proof_rows):
    """Timing noise, measured on sweeps whose optimized IR is identical to the canonical IR."""
    identical_ids = {row["sweep_id"] for row in proof_rows if row["ir_identical_to_canonical"] == "True"}
    deltas = sorted(
        abs(float(row["delta_cost_J"])) / float(row["cost_J_before"]) * 100.0
        for row in master_rows if row["sweep_id"] in identical_ids
    )
    if not deltas:
        raise ValueError("no sweeps with identical IR; the noise floor cannot be measured")
    return [
        macro("NoiseSweeps", integer(len(deltas))),
        macro("NoiseIdenticalPct", percent(len(deltas), len(master_rows))),
        macro("NoiseMedianAbsPct", decimal(nearest_rank(deltas, 0.5), 2)),
        macro("NoiseNinetyFifthAbsPct", decimal(nearest_rank(deltas, 0.95), 2)),
        macro("NoiseMaxAbsPct", decimal(deltas[-1], 2)),
    ]


def rpb_macros(rpb):
    lines, total_sweeps, weighted = [], 0, 0.0
    total_waste = 0.0
    for regime, word in REGIME_WORDS.items():
        values = rpb["by_regime"].get(regime)
        if values is None:
            continue
        lines.append(macro(f"Rpb{word}Mean", decimal(values["mean_rpb_ratio"], 3)))
        lines.append(macro(f"Waste{word}Seconds", decimal(values["total_waste_cycle_ms"] / 1000.0, 2)))
        total_sweeps += values["sweeps"]
        weighted += values["mean_rpb_ratio"] * values["sweeps"]
        total_waste += values["total_waste_cycle_ms"]
    lines.append(macro("RpbOverallMean", decimal(weighted / total_sweeps, 3)))
    lines.append(macro("WasteTotalSeconds", decimal(total_waste / 1000.0, 2)))
    return lines


def matrix_macros(prefix, matrix_rows, passes):
    entries = [(abs(float(row[second])), float(row[second])) for row in matrix_rows for second in passes]
    magnitudes = [magnitude for magnitude, _ in entries]
    return [
        macro(f"{prefix}MaxAbs", decimal(max(magnitudes), 4)),
        macro(f"{prefix}MeanAbs", decimal(sum(magnitudes) / len(magnitudes), 4)),
        macro(f"{prefix}Entries", integer(len(entries))),
    ]


def variant_macros(report, master_rows):
    """Counts behind the two sweep-level deviations: the instcombine spelling and the crash replacements."""
    spelling = report["instcombine_spelling"]
    retried = sum(1 for row in master_rows if VARIANT_SPELLING in row["pass_sequence_str"])
    reproduced = sum(1 for entry in report["crashes"] if entry["reproduced"])
    return [
        macro("RetriedSweeps", integer(retried)),
        macro("SpellingCandidates", integer(spelling["candidates"])),
        macro("SpellingIdentical", integer(spelling["identical"])),
        macro("SpellingDiffering", integer(spelling["differing_count"])),
        macro("ArchivedCrashes", len(report["crashes"])),
        macro("ArchivedCrashesReproduced", reproduced),
        macro("ArchivedReplacementRuns", sum(1 for entry in report["replacements"] if entry["runs"])),
    ]


def r5_macros(summary):
    largest = max(row["max_abs_pct"] for row in summary)
    return [
        macro("FiveMaxAbsPct", decimal(largest, 2)),
        macro("FiveSequencesJudged", len(summary)),
    ]


def agreement_macros(agreement):
    return [
        macro("EncodingMaxWidth", agreement["max_width"]),
        macro("EncodingCases", integer(agreement["total_cases"])),
        macro("EncodingMismatches", integer(agreement["total_mismatches"])),
        macro("EncodingFamilies", len(agreement["families"])),
    ]
