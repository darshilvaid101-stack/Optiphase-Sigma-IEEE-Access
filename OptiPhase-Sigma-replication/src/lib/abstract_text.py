"""Plain-text abstract helpers for OpenAlex inverted indexes and Crossref JATS markup."""

import html
import re

MARKUP_TAG_PATTERN = re.compile(r"<[^>]+>")
WHITESPACE_PATTERN = re.compile(r"\s+")
LEADING_HEADING_PATTERN = re.compile(r"^\s*Abstract\s*[:.]?\s+", re.IGNORECASE)


def reconstruct_abstract(inverted_index):
    """Rebuild running text from OpenAlex's word-to-positions index."""
    if not inverted_index:
        return None
    positioned_words = sorted(
        (position, word) for word, positions in inverted_index.items() for position in positions
    )
    return " ".join(word for _, word in positioned_words)


def strip_markup(text):
    """Remove JATS or HTML tags, unescape entities, and collapse whitespace."""
    if not text:
        return None
    unescaped = html.unescape(MARKUP_TAG_PATTERN.sub(" ", text))
    collapsed = WHITESPACE_PATTERN.sub(" ", unescaped).strip()
    without_heading = LEADING_HEADING_PATTERN.sub("", collapsed)
    return without_heading or None
