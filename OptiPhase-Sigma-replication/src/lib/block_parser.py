"""Parse the integer-only basic blocks of an LLVM textual listing into instructions.

Anything outside the supported fragment marks its block as unsupported, so the checker reports the block as
not encodable. Nothing is skipped silently, and a flag the encoder does not model makes its block unsupported.
"""

import re
from dataclasses import dataclass, field

INSTRUCTION_PATTERN = re.compile(r"^\s+(?:(%[\w.$-]+) = )?(\w+)(?:\s+(.*?))?\s*$")
LABEL_PATTERN = re.compile(r"^([\w.$-]+):")
DEFINE_PATTERN = re.compile(r"^define .*?@([^\s(]+)\(")
INTEGER_TYPE_PATTERN = re.compile(r"^i(\d+)$")
OPERAND_PATTERN = re.compile(r"^(%[\w.$-]+|-?\d+|true|false)$")
FLAG_WORDS = frozenset({"nsw", "nuw", "exact", "disjoint", "samesign", "nneg"})
ALLOWED_FLAGS = {
    "add": ("nsw", "nuw"),
    "sub": ("nsw", "nuw"),
    "mul": ("nsw", "nuw"),
    "shl": ("nsw", "nuw"),
    "lshr": ("exact",),
    "ashr": ("exact",),
    "and": (),
    "or": ("disjoint",),
    "xor": (),
    "icmp": ("samesign",),
    "zext": ("nneg",),
    "sext": (),
    "trunc": ("nsw", "nuw"),
    "select": (),
}
BINARY_OPCODES = frozenset({"add", "sub", "mul", "and", "or", "xor", "shl", "lshr", "ashr"})
CAST_OPCODES = frozenset({"zext", "sext", "trunc"})
MAX_WIDTH = 64


class NotEncodable(Exception):
    """An instruction or operand lies outside the supported integer fragment."""


@dataclass
class Instruction:
    result: str | None
    opcode: str
    flags: tuple
    width: int
    operands: tuple
    predicate: str | None = None
    source_width: int | None = None


@dataclass
class Block:
    label: str
    instructions: list = field(default_factory=list)
    unsupported: str | None = None


def parse_width(type_text):
    match = INTEGER_TYPE_PATTERN.match(type_text.strip())
    if not match:
        raise NotEncodable(f"type {type_text}")
    width = int(match.group(1))
    if not 1 <= width <= MAX_WIDTH:
        raise NotEncodable(f"width {width}")
    return width


def parse_operand(token):
    token = token.strip()
    if not OPERAND_PATTERN.match(token):
        raise NotEncodable(f"operand {token}")
    return token


def split_flags(words, opcode):
    """Separate the flags from the remaining words; a flag the encoder does not model is not encodable."""
    flags = tuple(word for word in words if word in FLAG_WORDS)
    if not set(flags) <= set(ALLOWED_FLAGS[opcode]):
        raise NotEncodable(f"flags {' '.join(flags)} on {opcode}")
    return flags, [word for word in words if word not in FLAG_WORDS]


def parse_binary(result, opcode, rest):
    flags, words = split_flags(rest.split(), opcode)
    type_text, operand_text = " ".join(words).split(" ", 1)
    operands = tuple(parse_operand(part) for part in operand_text.split(","))
    return Instruction(result, opcode, flags, parse_width(type_text), operands)


def parse_icmp(result, rest):
    flags, words = split_flags(rest.split(), "icmp")
    predicate, type_text, operand_text = " ".join(words).split(" ", 2)
    operands = tuple(parse_operand(part) for part in operand_text.split(","))
    return Instruction(result, "icmp", flags, parse_width(type_text), operands, predicate=predicate)


def parse_select(result, rest):
    condition_part, true_part, false_part = [part.strip() for part in rest.split(",", 2)]
    cond_type, cond = condition_part.split(" ", 1)
    true_type, true_value = true_part.split(" ", 1)
    false_type, false_value = false_part.split(" ", 1)
    if parse_width(cond_type) != 1:
        raise NotEncodable("select condition is not i1")
    width = parse_width(true_type)
    if parse_width(false_type) != width:
        raise NotEncodable("select arms differ in width")
    operands = tuple(parse_operand(value) for value in (cond, true_value, false_value))
    return Instruction(result, "select", (), width, operands)


def parse_cast(result, opcode, rest):
    source_text, to_text = rest.rsplit(" to ", 1)
    flags, words = split_flags(source_text.split(), opcode)
    source_type, source_value = " ".join(words).split(" ", 1)
    return Instruction(
        result, opcode, flags, parse_width(to_text), (parse_operand(source_value),),
        source_width=parse_width(source_type),
    )


def parse_ret(rest):
    if rest.strip() == "void":
        raise NotEncodable("ret void")
    type_text, value = rest.split(" ", 1)
    return Instruction(None, "ret", (), parse_width(type_text), (parse_operand(value),))


def parse_instruction(match):
    result, opcode, rest = match.group(1), match.group(2), match.group(3) or ""
    if opcode in BINARY_OPCODES:
        return parse_binary(result, opcode, rest)
    if opcode == "icmp":
        return parse_icmp(result, rest)
    if opcode == "select":
        return parse_select(result, rest)
    if opcode in CAST_OPCODES:
        return parse_cast(result, opcode, rest)
    if opcode == "ret":
        return parse_ret(rest)
    raise NotEncodable(f"opcode {opcode}")


def blocks_of_function(listing, function_name):
    """Parse the blocks of one function from an LLVM textual listing; unsupported blocks are marked."""
    blocks, current, inside = [], None, False
    for line in listing.splitlines():
        define = DEFINE_PATTERN.match(line)
        if define:
            inside = define.group(1) == function_name
            current = None
            continue
        if not inside:
            continue
        if line.startswith("}"):
            break
        label = LABEL_PATTERN.match(line)
        if label:
            current = Block(label.group(1))
            blocks.append(current)
            continue
        if not line.startswith("  ") or not line.strip() or line.strip().startswith(";"):
            continue
        if line.split()[0] == "br":
            continue
        if current is None:
            current = Block("entry")
            blocks.append(current)
        match = INSTRUCTION_PATTERN.match(line)
        if match is None:
            current.unsupported = current.unsupported or f"unparsed line: {line.strip()[:60]}"
            continue
        try:
            current.instructions.append(parse_instruction(match))
        except (NotEncodable, ValueError) as error:
            current.unsupported = current.unsupported or str(error)
    return blocks


def live_in_names(block):
    defined = {inst.result for inst in block.instructions if inst.result}
    used = {op for inst in block.instructions for op in inst.operands if op.startswith("%")}
    return frozenset(used - defined)
