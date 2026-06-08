"""Polite HTTP fetching and raw-crawl metadata (component 6)."""

from __future__ import annotations

from .client import (
    DEFAULT_MAX_BYTES,
    DEFAULT_MAX_REDIRECTS,
    DEFAULT_MAX_RETRIES,
    DEFAULT_TIMEOUT_SECONDS,
    RETRYABLE_STATUS,
    HttpClient,
    make_robots_fetcher,
)
from .models import FetchOutcome, RawCrawlRecord, build_raw_record, sha256_hex

__all__ = [
    "HttpClient",
    "make_robots_fetcher",
    "FetchOutcome",
    "RawCrawlRecord",
    "build_raw_record",
    "sha256_hex",
    "DEFAULT_TIMEOUT_SECONDS",
    "DEFAULT_MAX_RETRIES",
    "DEFAULT_MAX_REDIRECTS",
    "DEFAULT_MAX_BYTES",
    "RETRYABLE_STATUS",
]
