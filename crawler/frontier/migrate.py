"""Programmatic access to the frontier's Alembic migrations."""

from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config

ALEMBIC_INI = Path(__file__).resolve().parents[2] / "alembic.ini"


def make_alembic_config(dsn: str) -> Config:
    cfg = Config(str(ALEMBIC_INI))
    cfg.set_main_option("sqlalchemy.url", dsn)
    return cfg


def run_migrations(dsn: str, revision: str = "head") -> None:
    """Upgrade the database at ``dsn`` to ``revision`` (default: latest)."""
    command.upgrade(make_alembic_config(dsn), revision)
