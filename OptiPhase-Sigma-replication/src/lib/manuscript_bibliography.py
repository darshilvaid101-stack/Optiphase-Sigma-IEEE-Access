"""Bibliography rules for the manuscript: the curated 2024-2026 set and the foundational tool and benchmark set."""

import re
from pathlib import Path

from lib.kernel_registry import REPO_ROOT

CURATED_BIBLIOGRAPHY = REPO_ROOT / "manuscript" / "references_curated.bib"
CURATED_COUNT = 30
CURATED_FIRST_YEAR = 2024
RECENT_SHARE_MINIMUM = 0.8
FOUNDATIONAL_KEYS = frozenset({
    "lattner2004llvm",
    "demoura2008z3",
    "lopes2021alive2",
    "lee2017undefined",
    "guthaus2001mibench",
    "maleki2011evaluation",
    "callahan1988vectorizing",
    "pouchet2016polybench",
    "eembccoremark",
})
CITE_PATTERN = re.compile(r"\\cite[a-zA-Z]*\*?(?:\[[^\]]*\])*\{([^}]*)\}")
ENTRY_PATTERN = re.compile(r"^@\w+\{([^,\s]+),", re.MULTILINE)
YEAR_PATTERN = re.compile(r"^\s*year\s*=\s*\{?(\d{4})", re.MULTILINE)
DOI_PATTERN = re.compile(r"^\s*doi\s*=\s*\{([^}]*)\}", re.MULTILINE)
URL_PATTERN = re.compile(r"^\s*url\s*=", re.MULTILINE)


def read_text(path):
    return path.read_text(encoding="utf-8") if path.exists() else ""


def cited_keys(source):
    keys = set()
    for group in CITE_PATTERN.findall(source):
        keys.update(key.strip() for key in group.split(",") if key.strip())
    return keys


def entry_bodies(text):
    """Map each BibTeX key to the text of its entry, which runs to the next entry."""
    heads = list(ENTRY_PATTERN.finditer(text))
    bodies = {}
    for position, head in enumerate(heads):
        end = heads[position + 1].start() if position + 1 < len(heads) else len(text)
        bodies[head.group(1)] = text[head.start():end]
    return bodies


def bibliography_entries(path=CURATED_BIBLIOGRAPHY):
    """Per-key facts that the checks use: year, DOI, whether a url field is present, and the foundational flag."""
    entries = {}
    for key, body in entry_bodies(read_text(path)).items():
        year = YEAR_PATTERN.search(body)
        doi = DOI_PATTERN.search(body)
        entries[key] = {
            "year": int(year.group(1)) if year else None,
            "doi": doi.group(1) if doi else None,
            "has_url": URL_PATTERN.search(body) is not None,
            "foundational": key in FOUNDATIONAL_KEYS,
        }
    return entries


def bibliography_report(entries):
    dois = [fact["doi"] for fact in entries.values() if fact["doi"]]
    curated = [key for key, fact in entries.items() if not fact["foundational"]]
    recent = [key for key in curated if entries[key]["year"] and entries[key]["year"] >= CURATED_FIRST_YEAR]
    return {
        "curated_count": len(curated),
        "foundational_count": len(entries) - len(curated),
        "curated_recent_count": len(recent),
        "duplicate_dois": sorted({doi for doi in dois if dois.count(doi) > 1}),
        "entries_with_url_field": sorted(key for key, fact in entries.items() if fact["has_url"]),
        "entries_without_year": sorted(key for key, fact in entries.items() if fact["year"] is None),
    }


def citation_report(sources, entries):
    cited = set()
    for path in sources:
        cited |= cited_keys(read_text(path))
    curated = {key for key, fact in entries.items() if not fact["foundational"]}
    cited_curated = cited & curated
    cited_recent = {key for key in cited_curated if entries[key]["year"] and entries[key]["year"] >= CURATED_FIRST_YEAR}
    return {
        "missing_bibliography_keys": sorted(cited - set(entries)),
        "uncited_curated_keys": sorted(curated - cited),
        "cited_curated_count": len(cited_curated),
        "cited_foundational_count": len(cited & FOUNDATIONAL_KEYS),
        "cited_recent_share": len(cited_recent) / len(cited_curated) if cited_curated else 0.0,
        "unused_bibliography_entries": sorted(set(entries) - cited),
    }


def bibliography_checks_pass(report, citations):
    return (
        report["curated_count"] == CURATED_COUNT,
        report["foundational_count"] == len(FOUNDATIONAL_KEYS),
        report["duplicate_dois"] == [],
        report["entries_with_url_field"] == [],
        report["entries_without_year"] == [],
        report["curated_recent_count"] == report["curated_count"],
        citations["missing_bibliography_keys"] == [],
        citations["uncited_curated_keys"] == [],
        citations["cited_curated_count"] == CURATED_COUNT,
        citations["cited_recent_share"] >= RECENT_SHARE_MINIMUM,
    )
