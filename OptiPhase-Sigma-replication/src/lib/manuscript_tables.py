"""Tables for the manuscript, in the IEEE Access grid style, each generated from the stored outputs."""

import re
from collections import Counter, defaultdict

from lib.manuscript_macros import integer, percent

MAX_MATRIX_ROWS = 12
REGIME_PURPOSES = {
    "R1": "Standard and size levels",
    "R2": "Single passes",
    "R3": "Ordered pairs",
    "R4": "O3 prefixes",
    "R5": "Pass interference",
    "R6": "M\\_pass sequences",
}
SMT_COLUMNS = ("UNSAT", "SAT", "UNKNOWN", "NOT_COMPARABLE")
R5_PIVOT = "loop-vectorize"
R5_NONE = "none"
SPELLING_MARKER = re.compile(r"<[^>]*>")
PASS_CALL = re.compile(r"function\(([^)]*)\)")
SMT_HEADER = ("Regime", "Sweeps", "UNSAT", "SAT", "Unknown", "Not comparable", "Failed")


TABLE_COLUMN_GAP = "\\setlength{\\tabcolsep}{3pt}"


def ruled_table(caption, label, header, body, alignment):
    """A centred table in the IEEE Access style: the caption above, vertical rules, and a horizontal rule after every row."""
    columns = "|" + "|".join(alignment) + "|"
    lines = [
        "\\begin{table}[t]",
        "\\centering",
        f"\\caption{{{caption}}}",
        f"\\label{{{label}}}",
        TABLE_COLUMN_GAP,
        f"\\begin{{tabular}}{{{columns}}}",
        "\\hline",
        " & ".join(header) + " \\\\",
        "\\hline",
    ]
    for row in body:
        lines += [" & ".join(row) + " \\\\", "\\hline"]
    lines += ["\\end{tabular}", "\\end{table}", ""]
    return "\n".join(lines)


def regime_table(master_rows):
    counts = Counter(row["regime_id"] for row in master_rows)
    body = [[regime, purpose, integer(counts.get(regime, 0))] for regime, purpose in REGIME_PURPOSES.items()]
    body.append(["Total", "", integer(sum(counts.values()))])
    return ruled_table("Sweeps per regime.", "tab:regimes", ["Regime", "Purpose", "Sweeps"], body, "llr")


def smt_table(proof_rows):
    by_regime = defaultdict(Counter)
    for row in proof_rows:
        by_regime[row["regime_id"]][row["z3_refinement_status"]] += 1
    body = []
    for regime in REGIME_PURPOSES:
        counter = by_regime.get(regime)
        if not counter:
            continue
        total = sum(counter.values())
        shares = [percent(counter.get(status, 0), total) + "\\%" for status in SMT_COLUMNS]
        other = counter.get("ERROR", 0) + counter.get("IR_NOT_REPRODUCED", 0)
        body.append([regime, integer(total), *shares, percent(other, total) + "\\%"])
    return ruled_table(
        "Block-local refinement outcome per sweep, as a percentage of the sweeps in each regime. Failed counts tool "
        "errors and optimized IR that did not reproduce.",
        "tab:smt", list(SMT_HEADER), body, "lrrrrrr",
    )


def pareto_table(pareto_rows, suite_by_kernel):
    by_suite = defaultdict(dict)
    for row in pareto_rows:
        suite = suite_by_kernel[row["kernel_id"]]
        entry = by_suite[suite].setdefault(
            row["kernel_id"], {"hypervolume": float(row["hypervolume_kernel"]), "front": 0},
        )
        entry["front"] += 1
    body = []
    for suite in sorted(by_suite):
        kernels = by_suite[suite].values()
        hypervolumes = [entry["hypervolume"] for entry in kernels]
        fronts = [entry["front"] for entry in kernels]
        body.append([
            suite.replace("_", "\\_"), str(len(hypervolumes)),
            f"{sum(hypervolumes) / len(hypervolumes) * 1e6:.2f}",
            f"{sum(fronts) / len(fronts):.1f}",
        ])
    return ruled_table(
        "Exact three-objective hypervolume at the reference point (0.5, 0.5, 0.5), in units of $10^{-6}$, and "
        "Pareto-front size, averaged over the kernels of each suite.",
        "tab:pareto", ["Suite", "Kernels", "Mean hypervolume ($\\times10^{-6}$)", "Mean front size"], body, "lrrr",
    )


def matrix_table(matrix_rows, passes, caption, label):
    entries = [
        (float(row[second]), row["first_pass"], second)
        for row in matrix_rows for second in passes
    ]
    entries.sort(key=lambda entry: -abs(entry[0]))
    body = [[first, second, f"{value:+.4f}"] for value, first, second in entries[:MAX_MATRIX_ROWS]]
    return ruled_table(caption, label, ["First pass", "Second pass", "Value"], body, "llr")


def encoding_table(agreement):
    body = [
        [family, integer(counts["cases"]), integer(counts["mismatches"])]
        for family, counts in agreement["families"].items()
    ]
    return ruled_table(
        f"Exhaustive agreement between the Z3 encoder and the reference semantics, widths 1 to "
        f"{agreement['max_width']}, per instruction family.",
        "tab:encoding", ["Family", "Cases", "Mismatches"], body, "lrr",
    )


def r5_table(summary):
    body = []
    for row in summary:
        sequence = "+".join(row["sequence"])
        body.append([
            row["position"], sequence, integer(row["kernels"]), f"{row['mean_pct']:+.2f}",
            f"{row['median_pct']:+.2f}", f"{row['max_abs_pct']:.2f}",
        ])
    return ruled_table(
        "Interference of cleanup sequences with \\texttt{loop-vectorize}. The effect is the change in cost, relative to "
        "the canonical cost, caused by adding the sequence to the pivot-only pipeline, in percent. Positive values mean "
        "slower.",
        "tab:r5", ["Position", "Sequence", "Kernels", "Mean (\\%)", "Median (\\%)", "Max abs (\\%)"], body, "llrrrr",
    )


def rpb_table(rpb):
    body = []
    for regime, purpose in REGIME_PURPOSES.items():
        values = rpb["by_regime"].get(regime)
        if values is None:
            continue
        body.append([
            regime, purpose, f"{values['mean_rpb_ratio']:.3f}",
            f"{values['total_waste_cycle_ms'] / 1000.0:.2f}",
        ])
    return ruled_table(
        "Redundant pass events and estimated compile-time waste per regime. The ratio is the mean over sweeps of "
        "the fraction of pass executions that -print-changed reports as unchanged. Waste is the sum over sweeps of "
        "compile time multiplied by that ratio.",
        "tab:rpb", ["Regime", "Purpose", "Mean ratio", "Waste (s)"], body, "llrr",
    )


def logical_pass_names(sequence):
    """Pass names of a pipeline string, with spelling markers removed so retried spellings count as one sequence."""
    return [SPELLING_MARKER.sub("", name) for name in PASS_CALL.findall(sequence)]


def sequence_label(names):
    return ", ".join(names) if names else R5_NONE


def r5_sequence_table(master_rows):
    """The cleanup sequences of R5 on each side of loop-vectorize, with the sweeps that contain each one."""
    pre_counts, post_counts = Counter(), Counter()
    for row in master_rows:
        if row["regime_id"] != "R5":
            continue
        names = logical_pass_names(row["pass_sequence_str"])
        pivot = names.index(R5_PIVOT)
        pre_counts[sequence_label(names[:pivot])] += 1
        post_counts[sequence_label(names[pivot + 1:])] += 1
    body = [["Pre-pivot", sequence, integer(count)] for sequence, count in ordered_counts(pre_counts)]
    body += [["Post-pivot", sequence, integer(count)] for sequence, count in ordered_counts(post_counts)]
    caption = ("Cleanup sequences of R5 before and after \\texttt{loop-vectorize}. Each row counts the sweeps that "
               "contain the sequence at that position, over all kernels.")
    return ruled_table(caption, "tab:r5seq", ["Position", "Sequence", "Sweeps"], body, "llr")


def ordered_counts(counts):
    """Sequences in a fixed reading order: the empty sequence first, then alphabetical."""
    return sorted(counts.items(), key=lambda item: (item[0] != R5_NONE, item[0]))
