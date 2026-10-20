"""Macros, tables, and figure data for the instruction-count interaction, the IR-level pass checks, and the pass-time waste.

Instruction counts are exact for each kernel, so their interactions carry no timing noise, and they do not pass through
the backend. The pass checks come from src/pass_checks.py. The waste uses the pass time that -time-passes reports for each
sweep, not the wall time of the optimizer process.
"""

from collections import defaultdict
from math import sqrt
from statistics import fmean, stdev

from lib.fixpoint_retry import canonical_spelling
from lib.manuscript_macros import decimal, integer, macro
from lib.manuscript_tables import ruled_table
from lib.pass_catalog import stage_by_name
from lib.pipeline_plans import R3_PASSES
from lib.uncertainty import Z_CRITICAL, count_significant

TABLE_ROWS = 12


def instcount_interactions(master_rows):
    """Per kernel, (dN_ij - dN_i - dN_j) / N0, keyed by the ordered pair of R3 passes."""
    stages = stage_by_name()
    canonical, single, pair = {}, {}, {}
    for row in master_rows:
        kernel = row["kernel_id"]
        canonical.setdefault(kernel, int(row["ir_inst_before"]))
        names = [canonical_spelling(part) for part in row["pass_sequence_str"].split(",")]
        if row["regime_id"] == "R2":
            single[(kernel, names[0])] = int(row["ir_delta_inst"])
        elif row["regime_id"] == "R3":
            pair[(kernel, names[0], names[1])] = int(row["ir_delta_inst"])
    values = defaultdict(list)
    for kernel in sorted(canonical):
        for first in R3_PASSES:
            for second in R3_PASSES:
                a, b = stages[first], stages[second]
                unexplained = pair[(kernel, a, b)] - single[(kernel, a)] - single[(kernel, b)]
                values[(first, second)].append(unexplained / canonical[kernel])
    return values


def interaction_statistics(values):
    return {key: (fmean(items), stdev(items) / sqrt(len(items))) for key, items in values.items()}


def instcount_macros(stats):
    selves = {key: value for key, value in stats.items() if key[0] == key[1]}
    return [
        macro("InstInteractionCells", integer(len(stats))),
        macro("InstInteractionConsistentCells", integer(count_significant(stats))),
        macro("InstInteractionSelfCells", integer(len(selves))),
        macro("InstInteractionSelfConsistentCells", integer(count_significant(selves))),
        macro("InstInteractionMaxAbsPct", decimal(100 * max(abs(mean) for mean, _ in stats.values()), 2)),
    ]


def instcount_table(stats):
    entries = sorted(stats.items(), key=lambda item: -abs(item[1][0]))[:TABLE_ROWS]
    body = []
    for (first, second), (mean, se) in entries:
        consistent = "yes" if abs(mean) > Z_CRITICAL * se else "no"
        body.append([first, second, f"{100 * mean:+.2f}", f"{100 * se:.2f}", consistent])
    return ruled_table(
        "Largest instruction-count interactions over kernels, as a percentage of the canonical instruction count, with "
        "standard errors across kernels. The standard errors measure how much the kernels differ; the counts are exact.",
        "tab:instcount", ["First pass", "Second pass", "Mean (\\%)", "SE (\\%)", "Beyond 2 SE"], body, "llrrl",
    )


LOOP_PASSES = ("licm", "indvars", "loop-rotate", "loop-unroll", "loop-vectorize")
CANONICAL_FORM = "canonical"
MEM2REG_FORM = "mem2reg_only"


def changed_count(checks, name, form):
    return checks["per_pass"][name][form]["changed"]


def pass_checks_macros(checks):
    repeat_shares = [
        form["changed_then_repeat_changed"] / form["changed"]
        for passes in checks["per_pass"].values()
        for form in [passes["canonical"]]
        if form["changed"]
    ]
    unroll = checks["per_pass"]["loop-unroll"]
    return [
        macro("PassChecksKernels", integer(checks["kernels"])),
        macro("PassChecksPasses", integer(len(checks["passes"]))),
        macro("PassChecksUnrollCanonicalChanged", integer(unroll["canonical"]["changed"])),
        macro("PassChecksUnrollMemTwoRegChanged", integer(unroll["mem2reg_only"]["changed"])),
        macro("PassChecksLoopMinCanonical", integer(min(changed_count(checks, name, CANONICAL_FORM) for name in LOOP_PASSES))),
        macro("PassChecksLoopMinMemTwoReg", integer(min(changed_count(checks, name, MEM2REG_FORM) for name in LOOP_PASSES))),
        macro("PassChecksOtherMaxDiff", integer(max(
            abs(changed_count(checks, name, CANONICAL_FORM) - changed_count(checks, name, MEM2REG_FORM))
            for name in checks["passes"] if name != "loop-unroll"
        ))),
        macro("PassChecksRepeatMinPct", decimal(100 * min(repeat_shares), 0)),
        macro("PassChecksRepeatMaxPct", decimal(100 * max(repeat_shares), 0)),
    ]


def pass_checks_table(checks):
    body = []
    for name in checks["passes"]:
        canonical = checks["per_pass"][name]["canonical"]
        mem2reg = checks["per_pass"][name]["mem2reg_only"]
        body.append([
            name, str(canonical["changed"]), str(canonical["changed_then_repeat_changed"]),
            str(mem2reg["changed"]), str(mem2reg["changed_then_repeat_changed"]),
        ])
    return ruled_table(
        f"IR-level checks over {checks['kernels']} kernels. Changed counts the kernels where the pass changes the module, on "
        "the sweep canonical form and on the mem2reg-only form. Repeated counts the kernels where a second application changes it again, "
        "out of those where the first changed it.",
        "tab:passchecks", ["Pass", "Changed", "Repeated", "Mem2reg: changed", "Mem2reg: repeated"],
        body, "lrrrr",
    )


def pass_time_waste(master_rows):
    """Milliseconds of pass time spent on redundant executions, per regime, from each sweep's opt_pass_ms."""
    waste = defaultdict(float)
    for row in master_rows:
        waste[row["regime_id"]] += float(row["opt_pass_ms"]) * float(row["rpb_ratio"])
    return dict(waste)


def with_pass_time_waste(rpb, master_rows):
    waste = pass_time_waste(master_rows)
    for regime, values in rpb["by_regime"].items():
        values["total_waste_cycle_ms"] = waste[regime]
    return rpb


IDENTITY_TOLERANCE = 1e-12


def self_identity_macros(master_rows, checks):
    """Where a second application leaves the bitcode unchanged, dN_aa = dN_a, so the self-interaction is -dN_a / N0."""
    stages = stage_by_name()
    canonical, single, pair = {}, {}, {}
    for row in master_rows:
        kernel = row["kernel_id"].replace("/", "__")
        canonical.setdefault(kernel, int(row["ir_inst_before"]))
        names = [canonical_spelling(part) for part in row["pass_sequence_str"].split(",")]
        if row["regime_id"] == "R2":
            single[(kernel, names[0])] = int(row["ir_delta_inst"])
        elif row["regime_id"] == "R3":
            pair[(kernel, names[0], names[1])] = int(row["ir_delta_inst"])
    cases = mismatches = 0
    for name in R3_PASSES:
        stage = stages[name]
        for kernel in checks["per_pass"][name]["canonical"]["idempotent_kernels"]:
            single_delta = single[(kernel, stage)]
            interaction = (pair[(kernel, stage, stage)] - 2 * single_delta) / canonical[kernel]
            cases += 1
            mismatches += abs(interaction + single_delta / canonical[kernel]) > IDENTITY_TOLERANCE
    return [
        macro("InstSelfIdentityCases", integer(cases)),
        macro("InstSelfIdentityMismatches", integer(mismatches)),
    ]


def instcount_outputs(master_rows, checks):
    """Return (macro lines, {table file name: tex}) for the instruction-count and IR-level analyses."""
    stats = interaction_statistics(instcount_interactions(master_rows))
    macros = instcount_macros(stats) + pass_checks_macros(checks) + self_identity_macros(master_rows, checks)
    tables = {
        "table_instcount.tex": instcount_table(stats),
        "table_pass_checks.tex": pass_checks_table(checks),
    }
    return macros, tables
