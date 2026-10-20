"""Rebuild the canonical bitcode of every kernel with the current canonical pipeline, and refresh the manifest.

The linked module of each kernel stays in its build directory, so only the canonicalization runs again. The lowered
canonical executables of the previous backend are removed, so the baseline phase lowers them again with the current one.
"""

import hashlib
import json
import shutil
import sys
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from lib.bitcode_pipeline import CANONICAL_NAME, CANONICAL_PASS, canonicalize, disassemble  # noqa: E402
from lib.build_layout import kernel_build_directory  # noqa: E402
from lib.kernel_catalog import all_kernels  # noqa: E402

CANONICAL_DIRECTORY = REPO_ROOT / "data" / "benchmarks" / "bitcode_O0_canon"
MANIFEST_PATH = CANONICAL_DIRECTORY / "MANIFEST.json"
LINKED_NAME = "linked.bc"
LOWERED_DIRECTORY_NAME = "llc-canonical"


def canonical_file_name(kernel):
    return kernel.kernel_id.replace("/", "__") + ".bc"


def rebuild_kernel(kernel, entry):
    build_dir = kernel_build_directory(kernel)
    canonicalize(build_dir / LINKED_NAME, build_dir / CANONICAL_NAME)
    disassemble(build_dir / CANONICAL_NAME, build_dir)
    shutil.rmtree(build_dir / LOWERED_DIRECTORY_NAME, ignore_errors=True)
    target = CANONICAL_DIRECTORY / canonical_file_name(kernel)
    shutil.copyfile(build_dir / CANONICAL_NAME, target)
    data = target.read_bytes()
    entry["canonical_sha256"] = hashlib.sha256(data).hexdigest()
    entry["canonical_bytes"] = str(len(data))


def main():
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    entries = {entry["kernel_id"]: entry for entry in manifest["kernels"]}
    kernels = list(all_kernels())
    for kernel in kernels:
        rebuild_kernel(kernel, entries[kernel.kernel_id])
    manifest["canonicalPass"] = f"opt {CANONICAL_PASS}"
    manifest["generatedUtc"] = datetime.now(UTC).isoformat(timespec="seconds")
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"rebuilt {len(kernels)} canonical modules with {CANONICAL_PASS}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
