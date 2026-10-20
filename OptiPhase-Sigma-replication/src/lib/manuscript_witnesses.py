"""Macros for the witness-level SAT analysis: the flags the optimizer added to the instruction that a SAT answer names.

The counts come from data/telemetry/sat_witness_attribution.json (src/analyze_sat_witnesses.py). The totals are checked
against each other, so a report whose parts disagree stops the build instead of reaching the paper.
"""

import re

from lib.manuscript_macros import integer, macro, percent

SSA_NAME = re.compile(r"%[\w.$-]+")
OTHER_CHANGE = "other_change"
GAIN_CLASSES = ("flag_gain", "flag_swap")
FLAG_ONLY_CLASSES = ("flag_gain", "flag_swap", "flag_loss")
INTRODUCING_PASSES = (("instcombine", "Instcombine"), ("sccp", "Sccp"), ("indvars", "Indvars"))
FLAG_WORDS = (("nuw", "Nuw"), ("nsw", "Nsw"), ("nneg", "Nneg"), ("samesign", "Samesign"), ("exact", "Exact"),
              ("disjoint", "Disjoint"))


def renamed_only_count(sweeps):
    """Count other-change witnesses whose two instructions differ only in the names of their SSA operands."""
    count = 0
    for sweep in sweeps:
        for witness in sweep["witnesses"]:
            if witness["class"] != OTHER_CHANGE:
                continue
            canonical, optimized = witness["canonical"], witness["optimized"]
            if canonical and optimized and SSA_NAME.sub("%v", canonical) == SSA_NAME.sub("%v", optimized):
                count += 1
    return count


def gained_sweep_count(sweeps):
    return sum(1 for sweep in sweeps if any(w["class"] in GAIN_CLASSES for w in sweep["witnesses"]))


def check_totals(summary, sweeps):
    introduced = sum(summary["introductions_by_pass"].values()) + summary["untracked_introductions"]
    gained = sum(summary["flags_gained_by_witnesses"].values())
    if gained != introduced:
        raise ValueError(f"flags gained {gained} differ from located and untracked introductions {introduced}")
    if summary["witness_categories"]["total"] != summary["sat_witnesses"]:
        raise ValueError("witness categories A, B, and C do not cover every SAT witness")
    if gained_sweep_count(sweeps) != summary["sweeps_with_flag_gain"]:
        raise ValueError("sweeps_with_flag_gain does not match the per-sweep witness classes")


def pass_macros(passes, located):
    lines = []
    for key, word in INTRODUCING_PASSES:
        count = passes.get(key, 0)
        lines += [macro(f"Intro{word}", integer(count)), macro(f"Intro{word}Pct", percent(count, located))]
    return lines


def witness_macros(report):
    summary, sweeps = report["summary"], report["sweeps"]
    check_totals(summary, sweeps)
    classes = summary["witness_classes"]
    gained_flags = summary["flags_gained_by_witnesses"]
    passes = summary["introductions_by_pass"]
    gained_sweeps = summary["sweeps_with_flag_gain"]
    sat_sweeps = summary["sat_sweeps"]
    located = sum(passes.values())
    named_total = sum(passes.get(key, 0) for key, _ in INTRODUCING_PASSES)
    flag_only = sum(classes.get(name, 0) for name in FLAG_ONLY_CLASSES)
    categories = summary["witness_categories"]
    lines = [
        macro("WitnessCatA", integer(categories["A"])),
        macro("WitnessCatB", integer(categories["B"])),
        macro("WitnessCatC", integer(categories["C"])),
        macro("WitnessCatTotal", integer(categories["total"])),
        macro("WitnessFlagOnly", integer(flag_only)),
        macro("WitnessFlagOnlyPct", percent(flag_only, summary["sat_witnesses"])),
        macro("WitnessGainSweeps", integer(gained_sweeps)),
        macro("WitnessGainSweepsPct", percent(gained_sweeps, sat_sweeps)),
        macro("WitnessNoGainSweeps", integer(sat_sweeps - gained_sweeps)),
        macro("WitnessNoGainSweepsPct", percent(sat_sweeps - gained_sweeps, sat_sweeps)),
        macro("WitnessTotal", integer(summary["sat_witnesses"])),
        macro("WitnessFlagGain", integer(classes.get("flag_gain", 0))),
        macro("WitnessFlagSwap", integer(classes.get("flag_swap", 0))),
        macro("WitnessFlagLoss", integer(classes.get("flag_loss", 0))),
        macro("WitnessUnchangedText", integer(classes.get("unchanged_text", 0))),
        macro("WitnessOtherChange", integer(classes.get(OTHER_CHANGE, 0))),
        macro("WitnessRenamedOnly", integer(renamed_only_count(sweeps))),
        macro("WitnessGainedFlags", integer(sum(gained_flags.values()))),
        macro("IntroLocated", integer(located)),
        macro("IntroOther", integer(located - named_total)),
        macro("IntroUntracked", integer(summary["untracked_introductions"])),
        macro("ReplaysExact", integer(summary["replays_exact"])),
        macro("Replays", integer(summary["replays"])),
    ]
    for key, word in FLAG_WORDS:
        lines.append(macro(f"Gained{word}", integer(gained_flags.get(key, 0))))
    return lines + pass_macros(passes, located)
