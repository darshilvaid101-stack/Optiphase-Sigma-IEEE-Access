"""IR and trace metrics for sweep telemetry: instruction counts, opcode entropy, KL divergence, and pass events."""

import math
import re
from collections import Counter

INSTRUCTION_INDENT = "  "
TAIL_CALL_PREFIXES = ("tail", "musttail", "notail")
PASS_EVENT_PATTERN = re.compile(r"^Running pass: ", re.MULTILINE)
NO_CHANGE_PATTERN = re.compile(r"omitted because no change")
SCEV_RUN_PATTERN = re.compile(r"^Running analysis: ScalarEvolutionAnalysis on (\S+)", re.MULTILINE)
DEFINE_PATTERN = re.compile(r"^define [^@]*@([^\s(]+)\(", re.MULTILINE)
VECTORIZED_LOOP_PATTERN = re.compile(r'"llvm\.loop\.isvectorized"')
TOTAL_TIME_PATTERN = re.compile(r"Total Execution Time: ([0-9.]+) seconds")
PSEUDO_COUNT = 1.0


def defined_functions(listing):
    """Names of functions defined (not merely declared) in an IR listing, in sorted order."""
    return sorted(set(DEFINE_PATTERN.findall(listing)))


def instruction_lines(listing):
    """Yield the body lines of instructions: indented, non-comment lines inside function bodies."""
    for line in listing.splitlines():
        stripped = line.strip()
        if line.startswith(INSTRUCTION_INDENT) and stripped and not stripped.startswith(";"):
            yield stripped


def opcode_of(instruction):
    """Return the opcode of one instruction line, skipping an optional `%x =` and tail-call markers."""
    body = instruction.split(" = ", 1)[1] if instruction.startswith("%") and " = " in instruction else instruction
    words = body.split()
    while words and words[0] in TAIL_CALL_PREFIXES:
        words = words[1:]
    return words[0] if words else "unknown"


def opcode_histogram(listing):
    return Counter(opcode_of(line) for line in instruction_lines(listing))


def instruction_count(listing):
    return sum(opcode_histogram(listing).values())


def shannon_entropy_bits(histogram):
    """Shannon entropy in bits of the empirical distribution of opcodes."""
    total = sum(histogram.values())
    if total == 0:
        return 0.0
    return -sum((count / total) * math.log2(count / total) for count in histogram.values() if count)


def kl_divergence_bits(after, canonical):
    """D_KL(after || canonical) in bits over the union of opcodes, with a fixed additive pseudo-count."""
    keys = set(after) | set(canonical)
    after_total = sum(after.values()) + PSEUDO_COUNT * len(keys)
    canonical_total = sum(canonical.values()) + PSEUDO_COUNT * len(keys)
    divergence = 0.0
    for key in keys:
        p = (after.get(key, 0) + PSEUDO_COUNT) / after_total
        q = (canonical.get(key, 0) + PSEUDO_COUNT) / canonical_total
        divergence += p * math.log2(p / q)
    return divergence


def vectorized_loop_count(listing_text):
    """Loops that the loop vectorizer marked, counted from the llvm.loop.isvectorized metadata of the optimized IR.

    The count comes from the module itself, so it does not depend on the optimizer's remark stream, which can change the
    optimization it reports on.
    """
    return len(VECTORIZED_LOOP_PATTERN.findall(listing_text))


def parse_trace(stderr_text):
    """Summarize one opt run's diagnostic trace (-debug-pass-manager, -print-changed, -time-passes)."""
    scev_functions = set(SCEV_RUN_PATTERN.findall(stderr_text))
    scev_runs = len(SCEV_RUN_PATTERN.findall(stderr_text))
    total_time = TOTAL_TIME_PATTERN.search(stderr_text)
    return {
        "pass_events": len(PASS_EVENT_PATTERN.findall(stderr_text)),
        "noop_events": len(NO_CHANGE_PATTERN.findall(stderr_text)),
        "scev_runs": scev_runs,
        "scev_functions": len(scev_functions),
        "pass_time_seconds": float(total_time.group(1)) if total_time else 0.0,
    }


def scev_invalidations(trace):
    """SCEV recomputations beyond the first build per function: a conservative invalidation count."""
    return max(0, trace["scev_runs"] - trace["scev_functions"])
