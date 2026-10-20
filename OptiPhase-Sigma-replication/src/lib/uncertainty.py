"""Uncertainty for the interference estimates: standard errors across kernels, and each kernel's own timing noise.

The noise scale of a kernel is taken from its identical-IR sweeps, whose paired deltas measure nothing but timing noise.
Their median absolute delta m gives a standard deviation estimate of 1.4826 * m for a zero-centred normal distribution.
A per-kernel effect is said to exceed the noise when it is larger than Z_CRITICAL standard deviations of that kernel.
Standard errors are the sample standard deviation over kernels divided by the square root of the kernel count. These are
parametric summaries, and no hypothesis test is run.
"""

import math
import statistics
from collections import defaultdict

from lib.fixpoint_retry import canonical_spelling
from lib.pass_catalog import stage_by_name

Z_CRITICAL = 2.0
MAD_TO_SIGMA = 1.4826


def mean_and_standard_error(values):
    if len(values) < 2:
        return statistics.fmean(values), math.nan
    return statistics.fmean(values), statistics.stdev(values) / math.sqrt(len(values))


def kernel_sigma(master_rows, identical_ids):
    """Standard deviation estimate of the paired delta for each kernel, in nanoseconds."""
    deltas = defaultdict(list)
    for row in master_rows:
        if row["sweep_id"] in identical_ids:
            deltas[row["kernel_id"]].append(abs(float(row["delta_cost_J"])))
    return {kernel: MAD_TO_SIGMA * statistics.median(values) for kernel, values in deltas.items()}


def mpass_per_kernel(observations, passes, epsilon_for):
    """Per-kernel summands of the transition tensor. epsilon_for(observation) gives that kernel's denominator floor."""
    summands = defaultdict(list)
    for observation in observations:
        for first in passes:
            for second in passes:
                delta_first = observation["single"][first]
                delta_second = observation["single"][second]
                after_first = observation["pair"][(first, second)] - delta_first
                summands[(first, second)].append(
                    m_pass_entry_with_floor(after_first, delta_second, delta_first, epsilon_for(observation))
                )
    return summands


def interaction_per_kernel(observations, passes, j0_ns_by_kernel):
    """Per-kernel pairwise interaction (dJ_ij - dJ_i - dJ_j) / J0: the part of a pair's cost its two singles do not explain."""
    summands = defaultdict(list)
    for observation in observations:
        j0_ns = j0_ns_by_kernel[observation["kernel"]]
        for first in passes:
            for second in passes:
                unexplained = (
                    observation["pair"][(first, second)] - observation["single"][first] - observation["single"][second]
                )
                summands[(first, second)].append(unexplained / j0_ns)
    return summands


def m_pass_entry_with_floor(delta_second_after_first, delta_second, delta_first, floor):
    denominator = max(floor, abs(delta_second) + abs(delta_first))
    return (delta_second_after_first - delta_second) / denominator


def lie_per_kernel(rows, baselines, passes):
    """Per-kernel commutators (dJ(i then j) - dJ(j then i)) / J0, from the paired R3 deltas."""
    name_of_stage = {stage: name for name, stage in stage_by_name().items()}
    pair_delta = {}
    for row in rows:
        if row["regime_id"] != "R3":
            continue
        first_stage, second_stage = canonical_spelling(row["pass_sequence_str"]).split(",")
        pair_delta[(row["kernel_id"], name_of_stage[first_stage], name_of_stage[second_stage])] = float(row["delta_cost_J"])
    values = defaultdict(list)
    kernels = sorted({kernel for kernel, _, _ in pair_delta})
    for kernel in kernels:
        j0 = baselines[kernel]["median_ns"]
        for first in passes:
            for second in passes:
                forward = pair_delta.get((kernel, first, second))
                backward = pair_delta.get((kernel, second, first))
                if forward is not None and backward is not None:
                    values[(first, second)].append((forward - backward) / j0)
    return values


def count_significant(stats):
    return sum(1 for mean, se in stats.values() if not math.isnan(se) and abs(mean) > Z_CRITICAL * se)


def relative_sigma(sigma_ns_by_kernel, j0_ns_by_kernel):
    """Noise standard deviation as a fraction of each kernel's canonical cost."""
    return {kernel: sigma_ns_by_kernel[kernel] / j0_ns_by_kernel[kernel] for kernel in sigma_ns_by_kernel}


def count_beyond_noise(effects_by_kernel, relative_sigma_by_kernel):
    """Number of kernels whose effect (a fraction of canonical cost) exceeds Z_CRITICAL noise deviations."""
    return sum(
        1 for kernel, effect in effects_by_kernel.items()
        if abs(effect) > Z_CRITICAL * relative_sigma_by_kernel[kernel]
    )
