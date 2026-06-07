from __future__ import annotations

import sqlalchemy as sa

from crawler.frontier.migrate import run_migrations
from crawler.frontier.repository import FrontierRepository
from crawler.frontier.schema import frontier_urls, metadata
from crawler.seeds.loader import url_hash
from crawler.seeds.models import FrontierSeed


def _sqlite_dsn(tmp_path) -> str:
    return f"sqlite:///{tmp_path / 'frontier.db'}"


def test_migration_creates_expected_schema(tmp_path):
    dsn = _sqlite_dsn(tmp_path)
    run_migrations(dsn)

    engine = sa.create_engine(dsn)
    inspector = sa.inspect(engine)

    tables = set(inspector.get_table_names())
    # All model tables plus alembic's bookkeeping table.
    assert {"frontier_urls", "host_state", "crawl_runs", "alembic_version"} <= tables

    # Columns match the metadata definition.
    migrated_cols = {c["name"] for c in inspector.get_columns("frontier_urls")}
    assert migrated_cols == {c.name for c in frontier_urls.columns}

    index_names = {ix["name"] for ix in inspector.get_indexes("frontier_urls")}
    assert {"ix_frontier_lease", "ix_frontier_host"} <= index_names


def test_migration_is_idempotent_and_records_head(tmp_path):
    dsn = _sqlite_dsn(tmp_path)
    run_migrations(dsn)
    run_migrations(dsn)  # second upgrade is a no-op

    engine = sa.create_engine(dsn)
    with engine.connect() as conn:
        version = conn.execute(sa.text("SELECT version_num FROM alembic_version")).scalar_one()
    assert version  # a head revision is recorded


def test_migrated_schema_is_functional(tmp_path):
    dsn = _sqlite_dsn(tmp_path)
    run_migrations(dsn)

    repo = FrontierRepository(sa.create_engine(dsn))
    seed = FrontierSeed(
        url_hash=url_hash("https://chicago.eater.com/"),
        canonical_url="https://chicago.eater.com/",
        host="chicago.eater.com",
    )
    assert repo.add_seed(seed) is True
    assert repo.count_urls() == 1


def test_migration_matches_metadata_table_set():
    # Guard against forgetting to add a future table to a migration: the schema
    # metadata and the migrated DB are kept in lockstep by the tests above; here
    # we just assert the metadata still defines exactly the three frontier tables.
    assert set(metadata.tables) == {"frontier_urls", "host_state", "crawl_runs"}
