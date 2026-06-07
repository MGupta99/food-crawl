"""Data-access layer for the URL frontier.

:class:`FrontierRepository` wraps a SQLAlchemy engine and provides the small set
of operations component 3 needs: idempotent URL insertion, seed insertion (it
implements the component-2 :class:`~crawler.seeds.models.SeedSink` protocol),
status updates, and lookups by id / url_hash.

Idempotency is enforced with dialect-aware ``INSERT ... ON CONFLICT DO NOTHING``
(``url_hash`` for URLs, ``host`` for host rows), matching ``plan.md``.
"""

from __future__ import annotations

from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.engine import Engine

from crawler.seeds.models import FrontierSeed

from .models import FrontierUrl, HostState
from .schema import FrontierStatus, TopicSource, frontier_urls, host_state, metadata

# Seeds enter the frontier at maximum priority and relevance: they are trusted
# entry points and should be crawled first.
SEED_PRIORITY = 100
SEED_RELEVANCE = 1.0


class FrontierRepository:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    # --- schema management ---

    def create_schema(self) -> None:
        metadata.create_all(self.engine)

    def drop_schema(self) -> None:
        metadata.drop_all(self.engine)

    # --- inserts ---

    @staticmethod
    def _insert(dialect_name: str):
        if dialect_name == "postgresql":
            return pg_insert
        if dialect_name == "sqlite":
            return sqlite_insert
        raise NotImplementedError(f"unsupported dialect: {dialect_name!r}")

    def _insert_ignore(
        self,
        conn: sa.Connection,
        table: sa.Table,
        values: dict[str, Any],
        *,
        index_elements: list[str],
        returning: sa.Column,
    ) -> bool:
        """Insert a row, ignoring conflicts. Returns True iff a new row was created."""
        insert = self._insert(conn.dialect.name)
        stmt = (
            insert(table)
            .values(**values)
            .on_conflict_do_nothing(index_elements=index_elements)
            .returning(returning)
        )
        return conn.execute(stmt).first() is not None

    def add_url(
        self,
        *,
        url_hash: str,
        canonical_url: str,
        host: str,
        status: FrontierStatus | str = FrontierStatus.QUEUED,
        priority: int = 0,
        relevance_score: float = 0.0,
        topic_source: TopicSource | str | None = TopicSource.DISCOVERED,
        depth: int = 0,
        discovered_from: str | None = None,
    ) -> bool:
        """Idempotently insert a discovered URL. Returns True iff newly inserted."""
        values = {
            "url_hash": url_hash,
            "canonical_url": canonical_url,
            "host": host,
            "status": _enum_value(status),
            "priority": priority,
            "relevance_score": relevance_score,
            "topic_source": _enum_value(topic_source),
            "depth": depth,
            "discovered_from": discovered_from,
        }
        with self.engine.begin() as conn:
            return self._insert_ignore(
                conn, frontier_urls, values,
                index_elements=["url_hash"], returning=frontier_urls.c.id,
            )

    def add_seed(self, seed: FrontierSeed) -> bool:
        """Insert a seed URL and flag its host as a seed host.

        Implements :class:`crawler.seeds.models.SeedSink`. Returns True iff the
        URL was newly inserted (False if it was already present).
        """
        with self.engine.begin() as conn:
            self._flag_seed_host(conn, seed.host)
            return self._insert_ignore(
                conn,
                frontier_urls,
                {
                    "url_hash": seed.url_hash,
                    "canonical_url": seed.canonical_url,
                    "host": seed.host,
                    "status": FrontierStatus.QUEUED.value,
                    "priority": SEED_PRIORITY,
                    "relevance_score": SEED_RELEVANCE,
                    "topic_source": TopicSource.SEED.value,
                    "depth": 0,
                },
                index_elements=["url_hash"],
                returning=frontier_urls.c.id,
            )

    def _flag_seed_host(self, conn: sa.Connection, host: str) -> None:
        insert = self._insert(conn.dialect.name)
        stmt = (
            insert(host_state)
            .values(host=host, is_seed=True)
            .on_conflict_do_update(index_elements=["host"], set_={"is_seed": True})
        )
        conn.execute(stmt)

    # --- lookups ---

    def get_by_id(self, url_id: int) -> FrontierUrl | None:
        return self._fetch_one(frontier_urls.c.id == url_id)

    def get_by_hash(self, url_hash: str) -> FrontierUrl | None:
        return self._fetch_one(frontier_urls.c.url_hash == url_hash)

    def _fetch_one(self, where) -> FrontierUrl | None:
        with self.engine.connect() as conn:
            row = conn.execute(sa.select(frontier_urls).where(where)).mappings().first()
        return FrontierUrl.from_row(row) if row is not None else None

    def get_host_state(self, host: str) -> HostState | None:
        with self.engine.connect() as conn:
            row = (
                conn.execute(sa.select(host_state).where(host_state.c.host == host))
                .mappings()
                .first()
            )
        return HostState.from_row(row) if row is not None else None

    # --- updates ---

    def update_status(
        self,
        url_id: int,
        status: FrontierStatus | str,
        *,
        failure_reason: str | None = None,
        content_hash: str | None = None,
        touch_attempt: bool = False,
    ) -> bool:
        """Update a URL's status (and related fields). Returns True iff a row changed."""
        values: dict[str, Any] = {"status": _enum_value(status)}
        if failure_reason is not None:
            values["failure_reason"] = failure_reason
        if content_hash is not None:
            values["content_hash"] = content_hash
        if touch_attempt:
            values["last_attempt_at"] = sa.func.current_timestamp()
        with self.engine.begin() as conn:
            result = conn.execute(
                sa.update(frontier_urls).where(frontier_urls.c.id == url_id).values(**values)
            )
        return result.rowcount > 0

    # --- helpers ---

    def count_urls(self, *, status: FrontierStatus | str | None = None) -> int:
        stmt = sa.select(sa.func.count()).select_from(frontier_urls)
        if status is not None:
            stmt = stmt.where(frontier_urls.c.status == _enum_value(status))
        with self.engine.connect() as conn:
            return int(conn.execute(stmt).scalar_one())


def _enum_value(value: Any) -> Any:
    return value.value if hasattr(value, "value") else value
