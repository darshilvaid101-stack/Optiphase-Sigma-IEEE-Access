"""Interference of the R5 cleanup sequences with loop-vectorize.

For a kernel G, a pre-pivot sequence b and the pivot p = loop-vectorize, the interference is
    I_b(G) = (delta(b then p | G) - delta(p | G)) / J0(G),
where each delta is a paired within-window difference against the canonical build and J0(G) is the canonical cost
of the pivot-only sweep. Post-pivot sequences a are treated the same way: I_a(G) = (delta(p then a | G) - delta(p | G))
/ J0(G). The sweep IDs encode the position of each sequence in the R5 product, so no label is needed.
"""

import statistics
from collections import defaultdict

from lib.pipeline_plans import R5_AFTER, R5_BEFORE, static_plans

R5_REGIME = "R5"
EMPTY = ()
# Sweep IDs carry the index in the full static plan list, so the R5 position is the offset from the first R5 plan.
R5_FIRST_INDEX = next(index for index, plan in enumerate(static_plans()) if plan.regime_id == R5_REGIME)


def r5_position(sweep_id):
    """Return (before, after) sequences encoded in an R5 sweep ID such as K03-R5-389."""
    index = int(sweep_id.rsplit("-", 1)[1]) - R5_FIRST_INDEX
    before_index, after_index = divmod(index, len(R5_AFTER))
    return R5_BEFORE[before_index], R5_AFTER[after_index]


def deltas_by_kernel(master_rows):
    """Map kernel -> {(before, after): (delta, J0)} for the R5 rows."""
    table = defaultdict(dict)
    for row in master_rows:
        if row["regime_id"] != R5_REGIME:
            continue
        before, after = r5_position(row["sweep_id"])
        table[row["kernel_id"]][(before, after)] = (
            float(row["delta_cost_J"]), float(row["cost_J_before"]),
        )
    return table


def interference_records(master_rows):
    """Return one record per kernel and sequence: {'kernel', 'position', 'sequence', 'effect'} (effect is a fraction of J0)."""
    records = []
    for kernel_id, cells in deltas_by_kernel(master_rows).items():
        pivot = cells.get((EMPTY, EMPTY))
        if pivot is None:
            continue
        pivot_delta, pivot_j0 = pivot
        for (before, after), (delta, _) in cells.items():
            if before != EMPTY and after == EMPTY:
                effect = (delta - pivot_delta) / pivot_j0
                records.append({"kernel": kernel_id, "position": "before", "sequence": before, "effect": effect})
            if after != EMPTY and before == EMPTY:
                effect = (delta - pivot_delta) / pivot_j0
                records.append({"kernel": kernel_id, "position": "after", "sequence": after, "effect": effect})
    return records


def summarize(records):
    """Mean, median, and largest absolute effect per (position, sequence), as percentages of J0."""
    groups = defaultdict(list)
    for record in records:
        groups[(record["position"], record["sequence"])].append(record["effect"] * 100.0)
    summary = []
    for (position, sequence), effects in sorted(groups.items()):
        summary.append({
            "position": position,
            "sequence": sequence,
            "kernels": len(effects),
            "mean_pct": statistics.fmean(effects),
            "median_pct": statistics.median(effects),
            "max_abs_pct": max(abs(effect) for effect in effects),
        })
    return summary
