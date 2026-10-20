"""Where build products live: per-kernel build directories and the tracked bitcode directory."""

from lib.kernel_registry import REPO_ROOT

BUILD_ROOT = REPO_ROOT / "data" / "benchmarks" / "_build"
BITCODE_DIRECTORY = REPO_ROOT / "data" / "benchmarks" / "bitcode_O0_canon"
CANONICAL_NAME = "canon.bc"
CANONICAL_LISTING_NAME = "canon.ll"
NATIVE_DIRECTORY_NAME = "native"


def kernel_directory_name(spec):
    return spec.kernel_id.replace("/", "__")


def kernel_build_directory(spec):
    return BUILD_ROOT / kernel_directory_name(spec)
