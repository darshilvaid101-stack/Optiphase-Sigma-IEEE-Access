"""Shared HTTP session with an identifying User-Agent and bounded, typed retries."""

import time

import requests

from lib.constants import (
    BACKOFF_BASE_SECONDS,
    ERROR_DETAIL_LIMIT,
    HTTP_OK,
    MAX_RETRIES,
    REQUEST_TIMEOUT_SECONDS,
    RETRYABLE_STATUS_CODES,
    USER_AGENT,
)

NETWORK_FAILURE_STATUS = "network"


class HarvestRequestError(RuntimeError):
    """An upstream API kept failing after bounded retries or returned an unexpected status."""

    def __init__(self, url, status, detail):
        super().__init__(f"{url} failed (status={status}): {detail}")
        self.url = url
        self.status = status


def create_session():
    session = requests.Session()
    session.headers.update(
        {"User-Agent": USER_AGENT, "Accept": "application/json, application/atom+xml, */*"},
    )
    return session


def retry_delay_seconds(attempt, retry_after):
    if retry_after is not None and retry_after.isdigit():
        return float(retry_after)
    return BACKOFF_BASE_SECONDS * (2**attempt)


def get_response(session, url, params=None):
    """Return the first non-retryable response; raise HarvestRequestError once retries run out."""
    status, detail = NETWORK_FAILURE_STATUS, ""
    for attempt in range(MAX_RETRIES + 1):
        try:
            response = session.get(url, params=params, timeout=REQUEST_TIMEOUT_SECONDS)
        except requests.RequestException as error:
            status, detail = NETWORK_FAILURE_STATUS, str(error)[:ERROR_DETAIL_LIMIT]
            time.sleep(retry_delay_seconds(attempt, None))
            continue
        if response.status_code not in RETRYABLE_STATUS_CODES:
            return response
        status, detail = response.status_code, response.text[:ERROR_DETAIL_LIMIT]
        time.sleep(retry_delay_seconds(attempt, response.headers.get("Retry-After")))
    raise HarvestRequestError(url, status, detail)


def require_ok(url, response):
    if response.status_code != HTTP_OK:
        raise HarvestRequestError(url, response.status_code, response.text[:ERROR_DETAIL_LIMIT])
    return response


def get_json(session, url, params=None):
    return require_ok(url, get_response(session, url, params)).json()
