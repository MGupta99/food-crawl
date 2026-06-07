"""Engine/DSN helpers for the frontier database.

Production uses Cloud SQL (PostgreSQL) via psycopg3::

    postgresql+psycopg://USER:PASSWORD@HOST:5432/frontier

The DSN is typically assembled from the ``chi-food-<env>-db-connection`` Secret
Manager secret created by the Terraform foundation. For local development, point
``FRONTIER_DSN`` at a Cloud SQL Auth Proxy or a throwaway Postgres.
"""

from __future__ import annotations

import os

import sqlalchemy as sa
from sqlalchemy.engine import Engine

DSN_ENV_VAR = "FRONTIER_DSN"


def make_engine(dsn: str, *, echo: bool = False, **kwargs) -> Engine:
    """Create a SQLAlchemy engine. ``pool_pre_ping`` guards against dropped
    Cloud SQL connections."""
    return sa.create_engine(dsn, echo=echo, pool_pre_ping=True, **kwargs)


def dsn_from_env(env_var: str = DSN_ENV_VAR) -> str:
    dsn = os.environ.get(env_var)
    if not dsn:
        raise RuntimeError(
            f"{env_var} is not set; provide a SQLAlchemy DSN such as "
            "'postgresql+psycopg://user:pass@host:5432/frontier'"
        )
    return dsn


def engine_from_env(env_var: str = DSN_ENV_VAR, **kwargs) -> Engine:
    return make_engine(dsn_from_env(env_var), **kwargs)
