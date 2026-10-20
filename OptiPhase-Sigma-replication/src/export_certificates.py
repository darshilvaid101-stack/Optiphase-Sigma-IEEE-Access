"""Export SMT-LIB 2 certificates for the sweeps on the Pareto fronts, and re-check every query with the z3 binary.

Writes data/smt2_certificates/<sweep>.smt2.gz and data/smt2_certificates/manifest.json. Certificates are gzip-compressed
to keep the repository small; `gunzip` restores the plain SMT-LIB 2 text. The manifest records, for each sweep, the
query counts, the verdicts of the Python solver and of the z3 binary, and whether the sweep's status agrees with the
telemetry.
"""

import csv
import gzip
import json
import shutil
import sys
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed

from lib.build_layout import BUILD_ROOT, CANONICAL_LISTING_NAME, kernel_directory_name
from lib.certificate_export import export_sweep, sha256_text
from lib.kernel_catalog import all_kernels
from lib.kernel_registry import REPO_ROOT
from lib.z3_validator import STATUS_REFINES, STATUS_UNKNOWN, STATUS_VIOLATED
from task5_z3_verifier_and_math import optimized_listing

TELEMETRY = REPO_ROOT / "data" / "telemetry"
CERTIFICATE_DIR = REPO_ROOT / "data" / "smt2_certificates"
MANIFEST_PATH = CERTIFICATE_DIR / "manifest.json"
PARETO_PATH = TELEMETRY / "pareto_3d_frontiers.csv"
MASTER_PATH = TELEMETRY / "master_sweeps_28800.csv"
PROOFS_PATH = TELEMETRY / "z3_verification_proofs.csv"
WORKER_COUNT = 8
NOT_COMPARABLE = "NOT_COMPARABLE"


def sweep_status(verdicts):
    if STATUS_VIOLATED in verdicts:
        return STATUS_VIOLATED
    if STATUS_UNKNOWN in verdicts:
        return STATUS_UNKNOWN
    if STATUS_REFINES in verdicts:
        return STATUS_REFINES
    return NOT_COMPARABLE


def export_job(job):
    scratch = BUILD_ROOT / "certificate-scratch" / job["sweep_id"]
    scratch.mkdir(parents=True, exist_ok=True)
    try:
        canonical = (BUILD_ROOT / job["kernel_directory"] / CANONICAL_LISTING_NAME).read_text(encoding="utf-8")
        optimized = optimized_listing(job["kernel_directory"], job["pass_sequence"], scratch)
        record, certificate = export_sweep(job["sweep_id"], canonical, optimized, scratch / "check.smt2")
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
    with gzip.open(CERTIFICATE_DIR / f"{job['sweep_id']}.smt2.gz", "wt", encoding="utf-8") as handle:
        handle.write(certificate)
    verdicts = [entry["status"] for entry in record["queries"]]
    return {
        "sweep_id": job["sweep_id"],
        "queries": len(verdicts),
        "verdicts": dict(Counter(verdicts)),
        "cli_verdicts": record["cli_verdicts"],
        "cli_agreement": record["cli_agreement"],
        "sweep_status": sweep_status(verdicts),
        "certificate_sha256": sha256_text(certificate),
    }


def jobs_for_pareto_sweeps():
    pareto_sweeps = sorted({row["sweep_id"] for row in csv.DictReader(PARETO_PATH.open(encoding="utf-8", newline=""))})
    master = {row["sweep_id"]: row for row in csv.DictReader(MASTER_PATH.open(encoding="utf-8", newline=""))}
    directories = {kernel.kernel_id: kernel_directory_name(kernel) for kernel in all_kernels()}
    return [
        {"sweep_id": sweep, "kernel_directory": directories[master[sweep]["kernel_id"]],
         "pass_sequence": master[sweep]["pass_sequence_str"]}
        for sweep in pareto_sweeps
    ]


def main():
    CERTIFICATE_DIR.mkdir(parents=True, exist_ok=True)
    jobs = jobs_for_pareto_sweeps()
    stored = {row["sweep_id"]: row["z3_refinement_status"] for row in csv.DictReader(PROOFS_PATH.open(encoding="utf-8", newline=""))}
    records = []
    with ProcessPoolExecutor(max_workers=WORKER_COUNT) as pool:
        futures = [pool.submit(export_job, job) for job in jobs]
        for index, future in enumerate(as_completed(futures), start=1):
            records.append(future.result())
            if index % 200 == 0:
                print(f"exported {index}/{len(jobs)}", file=sys.stderr)
    records.sort(key=lambda record: record["sweep_id"])
    for record in records:
        record["stored_status"] = stored[record["sweep_id"]]
        record["status_agrees"] = record["sweep_status"] == record["stored_status"]
    totals = Counter()
    for record in records:
        totals["queries"] += record["queries"]
        totals["cli_agreement"] += record["cli_agreement"]
        totals["cli_verdicts"] += record["cli_verdicts"]
        totals["status_disagreements"] += 0 if record["status_agrees"] else 1
        totals.update({f"solver_{key}": value for key, value in record["verdicts"].items()})
    summary = {
        "sweeps": len(records),
        "queries": totals["queries"],
        "solver_verdicts": {key.replace("solver_", ""): value for key, value in totals.items() if key.startswith("solver_")},
        "cli_verdicts": totals["cli_verdicts"],
        "cli_agreement": totals["cli_agreement"],
        "sweep_status_disagreements_with_telemetry": totals["status_disagreements"],
    }
    MANIFEST_PATH.write_text(json.dumps({"summary": summary, "sweeps": records}, indent=1, sort_keys=True) + "\n",
                             encoding="utf-8")
    print(json.dumps(summary, sort_keys=True))
    return 0 if totals["cli_agreement"] == totals["queries"] and totals["status_disagreements"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
