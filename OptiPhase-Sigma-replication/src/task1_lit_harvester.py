"""Task 1: harvest 2024-2026 venue papers, verify each DOI against Crossref, and write BibTeX."""

import argparse
import json
import sys
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path

import bibtexparser

from lib.arxiv_client import fetch_category_entries
from lib.bibtex_writer import assign_keys, render_entry
from lib.constants import (
    ALLOWED_CROSSREF_TYPES,
    ARXIV_CATEGORIES,
    CROSSREF_PACING_SECONDS,
    CROSSREF_TITLE_MIN_SIMILARITY,
    CROSSREF_WORKERS,
    HARVEST_YEARS,
)
from lib.crossref_client import fetch_crossref_message, normalize_crossref_message
from lib.dedupe_records import dedupe_by_doi, dedupe_by_title_year
from lib.http_client import HarvestRequestError, create_session
from lib.openalex_client import fetch_venue_works, normalize_work
from lib.record_builder import build_record
from lib.semantic_scholar_probe import probe_semantic_scholar
from lib.title_similarity import normalize_title, title_similarity
from lib.topic_tags import is_compiler_topic
from lib.venues import VENUE_SPECS

REPO_ROOT = Path(__file__).resolve().parent.parent
LITERATURE_DIR = REPO_ROOT / "data" / "literature"
BIB_PATH = LITERATURE_DIR / "references_2500.bib"
METADATA_PATH = LITERATURE_DIR / "harvested_metadata.jsonl"
EXCLUSIONS_PATH = LITERATURE_DIR / "harvest_exclusions.jsonl"
SUMMARY_PATH = LITERATURE_DIR / "harvest_summary.json"
GATE_MIN_ENTRIES = 2500
PROGRESS_INTERVAL = 250
REQUIRED_BIBTEX_FIELDS = ("author", "title", "year", "doi")
SEMANTIC_SCHOLAR_PROBE_QUERY = "LLVM new pass manager phase ordering"
DBLP_STATUS = (
    "not used: dblp.org answered every request with an anti-bot challenge page "
    "(HTTP 202, HTML body), so no DBLP data was collected"
)


def log(message):
    timestamp = datetime.now(UTC).strftime("%H:%M:%S")
    print(f"[{timestamp}] {message}", file=sys.stderr, flush=True)


def harvest_openalex(session, max_pages):
    """Discover works for every named venue; return normalized records and per-venue counts."""
    records, returned_by_venue = [], {}
    for spec in VENUE_SPECS:
        works = fetch_venue_works(session, spec, max_pages)
        returned_by_venue[spec.key] = len(works)
        records.extend(normalize_work(work, spec) for work in works)
        log(f"OpenAlex {spec.key}: {len(works)} works")
    return records, returned_by_venue


def verify_one(session, record):
    """Check one DOI against Crossref; failures become verdicts and are never raised."""
    try:
        message = fetch_crossref_message(session, record["doi"])
    except HarvestRequestError as error:
        return {"record": record, "status": "crossref_error", "detail": str(error)}
    finally:
        time.sleep(CROSSREF_PACING_SECONDS)
    if message is None:
        return {"record": record, "status": "crossref_not_found", "detail": None}
    crossref = normalize_crossref_message(message)
    similarity = title_similarity(record["title"], crossref["title"])
    status = "verified" if similarity >= CROSSREF_TITLE_MIN_SIMILARITY else "title_mismatch"
    return {
        "record": record,
        "status": status,
        "detail": None,
        "crossref": crossref,
        "similarity": similarity,
    }


def verify_with_crossref(session, records):
    verdicts = []
    with ThreadPoolExecutor(max_workers=CROSSREF_WORKERS) as executor:
        for verdict in executor.map(lambda record: verify_one(session, record), records):
            verdicts.append(verdict)
            if len(verdicts) % PROGRESS_INTERVAL == 0:
                log(f"Crossref checked {len(verdicts)}/{len(records)}")
    return verdicts


def rejection_reason(verdict):
    if verdict["status"] != "verified":
        return verdict["status"]
    crossref = verdict["crossref"]
    if crossref["crossref_type"] not in ALLOWED_CROSSREF_TYPES:
        return f"crossref_type:{crossref['crossref_type']}"
    if not crossref["authors"]:
        return "no_authors"
    if crossref["year"] not in HARVEST_YEARS:
        return f"year_outside_window:{crossref['year']}"
    return None


def exclusion_row(reason, record, detail=None):
    return {
        "reason": reason,
        "venue": record["venue"],
        "openalex_id": record["openalex_id"],
        "doi": record["doi"],
        "title": record["title"],
        "detail": detail,
    }


def split_verdicts(verdicts):
    """Build records for verified works and an explicit exclusion row for everything else."""
    accepted, exclusions = [], []
    for verdict in verdicts:
        reason = rejection_reason(verdict)
        if reason is None:
            record = build_record(verdict["record"], verdict["crossref"], verdict["similarity"])
            accepted.append(record)
        else:
            exclusions.append(exclusion_row(reason, verdict["record"], verdict["detail"]))
    return accepted, exclusions


def attach_arxiv_matches(records, entries):
    """Link arXiv preprints to accepted records by DOI, then by normalized title."""
    by_doi = {record["doi"]: record for record in records}
    by_title = {normalize_title(record["title"]): record for record in records}
    matched = 0
    for entry in entries:
        record = by_doi.get(entry["doi"]) or by_title.get(normalize_title(entry["title"]))
        if record is None or record["arxiv_id"] is not None:
            continue
        record["arxiv_id"] = entry["arxiv_id"]
        matched += 1
        if record["abstract"] is None and entry["summary"]:
            record["abstract"] = entry["summary"]
            record["abstract_source"] = "arxiv"
    return matched


def crosscheck_arxiv(session, records):
    entries, failures = [], []
    for category in ARXIV_CATEGORIES:
        try:
            entries.extend(fetch_category_entries(session, category))
        except HarvestRequestError as error:
            failures.append(str(error))
        log(f"arXiv {category}: {len(entries)} entries collected so far")
    matched = attach_arxiv_matches(records, entries)
    return {"entries_seen": len(entries), "matched_records": matched, "failures": failures}


def run_semantic_scholar_probe(session):
    status, hits = probe_semantic_scholar(session, SEMANTIC_SCHOLAR_PROBE_QUERY)
    log(f"Semantic Scholar probe: {status} ({hits} hits)")
    return {"status": status, "hits": hits}


def collect_entries(max_pages):
    """Run discovery, verification, deduplication, and cross-checks; return entries and stats."""
    session = create_session()
    openalex_records, returned_by_venue = harvest_openalex(session, max_pages)
    with_doi = [record for record in openalex_records if record["doi"]]
    unique, doi_dropped = dedupe_by_doi(with_doi)
    verdicts = verify_with_crossref(session, unique)
    accepted, exclusions = split_verdicts(verdicts)
    deduped, title_dropped = dedupe_by_title_year(accepted)
    exclusions += [exclusion_row("missing_doi", record) for record in openalex_records if not record["doi"]]
    exclusions += [exclusion_row(item["reason"], item["record"], item["twin_doi"]) for item in doi_dropped]
    exclusions += [exclusion_row(item["reason"], item["record"], item["twin_doi"]) for item in title_dropped]
    arxiv_summary = crosscheck_arxiv(session, deduped)
    for record in deduped:
        record["compiler_topic"] = is_compiler_topic(record["title"], record["abstract"])
    stats = {
        "openalex_returned_by_venue": returned_by_venue,
        "openalex_total": len(openalex_records),
        "missing_doi": len(openalex_records) - len(with_doi),
        "after_doi_dedupe": len(unique),
        "crossref_status_counts": dict(Counter(verdict["status"] for verdict in verdicts)),
        "accepted_before_title_dedupe": len(accepted),
        "title_year_duplicates": len(title_dropped),
        "final_entries": len(deduped),
        "arxiv": arxiv_summary,
        "semantic_scholar": run_semantic_scholar_probe(session),
        "dblp": DBLP_STATUS,
    }
    return deduped, exclusions, stats


def render_bibtex(keyed_records, timestamp):
    header = (
        f"% Generated by src/task1_lit_harvester.py at {timestamp} (UTC).\n"
        "% Every entry was matched to Crossref by DOI before it was written; do not edit by hand.\n\n"
    )
    return header + "\n".join(render_entry(record) for record in keyed_records)


def write_jsonl(path, rows):
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def write_outputs(entries, exclusions):
    keyed = assign_keys(entries)
    timestamp = datetime.now(UTC).isoformat(timespec="seconds")
    BIB_PATH.write_text(render_bibtex(keyed, timestamp), encoding="utf-8")
    write_jsonl(METADATA_PATH, keyed)
    write_jsonl(EXCLUSIONS_PATH, exclusions)
    return keyed


def has_required_fields(entry):
    fields = entry.fields_dict
    return all(name in fields and fields[name].value for name in REQUIRED_BIBTEX_FIELDS)


def validate_bibtex(path):
    library = bibtexparser.parse_file(str(path))
    incomplete_keys = [entry.key for entry in library.entries if not has_required_fields(entry)]
    return {
        "parsed_entries": len(library.entries),
        "failed_blocks": len(library.failed_blocks),
        "entries_missing_required_fields": len(incomplete_keys),
        "first_incomplete_keys": incomplete_keys[:10],
    }


def build_summary(keyed, stats, validation):
    gate_passed = (
        validation["parsed_entries"] >= GATE_MIN_ENTRIES
        and validation["failed_blocks"] == 0
        and validation["entries_missing_required_fields"] == 0
    )
    return {
        "generated_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "harvest_years": list(HARVEST_YEARS),
        "final_entries": len(keyed),
        "compiler_topic_entries": sum(1 for entry in keyed if entry["compiler_topic"]),
        "abstract_sources": dict(Counter(entry["abstract_source"] or "none" for entry in keyed)),
        "gate_1": {
            "required_entries": GATE_MIN_ENTRIES,
            "parsed_entries": validation["parsed_entries"],
            "passed": gate_passed,
        },
        "bibtex_validation": validation,
        "stats": stats,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--max-pages",
        type=int,
        default=None,
        help="cap OpenAlex pages per venue (smoke tests only)",
    )
    arguments = parser.parse_args()
    entries, exclusions, stats = collect_entries(arguments.max_pages)
    keyed = write_outputs(entries, exclusions)
    validation = validate_bibtex(BIB_PATH)
    summary = build_summary(keyed, stats, validation)
    SUMMARY_PATH.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    log(f"entries written: {len(keyed)}; gate 1 passed: {summary['gate_1']['passed']}")
    return 0 if summary["gate_1"]["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
