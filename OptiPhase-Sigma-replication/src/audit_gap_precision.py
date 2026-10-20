"""Recount the gap-precision audit from the stored judgments and check it against the published numbers.

The candidate and refined tiers are recounted from data/literature/gap_precision_audit_sample.csv, which holds one row
per judged gap, and their Wilson 95% intervals are recomputed. Each row is first checked against the mined gap it names,
so the judgments cannot drift from the mining output. The strict census (17 gaps) has aggregate counts only: its per-row
judgments were not retained. Its counts are carried over from the stored JSON and marked as not reproducible.

Run: .venv/bin/python src/audit_gap_precision.py
The script exits with status 1, and leaves the JSON unchanged, when a recounted value differs from the stored one.
"""

import csv
import json
import math
import sys

from lib.kernel_registry import REPO_ROOT

LITERATURE = REPO_ROOT / "data" / "literature"
SAMPLE_PATH = LITERATURE / "gap_precision_audit_sample.csv"
MINED_PATH = LITERATURE / "mined_gaps_1000.csv"
CONFIDENCE_PATH = LITERATURE / "mined_gaps_audit.jsonl"
AUDIT_PATH = LITERATURE / "gap_precision_audit.json"
METHOD = (
    "Judgments by one AI assistant (Claude) against two written criteria. Limitation: the sentence states a limitation "
    "of existing work or the approach, an unsolved problem, or an unmet need. Cluster: the assigned cluster matches its "
    "definition in config/gap_regex_patterns.json (or the remedy text). Wilson 95% intervals. Each judgment was made"
    "once; no human re-judged the sample."
)
RECOUNTED_TIERS = ("candidate", "refined")
STRICT_TIER_KEYS = (
    "n",
    "limitation_yes",
    "limitation_precision",
    "limitation_wilson95",
    "cluster_yes",
    "cluster_precision",
    "cluster_wilson95",
)
STRICT_TIER = "strict_census"
WILSON_Z_95 = 1.959963984540054
INTERVAL_DIGITS = 4
YES = "yes"


def load_csv(path):
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def load_confidence():
    with CONFIDENCE_PATH.open(encoding="utf-8") as handle:
        return {record["gap_id"]: record["confidence"] for record in map(json.loads, handle)}


def wilson_interval(successes, trials):
    proportion = successes / trials
    z_squared = WILSON_Z_95 ** 2
    centre = (proportion + z_squared / (2 * trials)) / (1 + z_squared / trials)
    spread = WILSON_Z_95 * math.sqrt(proportion * (1 - proportion) / trials + z_squared / (4 * trials ** 2))
    half_width = spread / (1 + z_squared / trials)
    return [round(centre - half_width, INTERVAL_DIGITS), round(centre + half_width, INTERVAL_DIGITS)]


def tier_entry(rows):
    trials = len(rows)
    limitation_yes = sum(1 for row in rows if row["limitation_judgement"] == YES)
    cluster_yes = sum(1 for row in rows if row["cluster_judgement"] == YES)
    return {
        "n": trials,
        "limitation_yes": limitation_yes,
        "limitation_precision": round(limitation_yes / trials, INTERVAL_DIGITS),
        "limitation_wilson95": wilson_interval(limitation_yes, trials),
        "cluster_yes": cluster_yes,
        "cluster_precision": round(cluster_yes / trials, INTERVAL_DIGITS),
        "cluster_wilson95": wilson_interval(cluster_yes, trials),
    }


def check_against_mined(rows, confidence):
    mined = {row["gap_id"]: row for row in load_csv(MINED_PATH)}
    problems = []
    for row in rows:
        source = mined.get(row["gap_id"])
        if source is None:
            problems.append(f"{row['gap_id']}: not in mined_gaps_1000.csv")
        elif source["extracted_limitation_sentence"] != row["sentence"]:
            problems.append(f"{row['gap_id']}: sentence differs from the mined gap")
        elif source["cluster_id"] != row["cluster_id"]:
            problems.append(f"{row['gap_id']}: cluster differs from the mined gap")
        elif confidence.get(row["gap_id"]) != row["tier"]:
            problems.append(f"{row['gap_id']}: tier differs from mined_gaps_audit.jsonl")
    return problems


def build_report(rows, stored):
    tiers = {tier: tier_entry([row for row in rows if row["tier"] == tier]) for tier in RECOUNTED_TIERS}
    strict = {key: stored["tiers"][STRICT_TIER][key] for key in STRICT_TIER_KEYS}
    tiers[STRICT_TIER] = {**strict, "judgments_retained": False}
    return {"method": METHOD, "tiers": tiers}


def differences(report, stored):
    found = []
    for tier in RECOUNTED_TIERS:
        for key, value in report["tiers"][tier].items():
            stored_value = stored["tiers"][tier].get(key)
            if stored_value != value:
                found.append(f"{tier}.{key}: stored {stored_value!r}, recounted {value!r}")
    return found


def main():
    rows = load_csv(SAMPLE_PATH)
    problems = check_against_mined(rows, load_confidence())
    if problems:
        print("\n".join(problems), file=sys.stderr)
        return 1
    stored = json.loads(AUDIT_PATH.read_text(encoding="utf-8"))
    report = build_report(rows, stored)
    found = differences(report, stored)
    if found:
        print("\n".join(found), file=sys.stderr)
        return 1
    AUDIT_PATH.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    for tier, entry in report["tiers"].items():
        print(f"{tier}: n={entry['n']} limitation={entry['limitation_yes']} cluster={entry['cluster_yes']}")
    print("reproduced: candidate and refined tiers match the stored values")
    return 0


if __name__ == "__main__":
    sys.exit(main())
