"""Exhaustive agreement between the production Z3 encoder and the reference semantics, for small widths.

Each case feeds concrete operands (every defined value, plus one poisoned operand) to the encoder, simplifies the
resulting terms to constants, and compares them with llvm_reference_semantics. The encoder code run here is the code
that the refinement checks use; nothing is re-implemented in the harness.
"""

import itertools
from collections import defaultdict

import z3

from lib import llvm_reference_semantics as reference
from lib.block_parser import ALLOWED_FLAGS, BINARY_OPCODES, CAST_OPCODES, Instruction
from lib.z3_validator import COMPARISONS, Encoder

MISMATCH_EXAMPLE_LIMIT = 20


def operand_choices(width):
    """Every defined value of the width, plus one poisoned operand."""
    return [(value, False) for value in range(1 << width)] + [(0, True)]


def encoded_operand(choice, width):
    value, is_poison = choice
    return z3.BitVecVal(value, width), z3.BoolVal(is_poison)


def flag_subsets(allowed):
    return [
        tuple(subset)
        for size in range(len(allowed) + 1)
        for subset in itertools.combinations(allowed, size)
    ]


def family_name(opcode, flags):
    return " ".join((opcode, *flags))


def agrees(value, poison, expected):
    """Compare simplified encoder terms with the reference result (None means poison)."""
    simplified_poison = z3.simplify(poison)
    if expected is reference.POISON:
        return z3.is_true(simplified_poison)
    if not z3.is_false(simplified_poison):
        return False
    simplified_value = z3.simplify(value)
    return z3.is_bv_value(simplified_value) and simplified_value.as_long() == expected


def binary_cases(width):
    for opcode in sorted(BINARY_OPCODES):
        for flags in flag_subsets(ALLOWED_FLAGS[opcode]):
            instruction = Instruction("%r", opcode, flags, width, ("%a", "%b"))
            for left, right in itertools.product(operand_choices(width), repeat=2):
                value, poison = Encoder({}).binary(
                    instruction, [encoded_operand(left, width), encoded_operand(right, width)],
                )
                expected = reference.binary(opcode, flags, left, right, width)
                yield family_name(opcode, flags), agrees(value, poison, expected), (opcode, flags, left, right, width)


def compare_cases(width):
    for predicate in sorted(COMPARISONS):
        for flags in flag_subsets(ALLOWED_FLAGS["icmp"]):
            instruction = Instruction("%r", "icmp", flags, width, ("%a", "%b"), predicate=predicate)
            for left, right in itertools.product(operand_choices(width), repeat=2):
                value, poison = Encoder({}).compare(
                    instruction, [encoded_operand(left, width), encoded_operand(right, width)],
                )
                expected = reference.compare(predicate, flags, left, right, width)
                yield family_name("icmp", flags), agrees(value, poison, expected), (predicate, flags, left, right, width)


def select_cases(width):
    for condition, if_true, if_false in itertools.product(operand_choices(1), operand_choices(width), operand_choices(width)):
        value, poison = Encoder({}).select([
            encoded_operand(condition, 1), encoded_operand(if_true, width), encoded_operand(if_false, width),
        ])
        expected = reference.select(condition, if_true, if_false)
        yield "select", agrees(value, poison, expected), (condition, if_true, if_false, width)


def is_valid_cast(opcode, source_width, width):
    if opcode == "trunc":
        return width < source_width
    return width > source_width


def cast_cases(source_width, width):
    for opcode in sorted(CAST_OPCODES):
        if not is_valid_cast(opcode, source_width, width):
            continue
        for flags in flag_subsets(ALLOWED_FLAGS[opcode]):
            instruction = Instruction("%r", opcode, flags, width, ("%a",), source_width=source_width)
            for operand in operand_choices(source_width):
                value, poison = Encoder({}).cast(instruction, [encoded_operand(operand, source_width)])
                expected = reference.cast(opcode, flags, operand, source_width, width)
                yield family_name(opcode, flags), agrees(value, poison, expected), (opcode, flags, operand, source_width, width)


def all_cases(max_width):
    for width in range(1, max_width + 1):
        yield from binary_cases(width)
        yield from compare_cases(width)
        yield from select_cases(width)
    for source_width, width in itertools.product(range(1, max_width + 1), repeat=2):
        yield from cast_cases(source_width, width)


def run_agreement(max_width):
    """Return case and mismatch counts per instruction family, with the first mismatches for diagnosis."""
    families = defaultdict(lambda: {"cases": 0, "mismatches": 0})
    examples = []
    for family, agreed, detail in all_cases(max_width):
        families[family]["cases"] += 1
        if not agreed:
            families[family]["mismatches"] += 1
            if len(examples) < MISMATCH_EXAMPLE_LIMIT:
                examples.append({"family": family, "case": repr(detail)})
    total_cases = sum(counts["cases"] for counts in families.values())
    total_mismatches = sum(counts["mismatches"] for counts in families.values())
    return {
        "max_width": max_width,
        "total_cases": total_cases,
        "total_mismatches": total_mismatches,
        "families": dict(sorted(families.items())),
        "first_mismatches": examples,
    }
