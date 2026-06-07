"""Alembic environment for the URL frontier.

The target schema is ``crawler.frontier.schema.metadata`` (the single source of
truth). The database URL is resolved, in order, from:

1. the ``sqlalchemy.url`` main option (set programmatically by the
   ``chi-food-frontier migrate`` CLI), then
2. the ``FRONTIER_DSN`` environment variable.

``alembic.ini`` intentionally does not hardcode a URL.
"""

from __future__ import annotations

import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

from crawler.frontier.schema import metadata

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = metadata

# Detecting column type / server-default changes makes autogenerate useful for
# follow-on revisions.
_CONFIGURE_OPTS = {
    "target_metadata": target_metadata,
    "compare_type": True,
    "compare_server_default": True,
    # Required for batch (ALTER) operations to work on SQLite during local dev.
    "render_as_batch": True,
}


def _resolve_url() -> str:
    # Read from config.attributes (a plain dict set by the CLI) rather than
    # sqlalchemy.url, to avoid ConfigParser '%' interpolation corrupting
    # URL-encoded passwords.
    url = config.attributes.get("dsn")
    if url:
        return url
    url = os.environ.get("FRONTIER_DSN")
    if not url:
        raise RuntimeError(
            "No database URL: set FRONTIER_DSN or pass a DSN to "
            "'chi-food-frontier migrate'."
        )
    return url


def run_migrations_offline() -> None:
    context.configure(
        url=_resolve_url(),
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        **_CONFIGURE_OPTS,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    # Build the engine directly from the resolved URL so the DSN never passes
    # through ConfigParser interpolation.
    connectable = create_engine(_resolve_url(), poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(connection=connection, **_CONFIGURE_OPTS)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
