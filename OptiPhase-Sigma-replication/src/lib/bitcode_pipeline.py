"""Build pipeline: sources to unoptimized bitcode, canonicalization, and native reference builds.

The canonical form runs mem2reg, then loop-simplify and lcssa. Loop passes need the simplified loop form, so the canonical
module establishes it before any sweep runs.
"""

from pathlib import Path

from lib.kernel_registry import REPO_ROOT
from lib.llvm_tools import run_tool

CANONICAL_CLANG_FLAGS = ("-O0", "-Xclang", "-disable-O0-optnone", "-emit-llvm", "-c")
NATIVE_CLANG_FLAGS = ("-O0",)
CANONICAL_PASS = "-passes=mem2reg,loop-simplify,lcssa"
CANONICAL_NAME = "canon.bc"
NATIVE_DIRECTORY_NAME = "native"
LISTING_NAME = "canon.ll"


def repo_path(relative):
    return REPO_ROOT / relative


def include_flags(spec):
    return [f"-I{repo_path(directory)}" for directory in spec.include_dirs]


def define_flags(spec):
    return [f"-D{definition}" for definition in spec.defines]


def compile_raw_module(spec, source, output):
    """Compile one source to unoptimized bitcode with the canonical O0 flags."""
    arguments = [
        *CANONICAL_CLANG_FLAGS,
        *spec.extra_flags,
        *include_flags(spec),
        *define_flags(spec),
        str(repo_path(source)),
        "-o",
        str(output),
    ]
    run_tool("clang", arguments)


def canonicalize(linked, canonical):
    """Apply the canonical pipeline to a linked module, writing the canonical bitcode."""
    run_tool("opt", [CANONICAL_PASS, str(linked), "-o", str(canonical)])
    return canonical


def build_canonical_bitcode(spec, build_dir):
    """Compile every source, link the modules, then canonicalize them; return the canonical path."""
    build_dir.mkdir(parents=True, exist_ok=True)
    raw_modules = []
    for index, source in enumerate(spec.sources):
        raw_module = build_dir / f"module_{index:02d}.bc"
        compile_raw_module(spec, source, raw_module)
        raw_modules.append(raw_module)
    linked = build_dir / "linked.bc"
    run_tool("llvm_link", [*map(str, raw_modules), "-o", str(linked)])
    return canonicalize(linked, build_dir / CANONICAL_NAME)


def disassemble(bitcode, build_dir):
    """Validate a bitcode module by disassembling it; return the listing path."""
    listing = build_dir / LISTING_NAME
    run_tool("llvm_dis", [str(bitcode), "-o", str(listing)])
    return listing


def build_native_executable(spec, build_dir):
    """Build the reference native executable from the same sources and flags, at -O0."""
    native_directory = build_dir / NATIVE_DIRECTORY_NAME
    native_directory.mkdir(parents=True, exist_ok=True)
    executable = native_directory / spec.program_name
    arguments = [
        *NATIVE_CLANG_FLAGS,
        *spec.extra_flags,
        *include_flags(spec),
        *define_flags(spec),
        *[str(repo_path(source)) for source in spec.sources],
        *spec.link_libraries,
        "-o",
        str(executable),
    ]
    run_tool("clang", arguments)
    return executable
