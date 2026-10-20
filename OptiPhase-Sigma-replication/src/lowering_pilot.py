"""Pilot for the lowering level: does llc -O2 change the size effect of a middle-end pass?

For each pilot kernel and pass, the canonical bitcode and the optimized bitcode are each lowered with llc at -O2 and at
-O0. The __text section of each object file is read with llvm-size, and the size change caused by the pass is compared
across the two lowering levels. The pilot uses object files, not linked executables, so its sizes are a proxy for the
sizes of the linked binaries in the sweeps. Output goes to data/telemetry/lowering_pilot.json.
"""

import json
import re
import subprocess
import tempfile
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
LLVM_BIN = Path("/opt/homebrew/opt/llvm/bin")
CANONICAL_DIR = REPO_ROOT / "data/benchmarks/bitcode_O0_canon"
OUTPUT_PATH = REPO_ROOT / "data/telemetry/lowering_pilot.json"
PILOT_KERNELS = ("mibench__basicmath", "mibench__sha", "polybench__3mm", "polybench__jacobi-2d")
PILOT_PASSES = ("early-cse", "instcombine", "gvn", "dce")
LOWERING_LEVELS = ("-O2", "-O0")
TEXT_SIZE_PATTERN = re.compile(r"\(__TEXT,\s*__text\):\s*(\d+)")


def run_tool(tool, arguments):
    completed = subprocess.run([str(LLVM_BIN / tool), *arguments], check=True, capture_output=True, text=True)
    return completed.stdout


def optimized_bitcode(workdir, canonical, pass_name):
    output = workdir / f"{canonical.stem}.{pass_name}.bc"
    run_tool("opt", [f"-passes={pass_name}", str(canonical), "-o", str(output)])
    return output


def text_bytes(workdir, bitcode, level):
    obj = workdir / f"{bitcode.stem}.{level.lstrip('-')}.o"
    run_tool("llc", [level, "-filetype=obj", str(bitcode), "-o", str(obj)])
    match = TEXT_SIZE_PATTERN.search(run_tool("llvm-size", ["-m", str(obj)]))
    if match is None:
        raise ValueError(f"no __text size in llvm-size output for {obj}")
    return int(match.group(1))


def classify_change(delta_o0, delta_o2):
    """Compare the -O2 size change with the -O0 size change of the same pass."""
    if delta_o0 == 0:
        return "no_change_at_O0"
    if delta_o2 == 0:
        return "vanished"
    if delta_o2 == delta_o0:
        return "same"
    if delta_o2 * delta_o0 < 0:
        return "sign_reversed"
    return "smaller" if abs(delta_o2) < abs(delta_o0) else "larger"


def pilot_cases(workdir):
    cases = []
    for kernel in PILOT_KERNELS:
        canonical = CANONICAL_DIR / f"{kernel}.bc"
        base = {level: text_bytes(workdir, canonical, level) for level in LOWERING_LEVELS}
        for pass_name in PILOT_PASSES:
            optimized = optimized_bitcode(workdir, canonical, pass_name)
            delta = {level: text_bytes(workdir, optimized, level) - base[level] for level in LOWERING_LEVELS}
            cases.append({
                "kernel": kernel,
                "pass": pass_name,
                "delta_O0_bytes": delta["-O0"],
                "delta_O2_bytes": delta["-O2"],
                "relation": classify_change(delta["-O0"], delta["-O2"]),
            })
    return cases


def main():
    with tempfile.TemporaryDirectory() as workdir_name:
        cases = pilot_cases(Path(workdir_name))
    report = {
        "llvm": run_tool("opt", ["--version"]).splitlines()[0].strip(),
        "measure": "__text section of llc object files, in bytes",
        "kernels": list(PILOT_KERNELS),
        "passes": list(PILOT_PASSES),
        "cases": cases,
        "relations": dict(Counter(case["relation"] for case in cases)),
    }
    OUTPUT_PATH.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report["relations"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
