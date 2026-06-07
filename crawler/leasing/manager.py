"""URL leasing.

Workers never pop work directly; they *lease* a batch of URLs from the frontier.
A lease atomically claims the highest-priority eligible rows and marks them
``fetching`` with an expiry, so a crashed worker's URLs become re-leasable.

On PostgreSQL the claim uses ``SELECT ... FOR UPDATE SKIP LOCKED`` so concurrent
workers never grab the same rows. SQLite (used in tests) lacks ``SKIP LOCKED``
but serializes write transactions, which gives the same no-double-lease
guarantee; SQLAlchemy simply omits the clause there.

All time math is done server-side (dialect-aware) to avoid worker clock skew.
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.engine import Engine

from crawler.frontier.models import FrontierUrl
from crawler.frontier.schema import FrontierStatus, frontier_urls

DEFAULT_LEASE_SECONDS = 300  # 5 minutes (per plan.md)
DEFAULT_MAX_RETRIES = 3
DEFAULT_RETRY_DELAY_SECONDS = 300


def _now(dialect: str):
    if dialect == "postgresql":
        return sa.func.now()
    if dialect == "sqlite":
        return sa.func.current_timestamp()
    raise NotImplementedError(f"unsupported dialect: {dialect!r}")


def _plus_seconds(dialect: str, seconds: int):
    seconds = int(seconds)  # guard: interpolated into the interval literal
    if dialect == "postgresql":
        return sa.func.now() + sa.literal_column(f"interval '{seconds} seconds'")
    if dialect == "sqlite":
        return sa.func.datetime(sa.func.current_timestamp(), f"+{seconds} seconds")
    raise NotImplementedError(f"unsupported dialect: {dialect!r}")


class LeaseManager:
    """Leases URLs from the frontier and records fetch outcomes."""

    def __init__(
        self,
        engine: Engine,
        *,
        lease_seconds: int = DEFAULT_LEASE_SECONDS,
        max_retries: int = DEFAULT_MAX_RETRIES,
        retry_delay_seconds: int = DEFAULT_RETRY_DELAY_SECONDS,
    ) -> None:
        self.engine = engine
        self.lease_seconds = lease_seconds
        self.max_retries = max_retries
        self.retry_delay_seconds = retry_delay_seconds

    @property
    def _dialect(self) -> str:
        return self.engine.dialect.name

    def lease(self, batch: int = 100) -> list[FrontierUrl]:
        """Atomically claim up to ``batch`` eligible URLs, marking them fetching.

        Eligible = due (``next_fetch_after <= now``) and either ``queued`` or a
        ``fetching`` row whose lease has expired (so abandoned work is retried).
        """
        dialect = self._dialect
        now = _now(dialect)
        eligible = (
            sa.select(frontier_urls.c.id)
            .where(
                frontier_urls.c.next_fetch_after <= now,
                sa.or_(
                    frontier_urls.c.status == FrontierStatus.QUEUED.value,
                    sa.and_(
                        frontier_urls.c.status == FrontierStatus.FETCHING.value,
                        frontier_urls.c.lease_expires_at < now,
                    ),
                ),
            )
            .order_by(
                frontier_urls.c.priority.desc(),
                frontier_urls.c.relevance_score.desc(),
                frontier_urls.c.id.asc(),
            )
            .limit(batch)
            .with_for_update(skip_locked=True)
        )
        stmt = (
            sa.update(frontier_urls)
            .where(frontier_urls.c.id.in_(eligible))
            .values(
                status=FrontierStatus.FETCHING.value,
                lease_expires_at=_plus_seconds(dialect, self.lease_seconds),
                last_attempt_at=_now(dialect),
            )
            .returning(frontier_urls)
        )
        with self.engine.begin() as conn:
            rows = conn.execute(stmt).mappings().all()
        return [FrontierUrl.from_row(r) for r in rows]

    def reclaim_expired_leases(self) -> int:
        """Return abandoned (expired) leases to the queue. Returns rows reclaimed."""
        dialect = self._dialect
        stmt = (
            sa.update(frontier_urls)
            .where(
                frontier_urls.c.status == FrontierStatus.FETCHING.value,
                frontier_urls.c.lease_expires_at < _now(dialect),
            )
            .values(status=FrontierStatus.QUEUED.value, lease_expires_at=None)
        )
        with self.engine.begin() as conn:
            return conn.execute(stmt).rowcount

    def complete_fetch(self, url_id: int, *, content_hash: str | None = None) -> bool:
        """Mark a leased URL fetched. Returns True iff the row existed."""
        values: dict = {"status": FrontierStatus.FETCHED.value, "lease_expires_at": None}
        if content_hash is not None:
            values["content_hash"] = content_hash
        with self.engine.begin() as conn:
            result = conn.execute(
                sa.update(frontier_urls).where(frontier_urls.c.id == url_id).values(**values)
            )
        return result.rowcount > 0

    def mark_failed(self, url_id: int, reason: str, *, retry: bool = True) -> bool:
        """Record a failed fetch.

        If ``retry`` and the URL is under ``max_retries``, it is requeued with an
        incremented ``retry_count`` and a delayed ``next_fetch_after``; otherwise
        it is marked permanently ``failed``. Returns True iff the row existed.
        """
        dialect = self._dialect
        with self.engine.begin() as conn:
            retry_count = conn.execute(
                sa.select(frontier_urls.c.retry_count).where(frontier_urls.c.id == url_id)
            ).scalar_one_or_none()
            if retry_count is None:
                return False

            if retry and retry_count < self.max_retries:
                values: dict = {
                    "status": FrontierStatus.QUEUED.value,
                    "retry_count": retry_count + 1,
                    "failure_reason": reason,
                    "lease_expires_at": None,
                    "next_fetch_after": _plus_seconds(dialect, self.retry_delay_seconds),
                }
            else:
                values = {
                    "status": FrontierStatus.FAILED.value,
                    "failure_reason": reason,
                    "lease_expires_at": None,
                }
            conn.execute(
                sa.update(frontier_urls).where(frontier_urls.c.id == url_id).values(**values)
            )
        return True
