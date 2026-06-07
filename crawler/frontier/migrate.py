"""Programmatic access to the frontier's Alembic migrations."""

from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config

# The migrations live inside the package, so they are always present in an
# installed wheel. The repo-root alembic.ini is only used for logging config in
# a dev checkout (it is not packaged).
_MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"
_REPO_ALEMBIC_INI = Path(__file__).resolve().parents[2] / "alembic.ini"


def make_alembic_config(dsn: str) -> Config:
    ini = str(_REPO_ALEMBIC_INI) if _REPO_ALEMBIC_INI.is_file() else None
    cfg = Config(ini)
    # Resolve script_location to the packaged directory rather than relying on
    # the (possibly absent) ini's relative path.
    cfg.set_main_option("script_location", str(_MIGRATIONS_DIR))
    # Pass the DSN via attributes (a plain dict), NOT set_main_option: Alembic's
    # Config uses ConfigParser, which treats '%' as interpolation syntax and
    # would corrupt URL-encoded passwords in Cloud SQL / Secret Manager DSNs.
    cfg.attributes["dsn"] = dsn
    return cfg


def run_migrations(dsn: str, revision: str = "head") -> None:
    """Upgrade the database at ``dsn`` to ``revision`` (default: latest)."""
    command.upgrade(make_alembic_config(dsn), revision)
