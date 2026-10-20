"""Render verified records as BibTeX entries with deterministic, collision-free keys."""

import re
import string
import unicodedata

from lib.title_similarity import normalize_title

ENTRY_TYPE_BY_CROSSREF_TYPE = {
    "journal-article": "article",
    "proceedings-article": "inproceedings",
    "book-chapter": "inproceedings",
}
CONTAINER_FIELD_BY_ENTRY_TYPE = {"article": "journal", "inproceedings": "booktitle"}
LATEX_ESCAPES = (("&", r"\&"), ("%", r"\%"), ("#", r"\#"), ("_", r"\_"))
PAGE_RANGE_PATTERN = re.compile(r"^(\S+?)\s*[-–—]+\s*(\S+)$")
NON_ALPHANUMERIC_PATTERN = re.compile(r"[^A-Za-z0-9]")
ALPHABET_SIZE = len(string.ascii_lowercase)


def escape_text(value):
    escaped = value
    for character, replacement in LATEX_ESCAPES:
        escaped = escaped.replace(character, replacement)
    return escaped


def ascii_token(value):
    folded = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    return NON_ALPHANUMERIC_PATTERN.sub("", folded)


def lead_surname(authors):
    lead = authors[0]
    return ascii_token(lead.get("family") or lead.get("name") or "anon").lower()


def first_title_word(title):
    words = normalize_title(title).split()
    return words[0] if words else "paper"


def letter_suffix(index):
    """Map 1, 2, ..., 26, 27 to a, b, ..., z, aa so colliding keys stay readable."""
    letters = ""
    remaining = index
    while remaining > 0:
        remaining, offset = divmod(remaining - 1, ALPHABET_SIZE)
        letters = string.ascii_lowercase[offset] + letters
    return letters


def make_key(record, taken_keys):
    base = f"{lead_surname(record['authors'])}{record['year']}{first_title_word(record['title'])}"
    key, index = base, 0
    while key in taken_keys:
        index += 1
        key = f"{base}{letter_suffix(index)}"
    taken_keys.add(key)
    return key


def assign_keys(records):
    """Return copies of the records with a bibtex_key, ordered by year then DOI."""
    taken_keys = set()
    ordered = sorted(records, key=lambda record: (record["year"], record["doi"]))
    return [{**record, "bibtex_key": make_key(record, taken_keys)} for record in ordered]


def format_author(author):
    family, given = author.get("family"), author.get("given")
    if family and given:
        return f"{escape_text(family)}, {escape_text(given)}"
    if family:
        return "{" + escape_text(family) + "}"
    return "{" + escape_text(author.get("name") or "") + "}"


def format_authors(authors):
    return " and ".join(format_author(author) for author in authors)


def format_pages(pages):
    if not pages:
        return None
    match = PAGE_RANGE_PATTERN.match(pages.strip())
    if match:
        return f"{match.group(1)}--{match.group(2)}"
    return pages.strip()


def build_fields(record):
    publisher = escape_text(record["publisher"]) if record["publisher"] else None
    return [
        ("author", format_authors(record["authors"])),
        ("title", "{" + escape_text(record["title"]) + "}"),
        (CONTAINER_FIELD_BY_ENTRY_TYPE[entry_type(record)], escape_text(record["container_title"] or "")),
        ("year", str(record["year"])),
        ("volume", record["volume"]),
        ("number", record["issue"]),
        ("pages", format_pages(record["pages"])),
        ("articleno", record["article_number"]),
        ("publisher", publisher),
        ("doi", record["doi"]),
        ("url", f"https://doi.org/{record['doi']}"),
    ]


def entry_type(record):
    return ENTRY_TYPE_BY_CROSSREF_TYPE[record["crossref_type"]]


def render_entry(record):
    """Render one record as a BibTeX entry; DOI and URL fields are left unescaped on purpose."""
    body = ",\n".join(
        f"  {name} = {{{value}}}" for name, value in build_fields(record) if value
    )
    return f"@{entry_type(record)}{{{record['bibtex_key']},\n{body}\n}}\n"
