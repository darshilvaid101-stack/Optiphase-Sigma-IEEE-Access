"""Classify the SAT witnesses of every SAT sweep and attribute each flag that the optimizer added to a pipeline stage.

A SAT witness is a name whose block-local refinement query is satisfiable. Its canonical and optimized defining
instructions are compared with the wrap and exactness flags removed. The witness is a flag gain when only flags
differ and the optimized instruction carries flags the canonical one lacks. For each gained flag, the sweep's pipeline
is replayed one top-level stage at a time, and the first stage whose listing carries that flag on the same name is
recorded. A name that no stage keeps is reported as untracked.

Writes data/telemetry/sat_witness_attribution.json.
"""

import csv
import json
import re
import shutil
import subprocess
import sys
import tempfile
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

from lib.build_layout import BUILD_ROOT, CANONICAL_LISTING_NAME, CANONICAL_NAME, kernel_directory_name
from lib.kernel_catalog import all_kernels
from lib.kernel_registry import REPO_ROOT
from lib.llvm_tools import tool_path
from lib.pipeline_prefix import split_top_level
from lib.telemetry_metrics import defined_functions
from lib.z3_validator import NotEncodable, STATUS_VIOLATED, blocks_of_function, check_refinement
from task5_z3_verifier_and_math import Z3_TIMEOUT_MS, optimized_listing, split_pass_sequence

TELEMETRY = REPO_ROOT / "data" / "telemetry"
PROOFS_PATH = TELEMETRY / "z3_verification_proofs.csv"
MASTER_PATH = TELEMETRY / "master_sweeps_28800.csv"
REPORT_PATH = TELEMETRY / "sat_witness_attribution.json"
FLAGS = ("nuw", "nsw", "exact", "disjoint", "nneg", "samesign")
FLAG_TOKEN = re.compile(r"(?<![%@!\w.$-])(nuw|nsw|exact|disjoint|nneg|samesign)(?![\w.$-])")
BLOCK_LABEL = re.compile(r"^(\d+|[A-Za-z_.$][\w.$-]*):")
PARAMETER_BLOCK = re.compile(r"<[^>]*>")
NAME_TOKEN = re.compile(r"[A-Za-z][A-Za-z0-9\-]*")
WRAPPER_PASSES = frozenset({"function", "loop", "loop-mssa", "cgscc", "module"})
ENTRY_LABEL = "entry"
GROUP_STAGE = "group"
WORKER_COUNT = 8
CLASS_FLAG_GAIN = "flag_gain"
CLASS_FLAG_SWAP = "flag_swap"
CLASS_FLAG_LOSS = "flag_loss"
CLASS_UNCHANGED = "unchanged_text"
CLASS_OTHER = "other_change"
GAIN_CLASSES = (CLASS_FLAG_GAIN, CLASS_FLAG_SWAP)
# Category A: a flag gain. Category B: a flag loss only. Category C: every other witness. Every class has one category,
# and an unmapped class raises KeyError, so no witness can drop out of the count.
CATEGORY_OF_CLASS = {
    CLASS_FLAG_GAIN: "A",
    CLASS_FLAG_SWAP: "A",
    CLASS_FLAG_LOSS: "B",
    CLASS_UNCHANGED: "C",
    CLASS_OTHER: "C",
}


def flags_of(line):
    return set(FLAG_TOKEN.findall(line))


def without_flags(line):
    return " ".join(FLAG_TOKEN.sub(" ", line).split())


def function_body(listing, function_name):
    """Return the lines between the define line and the closing brace, or [] when the function is absent."""
    lines = listing.splitlines()
    start = next((i for i, line in enumerate(lines) if line.startswith("define") and f"@{function_name}(" in line), None)
    if start is None:
        return []
    end = next((i for i in range(start + 1, len(lines)) if lines[i].startswith("}")), len(lines))
    return lines[start + 1:end]


def block_lines(body, label):
    collected, current = [], ENTRY_LABEL
    for line in body:
        found = BLOCK_LABEL.match(line)
        if found:
            current = found.group(1)
        if current == label:
            collected.append(line)
    return collected


def defining_line(lines, name):
    pattern = re.compile(rf"^\s*{re.escape(name)} = ")
    for line in lines:
        if pattern.match(line):
            return line.strip()
    return None


def classify(canonical_line, optimized_line):
    added = sorted(flags_of(optimized_line) - flags_of(canonical_line))
    removed = sorted(flags_of(canonical_line) - flags_of(optimized_line))
    if without_flags(canonical_line) != without_flags(optimized_line):
        return CLASS_OTHER, added, removed
    if added and removed:
        return CLASS_FLAG_SWAP, added, removed
    if added:
        return CLASS_FLAG_GAIN, added, removed
    if removed:
        return CLASS_FLAG_LOSS, added, removed
    return CLASS_UNCHANGED, added, removed


def pair_witnesses(pair):
    """Return the witness records of one canonical/optimized block pair."""
    try:
        statuses, _ = check_refinement(pair["canonical_block"], pair["optimized_block"], Z3_TIMEOUT_MS)
    except NotEncodable:
        return []
    canonical_lines = block_lines(pair["canonical_body"], pair["label"])
    optimized_lines = block_lines(pair["optimized_body"], pair["label"])
    records = []
    for name, status in sorted(statuses.items()):
        if status != STATUS_VIOLATED:
            continue
        canonical_line = defining_line(canonical_lines, name)
        optimized_line = defining_line(optimized_lines, name)
        witness_class, added, removed = classify(canonical_line, optimized_line)
        records.append({
            "function": pair["function"], "block": pair["label"], "name": name, "class": witness_class,
            "added": added, "removed": removed, "canonical": canonical_line, "optimized": optimized_line,
        })
    return records


def sat_witnesses(canonical, optimized):
    witnesses = []
    shared = set(defined_functions(canonical)) & set(defined_functions(optimized))
    for function_name in sorted(shared):
        canonical_blocks = {block.label: block for block in blocks_of_function(canonical, function_name)}
        optimized_blocks = {block.label: block for block in blocks_of_function(optimized, function_name)}
        canonical_body = function_body(canonical, function_name)
        optimized_body = function_body(optimized, function_name)
        for label in sorted(canonical_blocks.keys() & optimized_blocks.keys()):
            witnesses += pair_witnesses({
                "function": function_name, "label": label,
                "canonical_block": canonical_blocks[label], "optimized_block": optimized_blocks[label],
                "canonical_body": canonical_body, "optimized_body": optimized_body,
            })
    return witnesses


def stage_pass(stage):
    """The single pass of a stage, or the group label when the stage holds several passes."""
    tokens = [token for token in NAME_TOKEN.findall(PARAMETER_BLOCK.sub("", stage)) if token not in WRAPPER_PASSES]
    return tokens[0] if len(tokens) == 1 else GROUP_STAGE


def replay_arguments(canonical, pass_sequence):
    """The extra opt arguments that optimized_listing passes for this sweep, in the same order."""
    _, arguments, attribute = split_pass_sequence(pass_sequence)
    if not attribute:
        return list(arguments)
    return [f"-force-attribute={name}:{attribute}" for name in defined_functions(canonical)]


def replay_stage(prefix, replay):
    completed = subprocess.run(
        [tool_path("opt"), f"-passes={','.join(prefix)}", *replay["extra"], str(replay["source"]), "-S",
         "-o", str(replay["output"])],
        capture_output=True, text=True, check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(f"opt failed on a {len(prefix)}-stage prefix: exit {completed.returncode}")
    return replay["output"].read_text(encoding="utf-8")


def first_introductions(gained, stages, replay):
    """Map each (function, name, flag) to the first stage whose listing carries the flag on that name."""
    introduced = {}
    final_text = None
    for count in range(1, len(stages) + 1):
        text = replay_stage(stages[:count], replay)
        for function_name, name, flag in gained:
            key = (function_name, name, flag)
            if key in introduced:
                continue
            line = defining_line(function_body(text, function_name), name)
            if line is not None and flag in flags_of(line):
                introduced[key] = {"stage_index": count, "stage": stages[count - 1], "pass": stage_pass(stages[count - 1])}
        final_text = text
    return introduced, final_text


def witness_record(job, scratch):
    directory = BUILD_ROOT / job["kernel_directory"]
    canonical = (directory / CANONICAL_LISTING_NAME).read_text(encoding="utf-8")
    optimized = optimized_listing(job["kernel_directory"], job["pass_sequence"], scratch)
    witnesses = sat_witnesses(canonical, optimized)
    gained = [(w["function"], w["name"], flag) for w in witnesses if w["class"] in GAIN_CLASSES for flag in w["added"]]
    replay_exact = None
    if gained:
        pipeline, _, _ = split_pass_sequence(job["pass_sequence"])
        stages = split_top_level(pipeline)
        replay = {
            "extra": replay_arguments(canonical, job["pass_sequence"]),
            "source": directory / CANONICAL_NAME,
            "output": scratch / "replay.ll",
        }
        introduced, final_text = first_introductions(gained, stages, replay)
        replay_exact = final_text == optimized
        for witness in witnesses:
            witness["introduced"] = {
                flag: introduced.get((witness["function"], witness["name"], flag)) for flag in witness["added"]
            }
    return {
        "sweep_id": job["sweep_id"], "regime": job["regime_id"], "witnesses": witnesses, "replay_exact": replay_exact,
    }


def attribute_sweep(job):
    scratch = Path(tempfile.mkdtemp(prefix="sat-witness-"))
    try:
        return witness_record(job, scratch)
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


def sat_jobs():
    statuses = {row["sweep_id"]: row["z3_refinement_status"] for row in csv.DictReader(PROOFS_PATH.open(encoding="utf-8", newline=""))}
    directories = {kernel.kernel_id: kernel_directory_name(kernel) for kernel in all_kernels()}
    return [
        {"sweep_id": row["sweep_id"], "regime_id": row["regime_id"], "pass_sequence": row["pass_sequence_str"],
         "kernel_directory": directories[row["kernel_id"]]}
        for row in csv.DictReader(MASTER_PATH.open(encoding="utf-8", newline=""))
        if statuses.get(row["sweep_id"]) == STATUS_VIOLATED
    ]


def category_counts(records):
    counts = Counter(CATEGORY_OF_CLASS[w["class"]] for r in records for w in r["witnesses"])
    return {"A": counts["A"], "B": counts["B"], "C": counts["C"], "total": sum(counts.values())}


def summarize(records):
    witness_classes = Counter(w["class"] for r in records for w in r["witnesses"])
    gained_records = [r for r in records if any(w["class"] in GAIN_CLASSES for w in r["witnesses"])]
    flags_gained = Counter()
    passes = Counter()
    untracked = 0
    for record in records:
        for witness in record["witnesses"]:
            for flag, info in witness.get("introduced", {}).items():
                flags_gained[flag] += 1
                if info is None:
                    untracked += 1
                else:
                    passes[info["pass"]] += 1
    return {
        "sat_sweeps": len(records),
        "sat_sweeps_with_witness": sum(1 for r in records if r["witnesses"]),
        "sat_witnesses": sum(witness_classes.values()),
        "witness_classes": dict(sorted(witness_classes.items())),
        "witness_categories": category_counts(records),
        "sweeps_with_flag_gain": len(gained_records),
        "flags_gained_by_witnesses": {flag: flags_gained.get(flag, 0) for flag in FLAGS},
        "introductions_by_pass": dict(passes.most_common()),
        "untracked_introductions": untracked,
        "replays": sum(1 for r in records if r["replay_exact"] is not None),
        "replays_exact": sum(1 for r in records if r["replay_exact"]),
        "by_regime_flag_gain": dict(sorted(Counter(r["regime"] for r in gained_records).items())),
    }


def main():
    jobs = sat_jobs()
    records = []
    with ProcessPoolExecutor(max_workers=WORKER_COUNT) as pool:
        futures = [pool.submit(attribute_sweep, job) for job in jobs]
        for index, future in enumerate(as_completed(futures), start=1):
            records.append(future.result())
            if index % 250 == 0:
                print(f"analysed {index}/{len(jobs)}", file=sys.stderr)
    records.sort(key=lambda record: record["sweep_id"])
    report = {"summary": summarize(records), "sweeps": records}
    REPORT_PATH.write_text(json.dumps(report, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report["summary"], sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
