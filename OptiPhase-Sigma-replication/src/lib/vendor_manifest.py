"""Provenance manifests for vendored benchmark sources: per-file SHA-256 plus source metadata."""

import json
from datetime import UTC, datetime
from pathlib import Path

from lib.llvm_tools import sha256_file

MANIFEST_NAME = "MANIFEST.json"


def list_vendored_files(root):
    """Return every file under root except the manifest itself, as sorted relative paths."""
    base = Path(root)
    files = [path for path in base.rglob("*") if path.is_file() and path.name != MANIFEST_NAME]
    return sorted(path.relative_to(base).as_posix() for path in files)


def describe_files(root):
    base = Path(root)
    return [
        {"path": relative, "sha256": sha256_file(base / relative)}
        for relative in list_vendored_files(root)
    ]


def write_manifest(root, provenance):
    """Write MANIFEST.json with the caller's provenance fields plus a fresh per-file hash list."""
    manifest = {
        **provenance,
        "manifestGeneratedAtUtc": datetime.now(UTC).isoformat(timespec="seconds"),
        "fileCount": 0,
        "files": describe_files(root),
    }
    manifest["fileCount"] = len(manifest["files"])
    target = Path(root) / MANIFEST_NAME
    target.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return manifest
