"""Title normalisation and similarity for Crossref verification, deduplication, and arXiv matching."""

import difflib
import re
import unicodedata

NON_ALPHANUMERIC_PATTERN = re.compile(r"[^a-z0-9]+")


def normalize_title(title):
    """Lowercase and strip accents and punctuation so that equal papers compare equal."""
    if not title:
        return ""
    decomposed = unicodedata.normalize("NFKD", title)
    ascii_only = decomposed.encode("ascii", "ignore").decode("ascii")
    return NON_ALPHANUMERIC_PATTERN.sub(" ", ascii_only.lower()).strip()


def title_similarity(left, right):
    """Return a similarity in [0, 1]; two empty titles are not treated as identical."""
    normalized_left, normalized_right = normalize_title(left), normalize_title(right)
    if not normalized_left or not normalized_right:
        return 0.0
    matcher = difflib.SequenceMatcher(None, normalized_left, normalized_right, autojunk=False)
    return matcher.ratio()
