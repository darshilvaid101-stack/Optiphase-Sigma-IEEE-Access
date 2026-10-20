"""Constants shared by the OptiPhase-Sigma literature harvester and gap miner."""

USER_AGENT = (
    "OptiPhaseSigma-harvester/1.0 (research; https://github.com/darshilvaid101-stack/Compiler-)"
)
HARVEST_YEARS = (2024, 2025, 2026)
ALLOWED_OPENALEX_TYPES = ("article", "conference-paper", "review")
ALLOWED_CROSSREF_TYPES = ("journal-article", "proceedings-article")

HTTP_OK = 200
HTTP_NOT_FOUND = 404
RETRYABLE_STATUS_CODES = (429, 500, 502, 503, 504)
REQUEST_TIMEOUT_SECONDS = 60
MAX_RETRIES = 5
BACKOFF_BASE_SECONDS = 2.0
ERROR_DETAIL_LIMIT = 200

OPENALEX_WORKS_URL = "https://api.openalex.org/works"
OPENALEX_PAGE_SIZE = 200
OPENALEX_SELECT_FIELDS = (
    "id,doi,title,publication_year,type,primary_location,biblio,abstract_inverted_index"
)

CROSSREF_WORKS_URL = "https://api.crossref.org/works"
CROSSREF_WORKERS = 4
CROSSREF_PACING_SECONDS = 0.5
CROSSREF_TITLE_MIN_SIMILARITY = 0.90

ARXIV_API_URL = "https://export.arxiv.org/api/query"
ARXIV_PAGE_SIZE = 100
ARXIV_MAX_RESULTS_PER_QUERY = 500
ARXIV_PACING_SECONDS = 3.0
ARXIV_CATEGORIES = ("cs.PL", "cs.SE", "cs.DC", "cs.AR")
ARXIV_TOPIC_TERMS = (
    "all:compiler",
    "all:LLVM",
    'all:"phase ordering"',
    "all:polyhedral",
    'all:"translation validation"',
    'all:"optimization pass"',
)

SEMANTIC_SCHOLAR_SEARCH_URL = "https://api.semanticscholar.org/graph/v1/paper/search"
SEMANTIC_SCHOLAR_API_KEY_VARIABLE = "SEMANTIC_SCHOLAR_API_KEY"
SEMANTIC_SCHOLAR_PROBE_ATTEMPTS = 3
SEMANTIC_SCHOLAR_PROBE_BACKOFF_SECONDS = 20.0

TITLE_DEDUPE_MIN_SIMILARITY = 0.97
TITLE_BUCKET_LENGTH = 24
