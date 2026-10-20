"""Analyse the block-local refinement verdicts against the telemetry and the observed outputs.

Three questions, each answered from stored outputs or from a re-derivation that uses the same code as Task 5:

1. Coverage. Why are sweeps NOT_COMPARABLE? Either no block label matched between the canonical and optimized
   listings, or every matched block was outside the encodable fragment.
2. Candidate counterexamples. For each SAT sweep, does the optimized IR add a wrap or exactness flag (nuw, nsw, exact,
   disjoint, nneg, samesign) that the canonical IR does not carry? Such a flag is the usual reason a block-local check
   cannot see the fact that justifies it.
3. Observed outputs. Do the benchmark outputs agree with the canonical outputs for each verdict? The bitcount
   re-verification (verify_bitcount_digests.py) supersedes the audit digests for that kernel.

Writes data/telemetry/refinement_analysis.json.
"""

import csv
import json
import re
import sys
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

from lib.build_layout import BUILD_ROOT, CANONICAL_LISTING_NAME, kernel_directory_name
from lib.kernel_catalog import all_kernels
from lib.kernel_registry import REPO_ROOT
from lib.z3_validator import STATUS_VIOLATED
from task5_z3_verifier_and_math import optimized_listing

TELEMETRY = REPO_ROOT / "data" / "telemetry"
PROOFS_PATH = TELEMETRY / "z3_verification_proofs.csv"
MASTER_PATH = TELEMETRY / "master_sweeps_28800.csv"
AUDIT_PATH = TELEMETRY / "sweep_audit.jsonl"
BITCOUNT_CHECK_PATH = TELEMETRY / "bitcount_output_check.json"
REPORT_PATH = TELEMETRY / "refinement_analysis.json"
FLAG_PATTERN = re.compile(r"\b(nuw|nsw|exact|disjoint|nneg|samesign)\b")
FLAGS = ("nuw", "nsw", "exact", "disjoint", "nneg", "samesign")
WORKER_COUNT = 8
BITCOUNT_KERNEL = "mibench/bitcount"


def flag_counts(listing_text):
    counts = Counter()
    for line in listing_text.splitlines():
        if line.startswith(" ") and "=" in line:
            counts.update(FLAG_PATTERN.findall(line))
    return {flag: counts.get(flag, 0) for flag in FLAGS}


def flags_added(job):
    """Re-derive the optimized IR as Task 5 does and compare its flag counts with the canonical IR."""
    scratch = BUILD_ROOT / "analysis-scratch" / job["sweep_id"]
    scratch.mkdir(parents=True, exist_ok=True)
    try:
        canonical = (BUILD_ROOT / job["kernel_directory"] / CANONICAL_LISTING_NAME).read_text(encoding="utf-8")
        optimized = optimized_listing(job["kernel_directory"], job["pass_sequence"], scratch)
    finally:
        for path in scratch.glob("*"):
            path.unlink()
        scratch.rmdir()
    before, after = flag_counts(canonical), flag_counts(optimized)
    added = {flag: max(0, after[flag] - before[flag]) for flag in FLAGS}
    return {"sweep_id": job["sweep_id"], "added": added}


def coverage_report(proofs):
    reasons = Counter()
    for row in proofs:
        if row["z3_refinement_status"] != "NOT_COMPARABLE":
            continue
        if int(row["blocks_matched"]) == 0:
            reasons["no_block_label_matched"] += 1
        else:
            reasons["matched_blocks_all_outside_fragment"] += 1
    totals = {
        key: sum(int(row[key]) for row in proofs)
        for key in ("blocks_matched", "blocks_compared", "blocks_not_encodable", "names_refines", "names_violated",
                    "names_unknown")
    }
    return {"not_comparable_reasons": dict(reasons), "totals": totals}


def digest_report(audit_latest, master_kernel, statuses, bitcount_matches):
    """Output agreement per verdict. Bitcount uses the re-verification, which supersedes the audit digests."""
    table = Counter()
    for sweep_id, status in statuses.items():
        record = audit_latest.get(sweep_id)
        if record is None or record["status"] != "ok":
            continue
        kernel = master_kernel[sweep_id]
        if kernel == BITCOUNT_KERNEL:
            matches = bitcount_matches[sweep_id]
        else:
            matches = record["digest_matches_canonical"]
        table[(status, kernel == BITCOUNT_KERNEL, matches)] += 1
    return [
        {"status": status, "bitcount": bitcount, "output_matches_canonical": matches, "sweeps": count}
        for (status, bitcount, matches), count in sorted(table.items())
    ]


def main():
    proofs = list(csv.DictReader(PROOFS_PATH.open(encoding="utf-8", newline="")))
    master = list(csv.DictReader(MASTER_PATH.open(encoding="utf-8", newline="")))
    master_kernel = {row["sweep_id"]: row["kernel_id"] for row in master}
    statuses = {row["sweep_id"]: row["z3_refinement_status"] for row in proofs}
    bitcount_check = json.loads(BITCOUNT_CHECK_PATH.read_text(encoding="utf-8"))
    bitcount_matches = bitcount_check["matches"]
    audit_latest = {}
    for line in AUDIT_PATH.read_text(encoding="utf-8").splitlines():
        if line.strip():
            record = json.loads(line)
            audit_latest[record["sweep_id"]] = record
    directories = {kernel.kernel_id: kernel_directory_name(kernel) for kernel in all_kernels()}
    sat_jobs = [
        {"sweep_id": row["sweep_id"], "pass_sequence": row["pass_sequence_str"],
         "kernel_directory": directories[row["kernel_id"]]}
        for row in master if statuses.get(row["sweep_id"]) == STATUS_VIOLATED
    ]
    flag_results = []
    with ProcessPoolExecutor(max_workers=WORKER_COUNT) as pool:
        futures = [pool.submit(flags_added, job) for job in sat_jobs]
        for future in as_completed(futures):
            flag_results.append(future.result())
    adds_flag = [result for result in flag_results if any(result["added"].values())]
    flag_totals = Counter()
    for result in flag_results:
        flag_totals.update({flag: count for flag, count in result["added"].items() if count})
    report = {
        "coverage": coverage_report(proofs),
        "sat_candidates": {
            "sweeps": len(flag_results),
            "adding_wrap_or_exactness_flag": len(adds_flag),
            "flags_added_by_sweep": {flag: sum(1 for r in flag_results if r["added"][flag]) for flag in FLAGS},
        },
        "outputs_by_verdict": digest_report(audit_latest, master_kernel, statuses, bitcount_matches),
        "bitcount_recheck": {
            "sweeps_checked": bitcount_check["sweeps_checked"],
            "sweeps_matching_canonical": bitcount_check["sweeps_matching_canonical"],
        },
    }
    REPORT_PATH.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"sat_sweeps": report["sat_candidates"]["sweeps"],
                      "adding_flag": report["sat_candidates"]["adding_wrap_or_exactness_flag"]}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
