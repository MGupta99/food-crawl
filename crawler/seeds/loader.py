"""Seed file parsing and frontier-seed construction.

Reads ``seeds.yaml`` and produces normalized :class:`FrontierSeed` records
(``is_seed=True``, ``topic_source="seed"``, ``depth=0``) suitable for idempotent
insertion into ``frontier_urls`` via a :class:`SeedSink`.

URL normalization is delegated to :mod:`crawler.canonicalizer` (component 7) so
seeds and discovered links share one canonical form and ``url_hash``.
"""

from __future__ import annotations

from dataclasses import dataclass
from importlib import resources
from pathlib import Path

import yaml

from crawler.canonicalizer import CanonicalizeError, canonicalize_with_host, url_hash

from .models import FrontierSeed, SeedLoadResult, SeedSink

__all__ = [
    "RawSeed",
    "SeedError",
    "url_hash",
    "canonicalize_seed_url",
    "parse_seed_file",
    "build_frontier_seeds",
    "load_seeds",
    "insert_seeds",
]

_DEFAULT_RESOURCE = "seeds.yaml"


class SeedError(ValueError):
    """Raised when a seed entry is malformed or uses an unsupported scheme."""


@dataclass(frozen=True, slots=True)
class RawSeed:
    url: str
    notes: str | None = None


def canonicalize_seed_url(raw_url: str) -> tuple[str, str]:
    """Return ``(canonical_url, host)`` for a seed URL.

    Thin wrapper over :func:`crawler.canonicalizer.canonicalize_with_host` that
    re-raises canonicalization failures as :class:`SeedError`.
    """
    if raw_url is None:
        raise SeedError("seed url is missing")
    try:
        return canonicalize_with_host(raw_url)
    except CanonicalizeError as exc:
        raise SeedError(str(exc)) from exc


def parse_seed_file(path: str | Path | None = None) -> list[RawSeed]:
    """Parse ``seeds.yaml`` into raw entries (no normalization)."""
    if path is None:
        text = resources.files(__package__).joinpath(_DEFAULT_RESOURCE).read_text("utf-8")
    else:
        text = Path(path).read_text("utf-8")

    data = yaml.safe_load(text) or {}
    raw_seeds = data.get("seeds")
    if raw_seeds is None:
        raise SeedError("seed file must contain a top-level 'seeds' list")
    if not isinstance(raw_seeds, list):
        raise SeedError("'seeds' must be a list")

    parsed: list[RawSeed] = []
    for i, entry in enumerate(raw_seeds):
        if isinstance(entry, str):
            parsed.append(RawSeed(url=entry))
        elif isinstance(entry, dict):
            if "url" not in entry:
                raise SeedError(f"seed entry #{i} is missing 'url'")
            url = entry["url"]
            # Don't coerce: a YAML `url: null` or numeric value must not silently
            # become the string "None"/"123" and canonicalize to e.g. https://none/.
            if not isinstance(url, str):
                raise SeedError(
                    f"seed entry #{i} 'url' must be a string, got {type(url).__name__}"
                )
            parsed.append(RawSeed(url=url, notes=entry.get("notes")))
        else:
            raise SeedError(f"seed entry #{i} must be a string or mapping")
    return parsed


def build_frontier_seeds(raw_seeds: list[RawSeed]) -> list[FrontierSeed]:
    """Normalize raw seeds into :class:`FrontierSeed` rows, deduped by ``url_hash``."""
    seen: set[str] = set()
    seeds: list[FrontierSeed] = []
    for raw in raw_seeds:
        canonical, host = canonicalize_seed_url(raw.url)
        h = url_hash(canonical)
        if h in seen:
            continue
        seen.add(h)
        seeds.append(
            FrontierSeed(
                url_hash=h,
                canonical_url=canonical,
                host=host,
                is_seed=True,
                topic_source="seed",
                depth=0,
                notes=raw.notes,
            )
        )
    return seeds


def load_seeds(path: str | Path | None = None) -> list[FrontierSeed]:
    """Parse and normalize the seed file in one step."""
    return build_frontier_seeds(parse_seed_file(path))


def insert_seeds(seeds: list[FrontierSeed], sink: SeedSink) -> SeedLoadResult:
    """Insert seeds through a :class:`SeedSink`, counting inserted vs. skipped."""
    result = SeedLoadResult(seeds=list(seeds))
    for seed in seeds:
        if sink.add_seed(seed):
            result.inserted += 1
        else:
            result.skipped += 1
    return result
