"""Deterministic sentence splitting for abstracts, protecting common scientific abbreviations."""

import re

ABBREVIATIONS = (
    "e.g.",
    "i.e.",
    "et al.",
    "vs.",
    "cf.",
    "Fig.",
    "Figs.",
    "Sec.",
    "Eq.",
    "approx.",
    "resp.",
)
PROTECTED_DOT = "\u0001"
SENTENCE_BOUNDARY_PATTERN = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9(\[\"'])")


def protect_abbreviations(text):
    protected = text
    for abbreviation in ABBREVIATIONS:
        protected = protected.replace(abbreviation, abbreviation.replace(".", PROTECTED_DOT))
    return protected


def split_sentences(text):
    """Split running text into sentences; whitespace inside each sentence is collapsed."""
    pieces = SENTENCE_BOUNDARY_PATTERN.split(protect_abbreviations(text))
    restored = (piece.replace(PROTECTED_DOT, ".") for piece in pieces)
    return [" ".join(piece.split()) for piece in restored if piece.strip()]
