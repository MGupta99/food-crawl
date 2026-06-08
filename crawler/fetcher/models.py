"""Fetch results and the raw-crawl metadata record.

:class:`FetchOutcome` is the low-level result of one HTTP fetch (status, body,
content hash, timing, transport errors). :class:`RawCrawlRecord` is the
per-fetch metadata document defined in ``plan.md`` ("Raw Crawl Format") that
accompanies each stored page; it joins the fetch result with frontier context
(``crawl_id``, ``canonical_url``, ``discovery_relevance``) and the storage URI.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime


def sha256_hex(data: bytes) -> str:
    """Content-addressed digest of a response body."""
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _iso_z(ts: datetime) -> str:
    """Format a naive-UTC datetime as ``...Z`` (matching the plan's JSON)."""
    return ts.replace(microsecond=0).isoformat() + "Z"


@dataclass(frozen=True, slots=True)
class FetchOutcome:
    """Result of a single HTTP fetch attempt (after retries/redirects)."""

    url: str  # the URL we were asked to fetch
    final_url: str  # URL after following redirects
    status_code: int | None  # None only on transport failure
    content_type: str | None  # raw Content-Type header (may include charset)
    body: bytes
    content_hash: str | None  # sha256 of body; None on transport failure
    fetch_timestamp: datetime  # naive UTC, request start
    elapsed_seconds: float
    num_redirects: int
    truncated: bool  # body hit the byte cap and was cut short
    error: str | None  # transport/timeout error, if any

    @property
    def ok(self) -> bool:
        """True if an HTTP response was received (even 4xx/5xx)."""
        return self.error is None and self.status_code is not None

    @property
    def is_success(self) -> bool:
        return self.status_code is not None and 200 <= self.status_code < 300

    @property
    def content_length(self) -> int:
        return len(self.body)

    @property
    def mime_type(self) -> str | None:
        """Content-Type without parameters, e.g. ``text/html``."""
        if not self.content_type:
            return None
        return self.content_type.split(";", 1)[0].strip().lower() or None


@dataclass(frozen=True, slots=True)
class RawCrawlRecord:
    """Per-fetch metadata document (see ``plan.md`` → Raw Crawl Format)."""

    crawl_id: str
    url: str
    canonical_url: str
    host: str
    status_code: int | None
    content_type: str | None
    fetch_timestamp: datetime
    content_hash: str | None
    discovery_relevance: float
    raw_gcs_uri: str | None

    def to_dict(self) -> dict:
        return {
            "crawl_id": self.crawl_id,
            "url": self.url,
            "canonical_url": self.canonical_url,
            "host": self.host,
            "status_code": self.status_code,
            "content_type": self.content_type,
            "fetch_timestamp": _iso_z(self.fetch_timestamp),
            "content_hash": self.content_hash,
            "discovery_relevance": self.discovery_relevance,
            "raw_gcs_uri": self.raw_gcs_uri,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), separators=(",", ":"))


def build_raw_record(
    outcome: FetchOutcome,
    *,
    crawl_id: str,
    canonical_url: str,
    host: str,
    discovery_relevance: float = 0.0,
    raw_gcs_uri: str | None = None,
) -> RawCrawlRecord:
    """Assemble a :class:`RawCrawlRecord` from a fetch outcome + frontier context.

    ``content_type`` is normalized to its MIME type (no charset) to match the
    plan's example.
    """
    return RawCrawlRecord(
        crawl_id=crawl_id,
        url=outcome.url,
        canonical_url=canonical_url,
        host=host,
        status_code=outcome.status_code,
        content_type=outcome.mime_type,
        fetch_timestamp=outcome.fetch_timestamp,
        content_hash=outcome.content_hash,
        discovery_relevance=discovery_relevance,
        raw_gcs_uri=raw_gcs_uri,
    )
