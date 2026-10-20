"""Combine OpenAlex discovery data with Crossref verification into one bibliographic record."""

from lib.constants import HARVEST_YEARS


def choose_abstract(crossref_abstract, openalex_abstract):
    if crossref_abstract:
        return crossref_abstract, "crossref"
    if openalex_abstract:
        return openalex_abstract, "openalex"
    return None, None


def build_record(openalex, crossref, similarity):
    """Merge a verified pair; Crossref supplies bibliographic fields, OpenAlex fills gaps."""
    abstract, abstract_source = choose_abstract(crossref["abstract"], openalex["abstract"])
    return {
        "venue": openalex["venue"],
        "openalex_id": openalex["openalex_id"],
        "doi": openalex["doi"],
        "title": crossref["title"],
        "year": crossref["year"],
        "crossref_type": crossref["crossref_type"],
        "authors": crossref["authors"],
        "container_title": crossref["container_title"] or openalex["source_name"],
        "volume": crossref["volume"] or openalex["volume"],
        "issue": crossref["issue"] or openalex["issue"],
        "pages": crossref["pages"] or openalex["pages"],
        "article_number": crossref["article_number"],
        "publisher": crossref["publisher"],
        "abstract": abstract,
        "abstract_source": abstract_source,
        "title_similarity": round(similarity, 4),
        "arxiv_id": None,
        "harvest_years": list(HARVEST_YEARS),
    }
