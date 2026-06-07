"""Data models for seed loading.

These describe seed rows destined for the ``frontier_urls`` table. The concrete
Cloud SQL repository is implemented in ``crawler/frontier`` (component 3); seed
loading depends only on the :class:`SeedSink` protocol so it can be developed and
tested independently.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


@dataclass(frozen=True, slots=True)
class FrontierSeed:
    """A normalized seed ready to insert into ``frontier_urls``."""

    url_hash: str
    canonical_url: str
    host: str
    is_seed: bool = True
    topic_source: str = "seed"
    depth: int = 0
    notes: str | None = None


@runtime_checkable
class SeedSink(Protocol):
    """Destination for seed rows.

    Implementations insert into ``frontier_urls`` idempotently (``ON CONFLICT
    (url_hash) DO NOTHING``) and return ``True`` when a new row was inserted,
    ``False`` when the URL was already present.
    """

    def add_seed(self, seed: FrontierSeed) -> bool: ...


@dataclass
class SeedLoadResult:
    """Outcome of inserting a batch of seeds through a :class:`SeedSink`."""

    inserted: int = 0
    skipped: int = 0
    seeds: list[FrontierSeed] = field(default_factory=list)

    @property
    def total(self) -> int:
        return self.inserted + self.skipped


class InMemorySeedSink:
    """In-memory :class:`SeedSink` for local development and tests."""

    def __init__(self) -> None:
        self.by_hash: dict[str, FrontierSeed] = {}

    def add_seed(self, seed: FrontierSeed) -> bool:
        if seed.url_hash in self.by_hash:
            return False
        self.by_hash[seed.url_hash] = seed
        return True

    def __len__(self) -> int:
        return len(self.by_hash)
