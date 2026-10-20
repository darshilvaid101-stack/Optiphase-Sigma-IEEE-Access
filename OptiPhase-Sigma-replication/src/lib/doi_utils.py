"""DOI normalisation shared by the OpenAlex, Crossref, and arXiv clients."""

DOI_URL_PREFIXES = (
    "https://doi.org/",
    "http://doi.org/",
    "https://dx.doi.org/",
    "http://dx.doi.org/",
)


def normalize_doi(raw_doi):
    """Return a lowercase bare DOI such as 10.1145/3750450, or None when absent."""
    if not raw_doi:
        return None
    bare_doi = raw_doi.strip()
    for prefix in DOI_URL_PREFIXES:
        bare_doi = bare_doi.removeprefix(prefix)
    return bare_doi.lower() or None
