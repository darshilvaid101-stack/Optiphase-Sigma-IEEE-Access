"""Declarative description of one benchmark kernel: its sources, build flags, and run command."""

from dataclasses import dataclass


@dataclass(frozen=True)
class KernelSpec:
    """Everything needed to build one kernel to bitcode and run it reproducibly.

    Paths are repository-relative. Arguments are relative to the scratch run directory,
    which is a fresh copy of run_directory, or an empty directory when run_directory is "".
    setup_arguments are program invocations executed first to produce this kernel's inputs.
    staged_files maps repository-relative sources to run-relative destinations.
    volatile_patterns are regular expressions for wall-clock fields the benchmark prints;
    they are masked before hashing so the digest covers deterministic output only.
    """

    kernel_id: str
    suite: str
    sources: tuple
    include_dirs: tuple
    defines: tuple
    extra_flags: tuple
    link_libraries: tuple
    run_directory: str
    program_name: str
    arguments: tuple
    stdin_file: str
    setup_arguments: tuple
    staged_files: tuple
    volatile_patterns: tuple
