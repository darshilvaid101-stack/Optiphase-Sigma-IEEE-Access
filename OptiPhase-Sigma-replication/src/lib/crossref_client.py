"""Crossref metadata lookup used to verify each harvested DOI and supply BibTeX fields."""

from urllib.parse import quote

from lib.abstract_text import strip_markup
from lib.constants import CROSSREF_WORKS_URL, HTTP_NOT_FOUND
from lib.doi_utils import normalize_doi
from lib.http_client import get_response, require_ok

DATE_FIELDS = ("published", "published-print", "published-online", "issued")


def fetch_crossref_message(session, doi):
    """Return Crossref's message for a DOI, or None when Crossref has no record of it."""
    url = f"{CROSSREF_WORKS_URL}/{quote(doi, safe='/')}"
    response = get_response(session, url)
    if response.status_code == HTTP_NOT_FOUND:
        return None
    return require_ok(url, response).json()["message"]


def first_or_none(values):
    return values[0] if values else None


def extract_year(message):
    for field_name in DATE_FIELDS:
        date_parts = (message.get(field_name) or {}).get("date-parts") or [[None]]
        year = date_parts[0][0]
        if year:
            return int(year)
    return None


def normalize_author(author):
    return {
        "family": author.get("family"),
        "given": author.get("given"),
        "name": author.get("name"),
    }


def normalize_crossref_message(message):
    """Reduce a Crossref work message to the bibliographic fields used downstream."""
    return {
        "doi": normalize_doi(message.get("DOI")),
        "title": strip_markup(first_or_none(message.get("title"))),
        "authors": [normalize_author(author) for author in message.get("author") or []],
        "container_title": strip_markup(first_or_none(message.get("container-title"))),
        "volume": message.get("volume"),
        "issue": message.get("issue"),
        "pages": message.get("page"),
        "article_number": message.get("article-number"),
        "publisher": message.get("publisher"),
        "crossref_type": message.get("type"),
        "year": extract_year(message),
        "abstract": strip_markup(message.get("abstract")),
    }
