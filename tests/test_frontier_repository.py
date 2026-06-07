from __future__ import annotations

import pytest
import sqlalchemy as sa
from sqlalchemy.pool import StaticPool

from crawler.frontier.repository import SEED_PRIORITY, FrontierRepository
from crawler.frontier.schema import FrontierStatus
from crawler.seeds.loader import load_seeds, url_hash
from crawler.seeds.models import FrontierSeed, SeedSink


@pytest.fixture
def repo() -> FrontierRepository:
    # A single shared in-memory SQLite connection (StaticPool) so the schema
    # persists across the repository's separate begin()/connect() calls.
    engine = sa.create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    r = FrontierRepository(engine)
    r.create_schema()
    return r


def _seed(url: str = "https://chicago.eater.com/", host: str = "chicago.eater.com") -> FrontierSeed:
    return FrontierSeed(url_hash=url_hash(url), canonical_url=url, host=host)


def test_create_schema_creates_all_tables(repo: FrontierRepository):
    tables = set(sa.inspect(repo.engine).get_table_names())
    assert {"frontier_urls", "host_state", "crawl_runs"} <= tables


def test_add_url_is_idempotent(repo: FrontierRepository):
    kwargs = dict(
        url_hash=url_hash("https://a-blog.com/x"),
        canonical_url="https://a-blog.com/x",
        host="a-blog.com",
    )
    assert repo.add_url(**kwargs) is True
    assert repo.add_url(**kwargs) is False  # ON CONFLICT DO NOTHING
    assert repo.count_urls() == 1


def test_add_url_defaults(repo: FrontierRepository):
    repo.add_url(
        url_hash=url_hash("https://a-blog.com/y"),
        canonical_url="https://a-blog.com/y",
        host="a-blog.com",
    )
    row = repo.get_by_hash(url_hash("https://a-blog.com/y"))
    assert row is not None
    assert row.status == FrontierStatus.QUEUED.value
    assert row.topic_source == "discovered"
    assert row.depth == 0
    assert row.first_seen_at is not None
    assert row.next_fetch_after is not None


def test_add_seed_sets_metadata_and_flags_host(repo: FrontierRepository):
    seed = _seed()
    assert repo.add_seed(seed) is True

    row = repo.get_by_hash(seed.url_hash)
    assert row is not None
    assert row.topic_source == "seed"
    assert row.depth == 0
    assert row.status == FrontierStatus.QUEUED.value
    assert row.priority == SEED_PRIORITY
    assert row.relevance_score == 1.0

    host = repo.get_host_state(seed.host)
    assert host is not None
    assert host.is_seed is True


def test_add_seed_is_idempotent(repo: FrontierRepository):
    seed = _seed()
    assert repo.add_seed(seed) is True
    assert repo.add_seed(seed) is False
    assert repo.count_urls() == 1


def test_repository_satisfies_seed_sink_protocol(repo: FrontierRepository):
    assert isinstance(repo, SeedSink)


def test_insert_packaged_seeds_through_repository(repo: FrontierRepository):
    from crawler.seeds.loader import insert_seeds

    seeds = load_seeds()
    first = insert_seeds(seeds, repo)
    assert first.inserted == len(seeds)
    assert repo.count_urls() == len(seeds)

    # Re-running is a no-op (idempotent).
    second = insert_seeds(seeds, repo)
    assert second.inserted == 0
    assert second.skipped == len(seeds)
    assert repo.count_urls() == len(seeds)


def test_get_by_id_and_missing_lookups(repo: FrontierRepository):
    assert repo.get_by_hash("does-not-exist") is None
    assert repo.get_by_id(99999) is None

    seed = _seed()
    repo.add_seed(seed)
    fetched = repo.get_by_hash(seed.url_hash)
    assert fetched is not None
    assert repo.get_by_id(fetched.id) == fetched


def test_update_status(repo: FrontierRepository):
    seed = _seed()
    repo.add_seed(seed)
    url = repo.get_by_hash(seed.url_hash)
    assert url is not None

    changed = repo.update_status(
        url.id, FrontierStatus.FAILED, failure_reason="timeout", touch_attempt=True
    )
    assert changed is True

    updated = repo.get_by_id(url.id)
    assert updated is not None
    assert updated.status == FrontierStatus.FAILED.value
    assert updated.failure_reason == "timeout"
    assert updated.last_attempt_at is not None

    # Updating a non-existent row reports no change.
    assert repo.update_status(99999, FrontierStatus.FETCHED) is False


def test_count_urls_by_status(repo: FrontierRepository):
    repo.add_url(url_hash=url_hash("u1"), canonical_url="https://h.com/1", host="h.com")
    repo.add_url(url_hash=url_hash("u2"), canonical_url="https://h.com/2", host="h.com")
    assert repo.count_urls() == 2
    assert repo.count_urls(status=FrontierStatus.QUEUED) == 2
    assert repo.count_urls(status=FrontierStatus.FETCHED) == 0
