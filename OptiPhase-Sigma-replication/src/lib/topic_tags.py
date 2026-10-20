"""Compiler-topic tagging that flags the subset of harvested papers relevant to the paper's topic."""

import re

COMPILER_TOPIC_PATTERNS = (
    r"\bcompilers?\b",
    r"\bllvm\b",
    r"\bphase[- ]ordering\b",
    r"\bpass (?:ordering|manager|pipeline|interactions?)\b",
    r"\boptimi[sz]ation passes?\b",
    r"\bpolyhedral\b",
    r"\btranslation validation\b",
    r"\bvectori[sz]ation\b",
    r"\bsmt\b",
    r"\bz3\b",
    r"\bintermediate representation\b",
    r"\bcode generation\b",
    r"\bregister allocation\b",
    r"\binstruction scheduling\b",
    r"\bloop (?:optimi[sz]ation|transformation)s?\b",
)
COMPILED_TOPIC_PATTERNS = tuple(re.compile(pattern, re.IGNORECASE) for pattern in COMPILER_TOPIC_PATTERNS)


def is_compiler_topic(title, abstract):
    text = f"{title or ''} {abstract or ''}"
    return any(pattern.search(text) for pattern in COMPILED_TOPIC_PATTERNS)
