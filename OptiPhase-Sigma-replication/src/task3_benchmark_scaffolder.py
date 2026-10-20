"""Task 3: build each benchmark kernel to canonical SSA bitcode and verify it against native runs."""

import json
import shutil
import sys
import tempfile
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

from lib.bitcode_pipeline import build_canonical_bitcode, build_native_executable, disassemble
from lib.kernel_catalog import all_kernels
from lib.kernel_execution import KernelRunError, execute_kernel, lli_launcher, native_launcher
from lib.kernel_registry import REPO_ROOT
from lib.llvm_tools import ToolError, run_tool, sha256_file

BUILD_ROOT = REPO_ROOT / "data" / "benchmarks" / "_build"
RUN_ROOT = BUILD_ROOT / "_runs"
BITCODE_DIRECTORY = REPO_ROOT / "data" / "benchmarks" / "bitcode_O0_canon"
MANIFEST_PATH = BITCODE_DIRECTORY / "MANIFEST.json"
GATE_KERNEL_COUNT = 60
ERROR_TEXT_LIMIT = 2000


def log(message):
    timestamp = datetime.now(UTC).strftime("%H:%M:%S")
    print(f"[{timestamp}] {message}", file=sys.stderr, flush=True)


def kernel_directory_name(spec):
    return spec.kernel_id.replace("/", "__")


def run_digest(spec, launcher):
    """Run one kernel under a launcher in a fresh scratch directory and return its digest."""
    scratch = Path(tempfile.mkdtemp(prefix="run-", dir=RUN_ROOT))
    try:
        return execute_kernel(spec, launcher, scratch)
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


def verify_built_kernel(spec, canonical, executable, named_bitcode):
    """Compare two native runs (determinism) and one lli run (IR matches the native build)."""
    native_first = run_digest(spec, native_launcher(executable))
    native_second = run_digest(spec, native_launcher(executable))
    lli_digest = run_digest(spec, lli_launcher(named_bitcode))
    return {
        "native_digest_run1": native_first,
        "native_digest_run2": native_second,
        "lli_digest": lli_digest,
        "native_deterministic": native_first == native_second,
        "lli_matches_native": lli_digest == native_first,
    }


def build_and_verify(spec):
    """Build, disassemble, and verify one kernel; failures are recorded, never raised."""
    build_dir = BUILD_ROOT / kernel_directory_name(spec)
    record = {"kernel_id": spec.kernel_id, "suite": spec.suite, "status": "failed"}
    try:
        canonical = build_canonical_bitcode(spec, build_dir)
        listing = disassemble(canonical, build_dir)
        executable = build_native_executable(spec, build_dir)
        named_bitcode = build_dir / spec.program_name
        shutil.copyfile(canonical, named_bitcode)
        record.update(verify_built_kernel(spec, canonical, executable, named_bitcode))
        record.update(
            canonical_sha256=sha256_file(canonical),
            canonical_bytes=canonical.stat().st_size,
            llvm_dis_valid=listing.stat().st_size > 0,
        )
        record["status"] = "verified" if all(
            (record["native_deterministic"], record["lli_matches_native"], record["llvm_dis_valid"])
        ) else "mismatch"
        shutil.copyfile(canonical, BITCODE_DIRECTORY / f"{kernel_directory_name(spec)}.bc")
    except (ToolError, KernelRunError) as error:
        record["error"] = str(error)[:ERROR_TEXT_LIMIT]
    return record


def toolchain_versions():
    clang_banner = run_tool("clang", ["--version"]).stdout.splitlines()[0]
    opt_banner = run_tool("opt", ["--version"]).stdout.splitlines()[0]
    return {"clang": clang_banner, "opt": opt_banner}


def write_manifest(records):
    verified = [record for record in records if record["status"] == "verified"]
    manifest = {
        "generatedUtc": datetime.now(UTC).isoformat(timespec="seconds"),
        "toolchain": toolchain_versions(),
        "canonicalFlags": ["-O0", "-Xclang", "-disable-O0-optnone", "-emit-llvm", "-c"],
        "canonicalPass": "opt -passes=mem2reg",
        "gate3": {
            "requiredKernels": GATE_KERNEL_COUNT,
            "verifiedKernels": len(verified),
            "passed": len(verified) == GATE_KERNEL_COUNT,
        },
        "kernels": records,
    }
    BITCODE_DIRECTORY.mkdir(parents=True, exist_ok=True)
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return manifest


def main():
    BUILD_ROOT.mkdir(parents=True, exist_ok=True)
    RUN_ROOT.mkdir(parents=True, exist_ok=True)
    kernels = all_kernels()
    records = []
    for index, spec in enumerate(kernels, start=1):
        log(f"[{index}/{len(kernels)}] {spec.kernel_id}")
        record = build_and_verify(spec)
        record["spec"] = {key: list(value) if isinstance(value, tuple) else value for key, value in asdict(spec).items()}
        records.append(record)
        log(f"    status={record['status']}" + (f" error={record['error'][:160]}" if "error" in record else ""))
    manifest = write_manifest(records)
    log(f"verified {manifest['gate3']['verifiedKernels']}/{len(kernels)} kernels; gate 3 passed: {manifest['gate3']['passed']}")
    return 0 if manifest["gate3"]["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
