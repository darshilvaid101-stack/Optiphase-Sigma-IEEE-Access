"""Macros and tables for the uncertainty of the interference estimates, computed from the stored telemetry."""

import statistics

from lib.manuscript_macros import decimal, integer, macro, percent
from lib.manuscript_tables import ruled_table
from lib.pass_algebra import M_PASS_EPSILON
from lib.pipeline_plans import R3_PASSES
from lib.r5_interference import interference_records
from lib.uncertainty import (
    Z_CRITICAL,
    count_beyond_noise,
    count_significant,
    interaction_per_kernel,
    kernel_sigma,
    lie_per_kernel,
    mean_and_standard_error,
    mpass_per_kernel,
    relative_sigma,
)

TABLE_ROWS = 12
SIGNIFICANCE_LABEL = "Beyond 2 SE"


def noise_standard_deviation(master_rows, proof_rows):
    identical = {row["sweep_id"] for row in proof_rows if row["ir_identical_to_canonical"] == "True"}
    return kernel_sigma(master_rows, identical)


def mpass_statistics(observations, sigma_ns):
    """Mean and standard error of each tensor entry: with the directive's epsilon, and with a per-kernel noise floor."""
    standard = mpass_per_kernel(observations, R3_PASSES, lambda observation: M_PASS_EPSILON)
    noise_aware = mpass_per_kernel(
        observations, R3_PASSES, lambda observation: Z_CRITICAL * sigma_ns[observation["kernel"]],
    )
    return (
        {key: mean_and_standard_error(values) for key, values in standard.items()},
        {key: mean_and_standard_error(values) for key, values in noise_aware.items()},
    )


def noise_dominated_share(observations, sigma_ns):
    """Share of (kernel, entry) denominators below twice the kernel's noise standard deviation."""
    total = dominated = 0
    for observation in observations:
        floor = Z_CRITICAL * sigma_ns[observation["kernel"]]
        for first in R3_PASSES:
            for second in R3_PASSES:
                denominator = max(M_PASS_EPSILON, abs(observation["single"][first]) + abs(observation["single"][second]))
                total += 1
                dominated += denominator < floor
    return dominated, total


def entry_table(stats, caption, label, scale=1.0, digits=4, value_names=("Mean", "SE")):
    entries = sorted(stats.items(), key=lambda item: -abs(item[1][0]))[:TABLE_ROWS]
    body = []
    for (first, second), (mean, se) in entries:
        beyond = "yes" if abs(mean) > Z_CRITICAL * se else "no"
        body.append([first, second, f"{mean * scale:+.{digits}f}", f"{se * scale:.{digits}f}", beyond])
    headers = ["First pass", "Second pass", *value_names, SIGNIFICANCE_LABEL]
    return ruled_table(caption, label, headers, body, "llrrl")


COMPARISON_PAIRS = (
    ("dse", "dse"), ("licm", "licm"), ("early-cse", "early-cse"), ("gvn", "gvn"), ("sccp", "sccp"),
    ("jump-threading", "loop-vectorize"),
)


def comparison_table(ratio_stats, interaction_stats):
    body = []
    for pair in COMPARISON_PAIRS:
        ratio_mean, ratio_se = ratio_stats[pair]
        interaction_mean, interaction_se = interaction_stats[pair]
        body.append([
            pair[0], pair[1], f"{ratio_mean:+.2f}", f"{ratio_se:.2f}",
            f"{100 * interaction_mean:+.2f}", f"{100 * interaction_se:.2f}",
        ])
    return ruled_table(
        "The same pass pairs under the ratio estimator (Equation~\\ref{eq:ratio}) and under the timing interaction normalized "
        "by the canonical cost (Equation~\\ref{eq:timing}). The ratio columns are dimensionless. The interaction columns are "
        "percentages of the canonical cost.",
        "tab:comparison",
        ["First pass", "Second pass", "Ratio mean", "Ratio SE", "Mean (\\%)", "SE (\\%)"],
        body, "llrrrr",
    )


def r5_rows(master_rows, sigma_ns, j0_ns):
    relative = relative_sigma(sigma_ns, j0_ns)
    groups = {}
    for record in interference_records(master_rows):
        groups.setdefault((record["position"], record["sequence"]), {})[record["kernel"]] = record["effect"]
    rows = []
    for (position, sequence), effects in sorted(groups.items()):
        values = list(effects.values())
        mean, se = mean_and_standard_error(values)
        rows.append({
            "position": position, "sequence": sequence, "mean": mean, "se": se,
            "median": statistics.median(values), "beyond": count_beyond_noise(effects, relative),
        })
    return rows


def r5_table(rows):
    body = []
    for row in rows:
        sequence = "+".join(row["sequence"]) or "none"
        body.append([
            row["position"], sequence, f"{row['mean'] * 100:+.2f}", f"{row['se'] * 100:.2f}",
            f"{row['median'] * 100:+.2f}", str(row["beyond"]),
        ])
    return ruled_table(
        "Interference of cleanup sequences with \\texttt{loop-vectorize}, as a percentage of the canonical cost. Mean, "
        "standard error, and median are over kernels. The last column counts kernels whose effect exceeds two noise "
        "standard deviations of that kernel.",
        "tab:r5", ["Position", "Sequence", "Mean (\\%)", "SE (\\%)", "Median (\\%)", "Beyond noise"],
        body, "llrrrr",
    )


def uncertainty_outputs(master_rows, proof_rows, observations, baselines):
    """Return (macro lines, {table file name: tex}) for the uncertainty analysis."""
    sigma_ns = noise_standard_deviation(master_rows, proof_rows)
    j0_ns = {kernel: record["median_ns"] for kernel, record in baselines.items()}
    standard, noise_aware = mpass_statistics(observations, sigma_ns)
    dominated, total = noise_dominated_share(observations, sigma_ns)
    lie = {key: mean_and_standard_error(values) for key, values in lie_per_kernel(master_rows, baselines, R3_PASSES).items()}
    r5 = r5_rows(master_rows, sigma_ns, j0_ns)
    interaction = {
        key: mean_and_standard_error(values)
        for key, values in interaction_per_kernel(observations, R3_PASSES, j0_ns).items()
    }
    distinct = {key: value for key, value in interaction.items() if key[0] != key[1]}
    self_pairs = {key: value for key, value in interaction.items() if key[0] == key[1]}
    macros = [
        macro("MpassSignificantCells", integer(count_significant(standard))),
        macro("MpassNoiseAwareSignificantCells", integer(count_significant(noise_aware))),
        macro("MpassCells", integer(len(standard))),
        macro("MpassNoiseDominatedPct", percent(dominated, total)),
        macro("LieSignificantCells", integer(count_significant(lie))),
        macro("LieCells", integer(len(lie))),
        macro("RFiveSequencesSignificant", integer(sum(1 for row in r5 if abs(row["mean"]) > Z_CRITICAL * row["se"]))),
        macro("RFiveSequencesJudged", len(r5)),
        macro("RFiveKernelsBeyondNoiseMax", max(row["beyond"] for row in r5)),
        macro("InteractionSignificantCells", integer(count_significant(interaction))),
        macro("InteractionCells", integer(len(interaction))),
        macro("InteractionDistinctSignificantCells", integer(count_significant(distinct))),
        macro("InteractionSelfSignificantCells", integer(count_significant(self_pairs))),
        macro("InteractionMaxAbsPct", decimal(100 * max(abs(mean) for mean, _ in interaction.values()), 2)),
        macro("InteractionSelfCells", integer(len(self_pairs))),
        macro("InteractionSelfPositiveCells", integer(sum(1 for mean, _ in self_pairs.values() if mean > 0))),
    ]
    tables = {
        "table_mpass.tex": entry_table(
            standard,
            "Largest entries of the ratio estimator, $\\mathbf{M}^{\\mathrm{ratio}}_{\\mathrm{pass}}$ (Equation~\\ref{eq:ratio}), with standard errors. "
            "An entry is marked when its magnitude exceeds two standard errors.",
            "tab:mpass",
        ),
        "table_comparison.tex": comparison_table(standard, interaction),
        "table_interaction.tex": entry_table(
            interaction,
            "Largest pairwise interaction entries over kernels, as a percentage of the canonical cost, with standard errors. "
            "Each entry is the mean of $(\\Delta_{ij}-\\Delta_i-\\Delta_j)/J_0$ over kernels.",
            "tab:interaction",
            scale=100.0,
            digits=3,
            value_names=("Mean (\\%)", "SE (\\%)"),
        ),
        "table_lie.tex": entry_table(
            lie,
            "Largest mean Lie-bracket commutators over kernels, in units of the canonical cost, with standard errors.",
            "tab:lie",
        ),
        "table_r5.tex": r5_table(r5),
    }
    return macros, tables
