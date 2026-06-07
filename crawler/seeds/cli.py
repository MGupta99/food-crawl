"""Command-line entry point for inspecting seeds and the lexicon.

Usage::

    chi-food-seeds seeds [--file PATH]      # list normalized frontier seeds
    chi-food-seeds lexicon [--file PATH]    # summarize lexicon terms
    chi-food-seeds check [--seeds PATH] [--lexicon PATH]

This is a dev/inspection tool. Inserting seeds into the Cloud SQL frontier is
wired up in component 3 (``crawler/frontier``); here ``seeds`` performs a dry
run through an in-memory sink.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys

from .lexicon import Lexicon
from .loader import insert_seeds, load_seeds
from .models import InMemorySeedSink


def _cmd_seeds(args: argparse.Namespace) -> int:
    seeds = load_seeds(args.file)
    result = insert_seeds(seeds, InMemorySeedSink())
    payload = {
        "total": result.total,
        "inserted": result.inserted,
        "skipped": result.skipped,
        "seeds": [dataclasses.asdict(s) for s in seeds],
    }
    json.dump(payload, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


def _cmd_lexicon(args: argparse.Namespace) -> int:
    lex = Lexicon.load(args.file)
    payload = {
        "num_terms": len(lex),
        "num_geo_terms": len(lex.geo_terms),
        "num_food_terms": len(lex.food_terms),
        "geo_terms": lex.geo_terms,
        "food_terms": lex.food_terms,
    }
    json.dump(payload, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


def _cmd_check(args: argparse.Namespace) -> int:
    seeds = load_seeds(args.seeds)
    lex = Lexicon.load(args.lexicon)
    print(f"OK: {len(seeds)} seed(s) parsed, {len(lex)} lexicon term(s) loaded.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="chi-food-seeds", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p_seeds = sub.add_parser("seeds", help="list normalized frontier seeds (dry run)")
    p_seeds.add_argument("--file", default=None, help="path to seeds.yaml (default: packaged)")
    p_seeds.set_defaults(func=_cmd_seeds)

    p_lex = sub.add_parser("lexicon", help="summarize the topic lexicon")
    p_lex.add_argument("--file", default=None, help="path to lexicon.yaml (default: packaged)")
    p_lex.set_defaults(func=_cmd_lexicon)

    p_check = sub.add_parser("check", help="validate seeds + lexicon parse cleanly")
    p_check.add_argument("--seeds", default=None, help="path to seeds.yaml")
    p_check.add_argument("--lexicon", default=None, help="path to lexicon.yaml")
    p_check.set_defaults(func=_cmd_check)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
