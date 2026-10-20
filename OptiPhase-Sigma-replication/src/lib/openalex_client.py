"""OpenAlex works discovery for named venues and the harvest year window."""

from lib.abstract_text import reconstruct_abstract
from lib.constants import (
    ALLOWED_OPENALEX_TYPES,
    HARVEST_YEARS,
    OPENALEX_PAGE_SIZE,
    OPENALEX_SELECT_FIELDS,
    OPENALEX_WORKS_URL,
)
from lib.doi_utils import normalize_doi
from lib.http_client import get_json

FIRST_PAGE = 1


def build_works_filter(spec):
    """Compose OpenAlex's filter string for one venue across the harvest years."""
    source_ids = "|".join(spec.openalex_source_ids)
    years = "|".join(str(year) for year in HARVEST_YEARS)
    work_types = "|".join(ALLOWED_OPENALEX_TYPES)
    clauses = [
        f"primary_location.source.id:{source_ids}",
        f"publication_year:{years}",
        f"type:{work_types}",
    ]
    if spec.openalex_issue:
        clauses.append(f"biblio.issue:{spec.openalex_issue}")
    return ",".join(clauses)


def build_page_params(spec, page):
    return {
        "filter": build_works_filter(spec),
        "per-page": OPENALEX_PAGE_SIZE,
        "page": page,
        "select": OPENALEX_SELECT_FIELDS,
    }


def fetch_venue_works(session, spec, max_pages):
    """Page through OpenAlex by page number, which needs no API key (cursor paging does).

    Stops at the first short page, or after max_pages when smoke-testing.
    """
    works, page = [], FIRST_PAGE
    while max_pages is None or page <= max_pages:
        payload = get_json(session, OPENALEX_WORKS_URL, build_page_params(spec, page))
        results = payload["results"]
        works.extend(results)
        if len(results) < OPENALEX_PAGE_SIZE:
            break
        page += 1
    return works


def openalex_pages(work_biblio):
    first_page, last_page = work_biblio.get("first_page"), work_biblio.get("last_page")
    if first_page and last_page:
        return f"{first_page}-{last_page}"
    return first_page


def normalize_work(work, spec):
    """Reduce an OpenAlex work to the fields the bibliography and gap miner need."""
    biblio = work.get("biblio") or {}
    source = (work.get("primary_location") or {}).get("source") or {}
    return {
        "venue": spec.key,
        "openalex_id": work["id"],
        "doi": normalize_doi(work.get("doi")),
        "title": work.get("title") or work.get("display_name"),
        "abstract": reconstruct_abstract(work.get("abstract_inverted_index")),
        "source_name": source.get("display_name"),
        "volume": biblio.get("volume"),
        "issue": biblio.get("issue"),
        "pages": openalex_pages(biblio),
    }
