"""arXiv Atom API client used to cross-check DOIs and fill abstracts for accepted records."""

import time
import xml.etree.ElementTree as ElementTree

from lib.constants import (
    ARXIV_API_URL,
    ARXIV_MAX_RESULTS_PER_QUERY,
    ARXIV_PACING_SECONDS,
    ARXIV_PAGE_SIZE,
    ARXIV_TOPIC_TERMS,
    HARVEST_YEARS,
)
from lib.doi_utils import normalize_doi
from lib.http_client import get_response, require_ok

ATOM_NAMESPACES = {
    "atom": "http://www.w3.org/2005/Atom",
    "arxiv": "http://arxiv.org/schemas/atom",
}
ARXIV_ABSTRACT_MARKER = "/abs/"
WINDOW_START_SUFFIX = "01010000"
WINDOW_END_SUFFIX = "12312359"


def build_search_query(category):
    window_start = f"{HARVEST_YEARS[0]}{WINDOW_START_SUFFIX}"
    window_end = f"{HARVEST_YEARS[-1]}{WINDOW_END_SUFFIX}"
    terms = " OR ".join(ARXIV_TOPIC_TERMS)
    return f"cat:{category} AND ({terms}) AND submittedDate:[{window_start} TO {window_end}]"


def element_text(entry, path):
    node = entry.find(path, ATOM_NAMESPACES)
    if node is None or not node.text:
        return None
    return " ".join(node.text.split())


def parse_entry(entry):
    identifier = element_text(entry, "atom:id") or ""
    return {
        "arxiv_id": identifier.rsplit("/", 1)[-1],
        "title": element_text(entry, "atom:title"),
        "summary": element_text(entry, "atom:summary"),
        "doi": normalize_doi(element_text(entry, "arxiv:doi")),
        "journal_ref": element_text(entry, "arxiv:journal_ref"),
    }


def is_abstract_entry(entry):
    return ARXIV_ABSTRACT_MARKER in (element_text(entry, "atom:id") or "")


def parse_feed(xml_bytes):
    """Parse an arXiv feed; error pseudo-entries lack an /abs/ identifier and are skipped."""
    root = ElementTree.fromstring(xml_bytes)
    entries = root.findall("atom:entry", ATOM_NAMESPACES)
    return [parse_entry(entry) for entry in entries if is_abstract_entry(entry)]


def build_page_params(category, start):
    return {
        "search_query": build_search_query(category),
        "start": start,
        "max_results": ARXIV_PAGE_SIZE,
        "sortBy": "submittedDate",
        "sortOrder": "descending",
    }


def fetch_category_entries(session, category):
    """Page through one category's query, pacing requests as arXiv's usage policy asks."""
    collected = []
    for start in range(0, ARXIV_MAX_RESULTS_PER_QUERY, ARXIV_PAGE_SIZE):
        params = build_page_params(category, start)
        response = require_ok(ARXIV_API_URL, get_response(session, ARXIV_API_URL, params))
        page = parse_feed(response.content)
        collected.extend(page)
        if len(page) < ARXIV_PAGE_SIZE:
            break
        time.sleep(ARXIV_PACING_SECONDS)
    return collected
