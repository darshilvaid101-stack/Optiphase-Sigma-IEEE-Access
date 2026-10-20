"""Deterministic deduplication: exact DOI first, then near-identical titles within a year."""

from collections import defaultdict

from lib.constants import TITLE_BUCKET_LENGTH, TITLE_DEDUPE_MIN_SIMILARITY
from lib.title_similarity import normalize_title, title_similarity


def dedupe_by_doi(records):
    """Keep the first record per DOI; return (kept, dropped) where dropped explains why."""
    seen_dois = set()
    kept, dropped = [], []
    for record in records:
        if record["doi"] in seen_dois:
            dropped.append({"record": record, "reason": "duplicate_doi", "twin_doi": record["doi"]})
            continue
        seen_dois.add(record["doi"])
        kept.append(record)
    return kept, dropped


def find_title_twin(candidates, record):
    for candidate in candidates:
        if title_similarity(candidate["title"], record["title"]) >= TITLE_DEDUPE_MIN_SIMILARITY:
            return candidate
    return None


def dedupe_by_title_year(records):
    """Drop records whose title is near-identical to an earlier record from the same year.

    Titles are bucketed by year and their first TITLE_BUCKET_LENGTH normalised characters,
    so near-duplicates that differ only after that prefix are not caught (a known limit).
    """
    buckets = defaultdict(list)
    kept, dropped = [], []
    for record in records:
        bucket_key = (record["year"], normalize_title(record["title"])[:TITLE_BUCKET_LENGTH])
        twin = find_title_twin(buckets[bucket_key], record)
        if twin is None:
            buckets[bucket_key].append(record)
            kept.append(record)
        else:
            dropped.append({"record": record, "reason": "duplicate_title", "twin_doi": twin["doi"]})
    return kept, dropped
