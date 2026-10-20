"""LLVM poison conditions for instruction flags, written as Z3 Boolean terms.

Each function returns the condition under which a flagged instruction is poison when its operands are defined,
following the poison rules of the LLVM Language Reference. llvm_reference_semantics states the same rules over
mathematical integers, and the agreement check compares the two on every small case.
"""

import z3

ARITHMETIC_OPCODES = ("add", "sub", "mul")
SHIFT_OPCODES = ("shl", "lshr", "ashr")


def overflow(opcode, a, b, width, is_signed):
    """True when the exact result of add, sub, or mul does not fit in `width` bits.

    The exact result is computed in a wider format. Add and sub need one extra bit. Mul needs `width` extra bits,
    because the product of two width-bit values can occupy 2 * width bits; one extra bit wraps and misses overflow.
    """
    extension = width if opcode == "mul" else 1
    widen = z3.SignExt if is_signed else z3.ZeroExt
    exact = {
        "add": widen(extension, a) + widen(extension, b),
        "sub": widen(extension, a) - widen(extension, b),
        "mul": widen(extension, a) * widen(extension, b),
    }[opcode]
    wrapped = {"add": a + b, "sub": a - b, "mul": a * b}[opcode]
    return exact != widen(extension, wrapped)


def any_of(conditions):
    return z3.Or(conditions) if conditions else z3.BoolVal(False)


def binary_flag_poison(opcode, flags, a, b, width):
    """Poison condition of the flags on a binary instruction whose operands a and b are defined."""
    conditions = []
    if opcode in ARITHMETIC_OPCODES:
        if "nsw" in flags:
            conditions.append(overflow(opcode, a, b, width, is_signed=True))
        if "nuw" in flags:
            conditions.append(overflow(opcode, a, b, width, is_signed=False))
    elif opcode == "shl":
        shifted = a << b
        if "nuw" in flags:
            conditions.append(z3.LShR(shifted, b) != a)
        if "nsw" in flags:
            conditions.append((shifted >> b) != a)
    elif opcode == "lshr" and "exact" in flags:
        conditions.append((z3.LShR(a, b) << b) != a)
    elif opcode == "ashr" and "exact" in flags:
        conditions.append(((a >> b) << b) != a)
    elif opcode == "or" and "disjoint" in flags:
        conditions.append((a & b) != 0)
    return any_of(conditions)


def cast_flag_poison(opcode, flags, value, source_width, width):
    """Poison condition of the flags on a cast of the defined operand `value`."""
    conditions = []
    if opcode == "zext" and "nneg" in flags:
        conditions.append(z3.Extract(source_width - 1, source_width - 1, value) == 1)
    if opcode == "trunc":
        truncated = z3.Extract(width - 1, 0, value)
        if "nuw" in flags:
            conditions.append(z3.ZeroExt(source_width - width, truncated) != value)
        if "nsw" in flags:
            conditions.append(z3.SignExt(source_width - width, truncated) != value)
    return any_of(conditions)


def compare_flag_poison(flags, a, b, width):
    """`samesign` makes a comparison poison when the two operands have different sign bits."""
    if "samesign" not in flags:
        return z3.BoolVal(False)
    sign_bit = width - 1
    return z3.Extract(sign_bit, sign_bit, a) != z3.Extract(sign_bit, sign_bit, b)
