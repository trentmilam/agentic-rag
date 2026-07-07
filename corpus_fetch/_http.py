"""Shared HTTP plumbing for the corpus_fetch fetchers.

Every fetcher in this package hits the same two real, public hosts
(``rfc-editor.org``, ``errata.rfc-editor.org``, ``iana.org``) with the same
identifying ``User-Agent``, the same small bounded connection pool, and the same
retry-with-backoff on transient failures -- factored out once so each ``fetch_*.py``
module states only what it fetches, not how to be polite about it.

Politeness here means: never more than ``DEFAULT_MAX_WORKERS`` requests to a host in
flight at once (a real bounded thread pool, not unbounded ``asyncio.gather``-style
fan-out), plus a small per-request pause on top of that pool -- this is a portfolio
demo hitting production IETF/IANA infrastructure, not a load test.
"""
from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, Iterable, TypeVar

import requests

USER_AGENT = (
    "agentic-rag-portfolio-demo/0.1 "
    "(+contact: trent@trentmilam.dev; purpose: personal portfolio RAG demo, non-commercial)"
)
DEFAULT_TIMEOUT_SECONDS = 30
MAX_RETRIES = 3
RETRY_BACKOFF_SECONDS = 2.0
DEFAULT_MAX_WORKERS = 8
POLITENESS_DELAY_SECONDS = 0.05  # small per-request pause, on top of the bounded pool

T = TypeVar("T")


def new_session() -> requests.Session:
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})
    return session


def get_with_retries(
    session: requests.Session, url: str, *, timeout: int = DEFAULT_TIMEOUT_SECONDS
) -> requests.Response:
    """GET with a few retries on transient (network / 5xx) failures.

    Raises on the final attempt so a caller doing thousands of these never mistakes a
    real, persistent failure for a success -- see each fetcher's own tally/report
    logic for how failures are surfaced rather than swallowed.
    """
    last_exc: Exception | None = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = session.get(url, timeout=timeout)
            if resp.status_code >= 500:
                raise requests.HTTPError(f"{resp.status_code} Server Error for {url}", response=resp)
            time.sleep(POLITENESS_DELAY_SECONDS)
            return resp
        except requests.RequestException as exc:
            last_exc = exc
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_BACKOFF_SECONDS * attempt)
    assert last_exc is not None
    raise last_exc


def fetch_many(items: Iterable[T], fetch_one: Callable[[T], None], *, max_workers: int = DEFAULT_MAX_WORKERS) -> None:
    """Run ``fetch_one`` over ``items`` on a small bounded thread pool.

    This bounded pool -- never more than ``max_workers`` requests in flight -- IS the
    politeness mechanism the callers rely on; ``fetch_one`` itself does no additional
    concurrency control.
    """
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        list(pool.map(fetch_one, items))
