"""Bounded Semantic Scholar probe; unauthenticated access is rate-limited, so failures are recorded."""

import os
import time

import requests

from lib.constants import (
    HTTP_OK,
    REQUEST_TIMEOUT_SECONDS,
    SEMANTIC_SCHOLAR_API_KEY_VARIABLE,
    SEMANTIC_SCHOLAR_PROBE_ATTEMPTS,
    SEMANTIC_SCHOLAR_PROBE_BACKOFF_SECONDS,
    SEMANTIC_SCHOLAR_SEARCH_URL,
)

HTTP_TOO_MANY_REQUESTS = 429
PROBE_FIELDS = "title,year,venue,externalIds"
PROBE_LIMIT = 5


def build_headers():
    api_key = os.environ.get(SEMANTIC_SCHOLAR_API_KEY_VARIABLE)
    return {"x-api-key": api_key} if api_key else {}


def probe_semantic_scholar(session, query):
    """Return (status, hit_count) after at most a few throttled attempts; never loops forever."""
    params = {"query": query, "limit": PROBE_LIMIT, "fields": PROBE_FIELDS}
    for attempt in range(1, SEMANTIC_SCHOLAR_PROBE_ATTEMPTS + 1):
        try:
            response = session.get(
                SEMANTIC_SCHOLAR_SEARCH_URL,
                params=params,
                headers=build_headers(),
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
        except requests.RequestException as error:
            return f"network_error:{type(error).__name__}", 0
        if response.status_code == HTTP_OK:
            return "ok", len(response.json().get("data", []))
        if response.status_code != HTTP_TOO_MANY_REQUESTS:
            return f"http_{response.status_code}", 0
        time.sleep(SEMANTIC_SCHOLAR_PROBE_BACKOFF_SECONDS * attempt)
    return "rate_limited", 0
