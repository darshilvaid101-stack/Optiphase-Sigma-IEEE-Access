"""Run a kernel natively or under lli in a fresh scratch directory and digest all observable output."""

import hashlib
import re
import shutil
import subprocess
from pathlib import Path

from lib.kernel_registry import REPO_ROOT
from lib.llvm_tools import tool_path

RUN_TIMEOUT_SECONDS = 900
RUN_DIRECTORY_NAME = "run"
MASKED_TEXT = b"<volatile>"


class KernelRunError(RuntimeError):
    """A kernel invocation timed out."""


def repo_path(relative):
    return REPO_ROOT / relative


def stage_run_directory(spec, scratch):
    """Create the run directory: a copy of the kernel's data directory, plus staged inputs."""
    run_directory = scratch / RUN_DIRECTORY_NAME
    if spec.run_directory:
        shutil.copytree(repo_path(spec.run_directory), run_directory)
    else:
        run_directory.mkdir(parents=True)
    for source, destination in spec.staged_files:
        target = run_directory / destination
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(repo_path(source), target)
    return run_directory


def invoke(launcher, arguments, run_directory, stdin_file):
    """Run launcher + arguments in run_directory, feeding stdin_file when one is named."""
    command = [*launcher, *arguments]
    if stdin_file:
        with (run_directory / stdin_file).open("rb") as stdin_handle:
            return run_command(command, run_directory, stdin_handle)
    return run_command(command, run_directory, subprocess.DEVNULL)


def run_command(command, run_directory, stdin_source):
    """Run a command and return its result. Non-zero exits are data, not errors: the
    official runme scripts do not check status, and the exit code is part of the digest."""
    try:
        return subprocess.run(
            command,
            cwd=run_directory,
            stdin=stdin_source,
            capture_output=True,
            timeout=RUN_TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired as error:
        raise KernelRunError(f"timeout after {RUN_TIMEOUT_SECONDS}s: {command}") from error


def list_files(run_directory):
    return {path.relative_to(run_directory).as_posix() for path in run_directory.rglob("*") if path.is_file()}


def read_new_files(run_directory, baseline):
    """Return the content of every file created since baseline, keyed by relative path."""
    created = sorted(list_files(run_directory) - baseline)
    return {relative: (run_directory / relative).read_bytes() for relative in created}


def mask_volatile(output, patterns):
    """Blank out fields the benchmark prints from the wall clock, so only deterministic output is hashed."""
    masked = output
    for pattern in patterns:
        masked = re.sub(pattern.encode("utf-8"), MASKED_TEXT, masked)
    return masked


def digest_run(spec, completed, created_files):
    """Hash the exit status, masked stdout and stderr, and every file the kernel created."""
    hasher = hashlib.sha256()
    hasher.update(f"exit={completed.returncode}\n".encode("utf-8"))
    hasher.update(mask_volatile(completed.stdout, spec.volatile_patterns))
    hasher.update(b"\x00stderr\x00")
    hasher.update(mask_volatile(completed.stderr, spec.volatile_patterns))
    for relative, content in created_files.items():
        hasher.update(f"\x00file:{relative}\x00".encode("utf-8"))
        hasher.update(content)
    return hasher.hexdigest()


def execute_kernel(spec, launcher, scratch):
    """Stage inputs, run setup invocations, run the kernel, and return its output digest."""
    run_directory = stage_run_directory(spec, scratch)
    for setup in spec.setup_arguments:
        invoke(launcher, setup, run_directory, "")
    baseline = list_files(run_directory)
    completed = invoke(launcher, spec.arguments, run_directory, spec.stdin_file)
    return digest_run(spec, completed, read_new_files(run_directory, baseline))


def native_launcher(executable):
    return [str(executable)]


def lli_launcher(bitcode):
    return [tool_path("lli"), str(bitcode)]
