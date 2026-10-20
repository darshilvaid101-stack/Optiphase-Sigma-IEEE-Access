"""Tree-aware prefixes of a nested NewPM pipeline, used for the stepwise -O3 ablation (regime R4)."""

import re

ITEM_PATTERN = re.compile(r"^([^(]*)(?:\((.*)\))?$", re.DOTALL)


def split_top_level(text):
    """Split on commas that are outside <...> parameter blocks and (...) nesting."""
    items, depth, current = [], 0, []
    for character in text:
        if character in "<(":
            depth += 1
        elif character in ">)":
            depth -= 1
        if character == "," and depth == 0:
            items.append("".join(current))
            current = []
        else:
            current.append(character)
    if current:
        items.append("".join(current))
    return items


def parse_item(item):
    """Return (name, children) where children is None for a leaf pass."""
    match = ITEM_PATTERN.match(item)
    name, children = match.group(1), match.group(2)
    return name, (split_top_level(children) if children is not None else None)


def count_leaves(items):
    total = 0
    for item in items:
        _, children = parse_item(item)
        total += 1 if children is None else count_leaves(children)
    return total


def take_prefix(items, budget):
    """Return (kept_items, leaves_used) keeping the first `budget` leaf passes in order."""
    kept, used = [], 0
    for item in items:
        if used >= budget:
            break
        name, children = parse_item(item)
        if children is None:
            kept.append(item)
            used += 1
            continue
        inner, inner_used = take_prefix(children, budget - used)
        kept.append(f"{name}({','.join(inner)})")
        used += inner_used
    return kept, used


def pipeline_prefix(pipeline, stages):
    """Return the pipeline text containing the first `stages` leaf passes of `pipeline`."""
    kept, _ = take_prefix(split_top_level(pipeline), stages)
    return ",".join(kept)
