"""CLI for managing the URL frontier database.

Usage::

    chi-food-frontier migrate                 # create the frontier schema
    chi-food-frontier load-seeds [--file ...]  # load seeds into the frontier
    chi-food-frontier stats                   # print frontier counts

All commands need a database; pass --dsn or set FRONTIER_DSN.
"""

from __future__ import annotations

import argparse
import json
import sys

from crawler.seeds.loader import insert_seeds, load_seeds

from .engine import DSN_ENV_VAR, dsn_from_env, make_engine
from .migrate import run_migrations
from .repository import FrontierRepository
from .schema import FrontierStatus


def _repo(args: argparse.Namespace) -> FrontierRepository:
    dsn = args.dsn or dsn_from_env()
    return FrontierRepository(make_engine(dsn))


def _cmd_migrate(args: argparse.Namespace) -> int:
    dsn = args.dsn or dsn_from_env()
    run_migrations(dsn, args.revision)
    print(f"Frontier schema migrated to '{args.revision}'.")
    return 0


def _cmd_load_seeds(args: argparse.Namespace) -> int:
    repo = _repo(args)
    seeds = load_seeds(args.file)
    result = insert_seeds(seeds, repo)
    print(
        f"Seeds: {result.total} processed, {result.inserted} inserted, "
        f"{result.skipped} already present."
    )
    return 0


def _cmd_stats(args: argparse.Namespace) -> int:
    repo = _repo(args)
    payload = {
        "total": repo.count_urls(),
        "by_status": {s.value: repo.count_urls(status=s) for s in FrontierStatus},
    }
    json.dump(payload, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="chi-food-frontier", description=__doc__)
    parser.add_argument(
        "--dsn",
        default=None,
        help=f"SQLAlchemy DSN (default: ${DSN_ENV_VAR})",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_migrate = sub.add_parser("migrate", help="apply alembic migrations (upgrade head)")
    p_migrate.add_argument("--revision", default="head", help="target revision (default: head)")
    p_migrate.set_defaults(func=_cmd_migrate)

    p_seeds = sub.add_parser("load-seeds", help="load seeds into the frontier")
    p_seeds.add_argument("--file", default=None, help="path to seeds.yaml (default: packaged)")
    p_seeds.set_defaults(func=_cmd_load_seeds)

    p_stats = sub.add_parser("stats", help="print frontier counts")
    p_stats.set_defaults(func=_cmd_stats)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
