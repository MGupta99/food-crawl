from __future__ import annotations

import threading
from datetime import datetime

import pytest
import sqlalchemy as sa
from sqlalchemy.pool import StaticPool

from crawler.frontier.repository import FrontierRepository
from crawler.frontier.schema import FrontierStatus, frontier_urls
from crawler.leasing.manager import LeaseManager
from crawler.seeds.loader import url_hash


@pytest.fixture
def engine() -> sa.Engine:
    eng = sa.create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    FrontierRepository(eng).create_schema()
    return eng


@pytest.fixture
def repo(engine: sa.Engine) -> FrontierRepository:
    return FrontierRepository(engine)


def _add(repo: FrontierRepository, key: str, *, priority: int = 0, relevance: float = 0.0) -> None:
    repo.add_url(
        url_hash=url_hash(key),
        canonical_url=f"https://h.com/{key}",
        host="h.com",
        priority=priority,
        relevance_score=relevance,
    )


def _set(engine: sa.Engine, key: str, **values) -> None:
    with engine.begin() as conn:
        conn.execute(
            sa.update(frontier_urls)
            .where(frontier_urls.c.url_hash == url_hash(key))
            .values(**values)
        )


def _row(repo: FrontierRepository, key: str):
    return repo.get_by_hash(url_hash(key))


def test_lease_marks_rows_fetching_with_expiry(engine, repo):
    _add(repo, "a")
    leased = LeaseManager(engine).lease()
    assert len(leased) == 1
    assert leased[0].status == FrontierStatus.FETCHING.value
    assert leased[0].lease_expires_at is not None
    assert leased[0].last_attempt_at is not None
    assert _row(repo, "a").status == FrontierStatus.FETCHING.value


def test_lease_picks_highest_priority_first(engine, repo):
    for i in range(1, 6):
        _add(repo, f"p{i}", priority=i)
    leased = LeaseManager(engine).lease(batch=2)
    leased_priorities = {u.priority for u in leased}
    assert leased_priorities == {5, 4}  # ORDER BY priority DESC LIMIT 2


def test_lease_does_not_return_already_leased(engine, repo):
    for i in range(3):
        _add(repo, f"u{i}")
    mgr = LeaseManager(engine)
    first = mgr.lease(batch=2)
    second = mgr.lease(batch=2)
    first_ids = {u.id for u in first}
    second_ids = {u.id for u in second}
    assert len(first) == 2
    assert len(second) == 1  # only one left un-leased
    assert first_ids.isdisjoint(second_ids)


def test_lease_empty_when_nothing_eligible(engine, repo):
    assert LeaseManager(engine).lease() == []


def test_lease_skips_future_next_fetch_after(engine, repo):
    _add(repo, "future")
    _set(engine, "future", next_fetch_after=datetime(2099, 1, 1))
    assert LeaseManager(engine).lease() == []


def test_expired_lease_is_re_leasable(engine, repo):
    _add(repo, "x")
    mgr = LeaseManager(engine)
    leased = mgr.lease()
    assert len(leased) == 1
    # Simulate a crashed worker: lease already expired.
    _set(engine, "x", lease_expires_at=datetime(2000, 1, 1))
    re_leased = mgr.lease()
    assert len(re_leased) == 1
    assert re_leased[0].id == leased[0].id


def test_reclaim_expired_leases(engine, repo):
    _add(repo, "x")
    mgr = LeaseManager(engine)
    mgr.lease()
    _set(engine, "x", lease_expires_at=datetime(2000, 1, 1))

    assert mgr.reclaim_expired_leases() == 1
    assert _row(repo, "x").status == FrontierStatus.QUEUED.value
    assert _row(repo, "x").lease_expires_at is None
    # Nothing left to reclaim.
    assert mgr.reclaim_expired_leases() == 0


def test_complete_fetch_sets_fetched_and_content_hash(engine, repo):
    _add(repo, "x")
    mgr = LeaseManager(engine)
    leased = mgr.lease()[0]

    assert mgr.complete_fetch(leased.id, content_hash="sha256:abc") is True
    row = repo.get_by_id(leased.id)
    assert row.status == FrontierStatus.FETCHED.value
    assert row.content_hash == "sha256:abc"
    assert row.lease_expires_at is None

    assert mgr.complete_fetch(99999) is False


def test_mark_failed_requeues_until_max_retries(engine, repo):
    _add(repo, "x")
    mgr = LeaseManager(engine, max_retries=2)
    leased = mgr.lease()[0]

    assert mgr.mark_failed(leased.id, "boom", retry=True) is True
    row = repo.get_by_id(leased.id)
    assert row.status == FrontierStatus.QUEUED.value
    assert row.retry_count == 1
    assert row.failure_reason == "boom"
    assert row.lease_expires_at is None


def test_mark_failed_terminal_when_retries_exhausted(engine, repo):
    _add(repo, "x")
    mgr = LeaseManager(engine, max_retries=0)
    leased = mgr.lease()[0]

    assert mgr.mark_failed(leased.id, "fatal", retry=True) is True
    assert repo.get_by_id(leased.id).status == FrontierStatus.FAILED.value


def test_mark_failed_no_retry_marks_failed(engine, repo):
    _add(repo, "x")
    mgr = LeaseManager(engine, max_retries=5)
    leased = mgr.lease()[0]
    assert mgr.mark_failed(leased.id, "stop", retry=False) is True
    assert repo.get_by_id(leased.id).status == FrontierStatus.FAILED.value


def test_mark_failed_missing_row_returns_false(engine, repo):
    assert LeaseManager(engine).mark_failed(99999, "nope") is False


def test_no_double_lease_under_concurrent_workers(tmp_path):
    # Real threads against a file-backed SQLite. SQLite serializes write
    # transactions (busy timeout avoids 'database is locked'), so each URL must
    # be leased by exactly one worker.
    dsn = f"sqlite:///{tmp_path / 'lease.db'}"
    engine = sa.create_engine(dsn, connect_args={"check_same_thread": False, "timeout": 30})
    repo = FrontierRepository(engine)
    repo.create_schema()

    total = 200
    for i in range(total):
        _add(repo, f"u{i}")

    leased_by_thread: list[list[int]] = []
    lock = threading.Lock()

    def worker() -> None:
        mine: list[int] = []
        mgr = LeaseManager(engine)
        while True:
            batch = mgr.lease(batch=7)
            if not batch:
                break
            mine.extend(u.id for u in batch)
        with lock:
            leased_by_thread.append(mine)

    threads = [threading.Thread(target=worker) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    all_ids = [i for mine in leased_by_thread for i in mine]
    assert len(all_ids) == total  # every URL leased
    assert len(set(all_ids)) == total  # and none leased twice
    assert repo.count_urls(status=FrontierStatus.FETCHING) == total
