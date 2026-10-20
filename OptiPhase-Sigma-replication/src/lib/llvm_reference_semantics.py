"""Reference semantics of the supported integer fragment, stated over mathematical integers.

This module shares no code with the Z3 encoder. Each rule is written from the poison rules of the LLVM Language
Reference, so agreement between the two is evidence about the encoder. An operand is a pair (value, is_poison);
a result is the defined value, or POISON (None).
"""

import operator

POISON = None
ARITHMETIC_OPCODES = ("add", "sub", "mul")
SHIFT_OPCODES = ("shl", "lshr", "ashr")
RELATIONS = {
    "eq": (False, operator.eq),
    "ne": (False, operator.ne),
    "ugt": (False, operator.gt),
    "uge": (False, operator.ge),
    "ult": (False, operator.lt),
    "ule": (False, operator.le),
    "sgt": (True, operator.gt),
    "sge": (True, operator.ge),
    "slt": (True, operator.lt),
    "sle": (True, operator.le),
}


def to_signed(value, width):
    return value - (1 << width) if value >> (width - 1) else value


def in_signed_range(number, width):
    return -(1 << (width - 1)) <= number < (1 << (width - 1))


def _arithmetic(opcode, flags, a, b, width):
    mask = (1 << width) - 1
    exact = {"add": a + b, "sub": a - b, "mul": a * b}[opcode]
    signed_a, signed_b = to_signed(a, width), to_signed(b, width)
    signed_exact = {"add": signed_a + signed_b, "sub": signed_a - signed_b, "mul": signed_a * signed_b}[opcode]
    if "nuw" in flags and not 0 <= exact <= mask:
        return POISON
    if "nsw" in flags and not in_signed_range(signed_exact, width):
        return POISON
    return exact & mask


def _shift(opcode, flags, a, b, width):
    mask = (1 << width) - 1
    if opcode == "shl":
        if "nuw" in flags and (a << b) > mask:
            return POISON
        if "nsw" in flags and not in_signed_range(to_signed(a, width) << b, width):
            return POISON
        return (a << b) & mask
    if "exact" in flags and a % (1 << b) != 0:
        return POISON
    if opcode == "lshr":
        return a >> b
    return (to_signed(a, width) >> b) & mask


def _bitwise(opcode, flags, a, b):
    if opcode == "and":
        return a & b
    if opcode == "xor":
        return a ^ b
    if "disjoint" in flags and a & b:
        return POISON
    return a | b


def binary(opcode, flags, left, right, width):
    (a, a_poison), (b, b_poison) = left, right
    if a_poison or b_poison:
        return POISON
    if opcode in SHIFT_OPCODES and b >= width:
        return POISON
    if opcode in ARITHMETIC_OPCODES:
        return _arithmetic(opcode, flags, a, b, width)
    if opcode in SHIFT_OPCODES:
        return _shift(opcode, flags, a, b, width)
    return _bitwise(opcode, flags, a, b)


def compare(predicate, flags, left, right, width):
    (a, a_poison), (b, b_poison) = left, right
    if a_poison or b_poison:
        return POISON
    sign_bit = 1 << (width - 1)
    if "samesign" in flags and (a & sign_bit) != (b & sign_bit):
        return POISON
    is_signed, relation = RELATIONS[predicate]
    x, y = (to_signed(a, width), to_signed(b, width)) if is_signed else (a, b)
    return int(relation(x, y))


def select(condition, if_true, if_false):
    condition_value, condition_poison = condition
    if condition_poison:
        return POISON
    chosen_value, chosen_poison = if_true if condition_value == 1 else if_false
    return POISON if chosen_poison else chosen_value


def cast(opcode, flags, operand, source_width, width):
    value, is_poison = operand
    if is_poison:
        return POISON
    mask = (1 << width) - 1
    if opcode == "zext":
        if "nneg" in flags and to_signed(value, source_width) < 0:
            return POISON
        return value
    if opcode == "sext":
        return to_signed(value, source_width) & mask
    if "nuw" in flags and value > mask:
        return POISON
    if "nsw" in flags and not in_signed_range(to_signed(value, source_width), width):
        return POISON
    return value & mask
