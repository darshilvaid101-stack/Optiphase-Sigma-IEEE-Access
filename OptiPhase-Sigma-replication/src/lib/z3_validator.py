"""Bounded two-rail (value, poison) refinement checks for integer-only LLVM basic blocks, using Z3.

Each SSA value is encoded as a bit-vector and a poison Boolean. A block is encodable only when every instruction is in
the supported integer fragment (block_parser.ALLOWED_FLAGS lists the flags it models). Anything else makes the block
not encodable, and it is reported as such. The check is block-local: live-ins must have the same names in source and
target, and only names defined in both blocks are compared. The refinement query for a name x is
not poison(source x) and (poison(target x) or value(source x) != value(target x)); UNSAT means no defined input
violates it. Live-in values are non-poison in every query.
"""

import z3

from lib.block_parser import (
    BINARY_OPCODES,
    CAST_OPCODES,
    NotEncodable,
    blocks_of_function,
    live_in_names,
)
from lib.z3_poison_rules import binary_flag_poison, cast_flag_poison, compare_flag_poison

__all__ = [
    "NotEncodable",
    "STATUS_REFINES",
    "STATUS_UNKNOWN",
    "STATUS_VIOLATED",
    "blocks_of_function",
    "check_refinement",
    "encode_block",
    "live_in_names",
]

STATUS_REFINES = "UNSAT"
STATUS_VIOLATED = "SAT"
STATUS_UNKNOWN = "UNKNOWN"
SHIFT_OPCODES = ("shl", "lshr", "ashr")
COMPARISONS = {
    "eq": lambda a, b: a == b,
    "ne": lambda a, b: a != b,
    "ugt": lambda a, b: z3.UGT(a, b),
    "uge": lambda a, b: z3.UGE(a, b),
    "ult": lambda a, b: z3.ULT(a, b),
    "ule": lambda a, b: z3.ULE(a, b),
    "sgt": lambda a, b: a > b,
    "sge": lambda a, b: a >= b,
    "slt": lambda a, b: a < b,
    "sle": lambda a, b: a <= b,
}


def binary_value(opcode, a, b):
    if opcode == "add":
        return a + b
    if opcode == "sub":
        return a - b
    if opcode == "mul":
        return a * b
    if opcode == "and":
        return a & b
    if opcode == "or":
        return a | b
    if opcode == "xor":
        return a ^ b
    if opcode == "shl":
        return a << b
    if opcode == "lshr":
        return z3.LShR(a, b)
    return a >> b


def operand_widths(instruction):
    """Bit-widths of each operand: select conditions are i1, casts read their source type."""
    if instruction.opcode == "select":
        return [1, instruction.width, instruction.width]
    if instruction.opcode in CAST_OPCODES:
        return [instruction.source_width]
    return [instruction.width] * len(instruction.operands)


class Encoder:
    """Two-rail encoding: each SSA value becomes (bit-vector, poison Boolean)."""

    def __init__(self, inputs):
        self.inputs = inputs
        self.values = {}

    def operand(self, token, width):
        if token == "true":
            return z3.BitVecVal(1, 1), z3.BoolVal(False)
        if token == "false":
            return z3.BitVecVal(0, 1), z3.BoolVal(False)
        if token.lstrip("-").isdigit():
            return z3.BitVecVal(int(token) % (1 << width), width), z3.BoolVal(False)
        if token not in self.values:
            if token not in self.inputs:
                self.inputs[token] = z3.BitVec(f"in{token[1:]}_{width}", width)
            self.values[token] = (self.inputs[token], z3.BoolVal(False))
        return self.values[token]

    def encode(self, instruction):
        operands = [
            self.operand(token, width)
            for token, width in zip(instruction.operands, operand_widths(instruction))
        ]
        if instruction.opcode in BINARY_OPCODES:
            return self.binary(instruction, operands)
        if instruction.opcode == "icmp":
            return self.compare(instruction, operands)
        if instruction.opcode == "select":
            return self.select(operands)
        if instruction.opcode in CAST_OPCODES:
            return self.cast(instruction, operands)
        raise NotEncodable(instruction.opcode)

    def binary(self, instruction, operands):
        (a, a_poison), (b, b_poison) = operands
        opcode, width = instruction.opcode, instruction.width
        poison = z3.Or(a_poison, b_poison, binary_flag_poison(opcode, instruction.flags, a, b, width))
        if opcode in SHIFT_OPCODES:
            poison = z3.Or(poison, z3.UGE(b, z3.BitVecVal(width, width)))
        return binary_value(opcode, a, b), poison

    def compare(self, instruction, operands):
        (a, a_poison), (b, b_poison) = operands
        if instruction.predicate not in COMPARISONS:
            raise NotEncodable(f"predicate {instruction.predicate}")
        outcome = COMPARISONS[instruction.predicate](a, b)
        poison = z3.Or(a_poison, b_poison, compare_flag_poison(instruction.flags, a, b, instruction.width))
        return z3.If(outcome, z3.BitVecVal(1, 1), z3.BitVecVal(0, 1)), poison

    def select(self, operands):
        (condition, condition_poison), (true_value, true_poison), (false_value, false_poison) = operands
        is_true = condition == z3.BitVecVal(1, 1)
        chosen = z3.If(is_true, true_value, false_value)
        chosen_poison = z3.If(is_true, true_poison, false_poison)
        return chosen, z3.Or(condition_poison, chosen_poison)

    def cast(self, instruction, operands):
        (value, poison), = operands
        source_width, width = instruction.source_width, instruction.width
        if instruction.opcode == "zext":
            result = z3.ZeroExt(width - source_width, value)
        elif instruction.opcode == "sext":
            result = z3.SignExt(width - source_width, value)
        else:
            result = z3.Extract(width - 1, 0, value)
        flag_poison = cast_flag_poison(instruction.opcode, instruction.flags, value, source_width, width)
        return result, z3.Or(poison, flag_poison)


def encode_block(block):
    """Encode a block's defined values in order; returns ({name: (value, poison)}, input symbols)."""
    if block.unsupported:
        raise NotEncodable(block.unsupported)
    inputs = {}
    encoder = Encoder(inputs)
    defined = []
    for instruction in block.instructions:
        if instruction.result is None:
            continue
        encoder.values[instruction.result] = encoder.encode(instruction)
        defined.append(instruction.result)
    return {name: encoder.values[name] for name in defined}, inputs


def name_queries(source, target):
    """Return ([(name, violation)], input symbols) for the names defined in both blocks.

    The violation of a name is the refinement query: the source defines it without poison, and the target does not
    define it equally. A query is unsatisfiable when the name refines.
    """
    if live_in_names(source) != live_in_names(target):
        raise NotEncodable("live-in sets differ")
    source_values, source_inputs = encode_block(source)
    target_values, target_inputs = encode_block(target)
    queries = []
    for name in sorted(set(source_values) & set(target_values)):
        source_value, source_poison = source_values[name]
        target_value, target_poison = target_values[name]
        if source_value.size() != target_value.size():
            raise NotEncodable(f"width mismatch for {name}")
        violation = z3.And(z3.Not(source_poison), z3.Or(target_poison, source_value != target_value))
        queries.append((name, violation))
    return queries, {**source_inputs, **target_inputs}


def check_refinement(source, target, timeout_ms):
    """Return (per-name status, input count) for the names defined in both blocks."""
    queries, shared_inputs = name_queries(source, target)
    statuses = {}
    for name, violation in queries:
        solver = z3.Solver()
        solver.set("timeout", timeout_ms)
        solver.add(violation)
        result = solver.check()
        if result == z3.unsat:
            statuses[name] = STATUS_REFINES
        elif result == z3.sat:
            statuses[name] = STATUS_VIOLATED
        else:
            statuses[name] = STATUS_UNKNOWN
    return statuses, len(shared_inputs)
