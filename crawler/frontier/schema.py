"""URL frontier schema (SQLAlchemy Core).

This is the single source of truth for the three frontier tables described in
``plan.md``:

- ``frontier_urls`` — what to crawl next (leasing reads from here)
- ``host_state``    — per-host politeness + reputation
- ``crawl_runs``    — per-crawl bookkeeping

The metadata targets PostgreSQL (Cloud SQL) in production but is dialect-portable
so the same schema can be created on in-memory SQLite for unit tests. A
``BigInteger`` primary key falls back to ``Integer`` on SQLite so autoincrement
works there.
"""

from __future__ import annotations

from enum import StrEnum

import sqlalchemy as sa

metadata = sa.MetaData()

# BIGSERIAL on Postgres, INTEGER autoincrement on SQLite.
_BigPK = sa.BigInteger().with_variant(sa.Integer(), "sqlite")
_now = sa.func.current_timestamp()


class FrontierStatus(StrEnum):
    """Lifecycle states for a frontier URL."""

    QUEUED = "queued"
    FETCHING = "fetching"
    FETCHED = "fetched"
    FAILED = "failed"
    SKIPPED = "skipped"


class TopicSource(StrEnum):
    SEED = "seed"
    DISCOVERED = "discovered"


frontier_urls = sa.Table(
    "frontier_urls",
    metadata,
    sa.Column("id", _BigPK, primary_key=True, autoincrement=True),
    sa.Column("url_hash", sa.Text, nullable=False, unique=True),
    sa.Column("canonical_url", sa.Text, nullable=False),
    sa.Column("host", sa.Text, nullable=False),
    sa.Column("status", sa.Text, nullable=False, server_default=FrontierStatus.QUEUED.value),
    sa.Column("priority", sa.Integer, nullable=False, server_default=sa.text("0")),
    sa.Column("relevance_score", sa.Float, nullable=False, server_default=sa.text("0")),
    sa.Column("topic_source", sa.Text),
    sa.Column("depth", sa.Integer, nullable=False, server_default=sa.text("0")),
    sa.Column("discovered_from", sa.Text),
    sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False, server_default=_now),
    sa.Column("last_attempt_at", sa.DateTime(timezone=True)),
    sa.Column("next_fetch_after", sa.DateTime(timezone=True), nullable=False, server_default=_now),
    sa.Column("lease_expires_at", sa.DateTime(timezone=True)),
    sa.Column("retry_count", sa.Integer, nullable=False, server_default=sa.text("0")),
    sa.Column("content_hash", sa.Text),
    sa.Column("failure_reason", sa.Text),
)

# Lease query: WHERE status='queued' AND next_fetch_after <= now ORDER BY
# priority DESC, relevance_score DESC.
sa.Index(
    "ix_frontier_lease",
    frontier_urls.c.status,
    frontier_urls.c.next_fetch_after,
    frontier_urls.c.priority.desc(),
    frontier_urls.c.relevance_score.desc(),
)
sa.Index("ix_frontier_host", frontier_urls.c.host)


host_state = sa.Table(
    "host_state",
    metadata,
    sa.Column("host", sa.Text, primary_key=True),
    sa.Column("is_seed", sa.Boolean, nullable=False, server_default=sa.false()),
    sa.Column("allow", sa.Boolean, nullable=False, server_default=sa.true()),
    sa.Column("robots_txt", sa.Text),
    sa.Column("robots_fetched_at", sa.DateTime(timezone=True)),
    sa.Column("crawl_delay_seconds", sa.Integer, nullable=False, server_default=sa.text("5")),
    sa.Column("last_fetch_at", sa.DateTime(timezone=True)),
    sa.Column("next_allowed_fetch_at", sa.DateTime(timezone=True)),
    sa.Column("consecutive_failures", sa.Integer, nullable=False, server_default=sa.text("0")),
    sa.Column("relevant_pages", sa.BigInteger, nullable=False, server_default=sa.text("0")),
    sa.Column("irrelevant_pages", sa.BigInteger, nullable=False, server_default=sa.text("0")),
)


crawl_runs = sa.Table(
    "crawl_runs",
    metadata,
    sa.Column("crawl_id", sa.Text, primary_key=True),
    sa.Column("started_at", sa.DateTime(timezone=True)),
    sa.Column("finished_at", sa.DateTime(timezone=True)),
    sa.Column("status", sa.Text),
    sa.Column("pages_fetched", sa.BigInteger, nullable=False, server_default=sa.text("0")),
    sa.Column("pages_failed", sa.BigInteger, nullable=False, server_default=sa.text("0")),
    sa.Column("pages_irrelevant", sa.BigInteger, nullable=False, server_default=sa.text("0")),
    sa.Column("bytes_downloaded", sa.BigInteger, nullable=False, server_default=sa.text("0")),
)
