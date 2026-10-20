"""Typed wrappers around the LLVM, clang, and Z3 command-line tools named in config/global_config.yaml."""

import functools
import hashlib
import subprocess
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
GLOBAL_CONFIG_PATH = REPO_ROOT / "config" / "global_config.yaml"
DEFAULT_TIMEOUT_SECONDS = 600
STDERR_TAIL_CHARACTERS = 1500
HASH_CHUNK_BYTES = 1 << 20


class ToolError(RuntimeError):
    """An external tool exited non-zero or timed out; carries the command and stderr tail."""

    def __init__(self, command, returncode, stderr_tail):
        super().__init__(f"{' '.join(command)} exited {returncode}: {stderr_tail}")
        self.command = command
        self.returncode = returncode
        self.stderr_tail = stderr_tail

    def __reduce__(self):
        # Worker processes re-raise this in the parent; rebuild from the real fields, not .args.
        return (ToolError, (self.command, self.returncode, self.stderr_tail))


@functools.cache
def load_tool_paths():
    config = yaml.safe_load(GLOBAL_CONFIG_PATH.read_text(encoding="utf-8"))
    return config["paths"]


def tool_path(name):
    paths = load_tool_paths()
    if name not in paths:
        raise KeyError(f"no tool named {name!r} in {GLOBAL_CONFIG_PATH}")
    return paths[name]


def run_tool(name, arguments, cwd=None, timeout_seconds=DEFAULT_TIMEOUT_SECONDS):
    """Run a configured tool with an argument list (never a shell); raise ToolError on failure."""
    command = [tool_path(name), *[str(argument) for argument in arguments]]
    try:
        completed = subprocess.run(
            command,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired as error:
        raise ToolError(command, "timeout", str(error)[-STDERR_TAIL_CHARACTERS:]) from error
    if completed.returncode != 0:
        tail = completed.stderr[-STDERR_TAIL_CHARACTERS:]
        raise ToolError(command, completed.returncode, tail)
    return completed


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(HASH_CHUNK_BYTES), b""):
            digest.update(chunk)
    return digest.hexdigest()
