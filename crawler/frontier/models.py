"""Row dataclasses returned by :class:`crawler.frontier.repository.FrontierRepository`."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True, slots=True)
class FrontierUrl:
    id: int
    url_hash: str
    canonical_url: str
    host: str
    status: str
    priority: int
    relevance_score: float
    topic_source: str | None
    depth: int
    discovered_from: str | None
    first_seen_at: datetime | None
    last_attempt_at: datetime | None
    next_fetch_after: datetime | None
    lease_expires_at: datetime | None
    lease_token: str | None
    retry_count: int
    content_hash: str | None
    failure_reason: str | None

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> FrontierUrl:
        return cls(
            id=row["id"],
            url_hash=row["url_hash"],
            canonical_url=row["canonical_url"],
            host=row["host"],
            status=row["status"],
            priority=row["priority"],
            relevance_score=row["relevance_score"],
            topic_source=row["topic_source"],
            depth=row["depth"],
            discovered_from=row["discovered_from"],
            first_seen_at=row["first_seen_at"],
            last_attempt_at=row["last_attempt_at"],
            next_fetch_after=row["next_fetch_after"],
            lease_expires_at=row["lease_expires_at"],
            lease_token=row["lease_token"],
            retry_count=row["retry_count"],
            content_hash=row["content_hash"],
            failure_reason=row["failure_reason"],
        )


@dataclass(frozen=True, slots=True)
class HostState:
    host: str
    is_seed: bool
    allow: bool
    robots_txt: str | None
    robots_fetched_at: datetime | None
    crawl_delay_seconds: int
    last_fetch_at: datetime | None
    next_allowed_fetch_at: datetime | None
    consecutive_failures: int
    relevant_pages: int
    irrelevant_pages: int

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> HostState:
        return cls(
            host=row["host"],
            is_seed=bool(row["is_seed"]),
            allow=bool(row["allow"]),
            robots_txt=row["robots_txt"],
            robots_fetched_at=row["robots_fetched_at"],
            crawl_delay_seconds=row["crawl_delay_seconds"],
            last_fetch_at=row["last_fetch_at"],
            next_allowed_fetch_at=row["next_allowed_fetch_at"],
            consecutive_failures=row["consecutive_failures"],
            relevant_pages=row["relevant_pages"],
            irrelevant_pages=row["irrelevant_pages"],
        )
