"""SMT-LIB 2 certificates for the refinement queries of one sweep, and their re-check by the z3 binary.

Each comparable block pair contributes one query per shared name. A query is written as a `(reset)` block that declares
its symbols, asserts that the refinement is violated, and checks satisfiability. Any SMT-LIB 2 solver can therefore
reproduce the verdict, and the z3 command-line binary is used here as that independent check.
"""

import hashlib
import subprocess

import z3

from lib.block_parser import blocks_of_function
from lib.llvm_tools import tool_path
from lib.telemetry_metrics import defined_functions
from lib.z3_validator import NotEncodable, STATUS_REFINES, STATUS_UNKNOWN, STATUS_VIOLATED, name_queries

Z3_TIMEOUT_SECONDS = 5
CHECK_SAT_LINE = "(check-sat)"
CLI_VERDICTS = {"unsat": STATUS_REFINES, "sat": STATUS_VIOLATED, "unknown": STATUS_UNKNOWN}


def sweep_queries(canonical_text, optimized_text):
    """Return [(function, block, name, violation)] for every comparable block pair of the two listings."""
    queries = []
    shared = set(defined_functions(canonical_text)) & set(defined_functions(optimized_text))
    for function_name in sorted(shared):
        canonical_blocks = {block.label: block for block in blocks_of_function(canonical_text, function_name)}
        optimized_blocks = {block.label: block for block in blocks_of_function(optimized_text, function_name)}
        for label in sorted(canonical_blocks.keys() & optimized_blocks.keys()):
            try:
                pair_queries, _ = name_queries(canonical_blocks[label], optimized_blocks[label])
            except NotEncodable:
                continue
            queries.extend((function_name, label, name, violation) for name, violation in pair_queries)
    return queries


def query_block(violation):
    solver = z3.Solver()
    solver.add(violation)
    body = [line for line in solver.to_smt2().splitlines() if line.strip() != CHECK_SAT_LINE]
    return "\n".join(["(reset)", *body, CHECK_SAT_LINE]) + "\n"


def solver_verdict(result):
    if result == z3.unsat:
        return STATUS_REFINES
    if result == z3.sat:
        return STATUS_VIOLATED
    return STATUS_UNKNOWN


def solver_status(violation):
    solver = z3.Solver()
    solver.set("timeout", Z3_TIMEOUT_SECONDS * 1000)
    solver.add(violation)
    return solver_verdict(solver.check())


def cli_verdicts(certificate_text, scratch_path):
    scratch_path.write_text(certificate_text, encoding="utf-8")
    completed = subprocess.run(
        [tool_path("z3"), f"-T:{Z3_TIMEOUT_SECONDS}", str(scratch_path)], capture_output=True, text=True, check=False,
    )
    return [CLI_VERDICTS.get(line.strip(), STATUS_UNKNOWN) for line in completed.stdout.splitlines() if line.strip()]


def sha256_text(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def export_sweep(sweep_id, canonical_text, optimized_text, scratch_path):
    """Return (record, certificate text). The record lists every query with its solver verdict and CLI verdict."""
    queries = sweep_queries(canonical_text, optimized_text)
    entries, blocks = [], []
    for index, (function_name, label, name, violation) in enumerate(queries):
        text = query_block(violation)
        entries.append({
            "index": index, "function": function_name, "block": label, "name": name,
            "status": solver_status(violation), "sha256": sha256_text(text),
        })
        blocks.append(f"; query {index}: function {function_name}, block {label}, name {name}\n{text}")
    certificate = f"; OptiPhase-Sigma refinement certificate for sweep {sweep_id}\n" + "".join(blocks)
    verdicts = cli_verdicts(certificate, scratch_path)
    agreement = sum(1 for entry, verdict in zip(entries, verdicts) if entry["status"] == verdict)
    record = {
        "sweep_id": sweep_id,
        "queries": entries,
        "cli_verdicts": len(verdicts),
        "cli_agreement": agreement,
    }
    return record, certificate
