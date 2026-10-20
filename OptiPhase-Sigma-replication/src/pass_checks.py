"""IR-level checks of the pass-interaction design, run on every canonical kernel.

Each pass of the R3 set is applied once and then a second time, on two canonical forms: the sweep canonical module
(mem2reg, loop-simplify, and lcssa), and the mem2reg-only module that the first campaign used, rebuilt from each kernel's linked
bitcode. The checks ask whether the pass changes the bitcode, and whether a repeated application changes it again. The output, data/telemetry/pass_checks.json, counts those outcomes per pass
and per canonical form, and lists the kernels where a changed module was left unchanged by the second application.
"""

import json
import subprocess
import sys
import tempfile
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from lib.build_layout import BUILD_ROOT  # noqa: E402
from lib.fixpoint_retry import VARIANT_SPELLING  # noqa: E402
from lib.pass_catalog import stage_by_name  # noqa: E402
from lib.pipeline_plans import R3_PASSES  # noqa: E402

LLVM_BIN = Path("/opt/homebrew/opt/llvm/bin")
CANONICAL_DIR = REPO_ROOT / "data/benchmarks/bitcode_O0_canon"
OUTPUT_PATH = REPO_ROOT / "data/telemetry/pass_checks.json"
LINKED_NAME = "linked.bc"
MEM2REG_PASSES = "mem2reg"
CANONICAL_LABEL = "canonical"
MEM2REG_LABEL = "mem2reg_only"


def run_opt(passes, source, target):
    arguments = [str(LLVM_BIN / "opt"), f"-passes={passes}", str(source), "-o", str(target)]
    subprocess.run(arguments, check=True, capture_output=True)


def apply_pass(source, target, pass_name):
    """Apply one pass as the sweeps do; instcombine falls back to the spelling the sweeps used after its fixpoint abort."""
    stage = stage_by_name()[pass_name]
    try:
        run_opt(stage, source, target)
    except subprocess.CalledProcessError:
        if pass_name != "instcombine":
            raise
        run_opt(stage.replace("instcombine", VARIANT_SPELLING), source, target)


def check_form(base, pass_name, workdir, label):
    first = workdir / f"{base.stem}.{pass_name}.{label}.1.bc"
    second = workdir / f"{base.stem}.{pass_name}.{label}.2.bc"
    apply_pass(base, first, pass_name)
    apply_pass(first, second, pass_name)
    return {
        "changed": base.read_bytes() != first.read_bytes(),
        "repeat_changed": first.read_bytes() != second.read_bytes(),
    }


def tally(counts, idempotent, pass_name, label, kernel_stem, outcome):
    entry = counts[pass_name][label]
    entry["kernels"] += 1
    entry["changed"] += outcome["changed"]
    entry["changed_then_repeat_changed"] += outcome["changed"] and outcome["repeat_changed"]
    if outcome["changed"] and not outcome["repeat_changed"]:
        idempotent[pass_name][label].append(kernel_stem)


def mem2reg_only_module(kernel, workdir):
    """The first campaign's canonical module, rebuilt from the kernel's linked bitcode (the build directory has the same name)."""
    target = workdir / f"{kernel.stem}.mem2reg.bc"
    run_opt(MEM2REG_PASSES, BUILD_ROOT / kernel.stem / LINKED_NAME, target)
    return target


def main():
    kernels = sorted(CANONICAL_DIR.glob("*.bc"))
    counts = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))
    idempotent = defaultdict(lambda: defaultdict(list))
    failures = defaultdict(int)
    with tempfile.TemporaryDirectory() as directory:
        workdir = Path(directory)
        for kernel in kernels:
            mem2reg_only = mem2reg_only_module(kernel, workdir)
            for pass_name in R3_PASSES:
                try:
                    plain = check_form(kernel, pass_name, workdir, CANONICAL_LABEL)
                    loop = check_form(mem2reg_only, pass_name, workdir, MEM2REG_LABEL)
                except subprocess.CalledProcessError:
                    failures[pass_name] += 1
                    continue
                tally(counts, idempotent, pass_name, CANONICAL_LABEL, kernel.stem, plain)
                tally(counts, idempotent, pass_name, MEM2REG_LABEL, kernel.stem, loop)
    version = subprocess.run([str(LLVM_BIN / "opt"), "--version"], check=True, capture_output=True, text=True)
    per_pass = {}
    for pass_name in R3_PASSES:
        per_pass[pass_name] = {}
        for label in (CANONICAL_LABEL, MEM2REG_LABEL):
            values = dict(counts[pass_name][label])
            values["idempotent_kernels"] = sorted(idempotent[pass_name][label])
            per_pass[pass_name][label] = values
    report = {
        "llvm": version.stdout.splitlines()[0].strip(),
        "kernels": len(kernels),
        "passes": list(R3_PASSES),
        "failures": dict(failures),
        "per_pass": per_pass,
    }
    OUTPUT_PATH.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"kernels={len(kernels)} passes={len(R3_PASSES)} failures={sum(failures.values())}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
