from __future__ import annotations

import pytest

from crawler.seeds.loader import (
    RawSeed,
    SeedError,
    build_frontier_seeds,
    canonicalize_seed_url,
    insert_seeds,
    load_seeds,
    parse_seed_file,
    url_hash,
)
from crawler.seeds.models import InMemorySeedSink


def test_canonicalize_basic():
    canonical, host = canonicalize_seed_url("https://Chicago.Eater.com/page#frag")
    assert canonical == "https://chicago.eater.com/page"
    assert host == "chicago.eater.com"


def test_canonicalize_defaults_scheme_and_path():
    canonical, host = canonicalize_seed_url("example-chicago-eats.com")
    assert canonical == "https://example-chicago-eats.com/"
    assert host == "example-chicago-eats.com"


def test_canonicalize_strips_default_port_but_keeps_custom():
    assert canonicalize_seed_url("https://host.com:443/")[0] == "https://host.com/"
    assert canonicalize_seed_url("http://host.com:8080/")[0] == "http://host.com:8080/"


@pytest.mark.parametrize("bad", ["", "   ", "ftp://host.com/", "mailto:a@b.com", "https://"])
def test_canonicalize_rejects_bad_urls(bad):
    with pytest.raises(SeedError):
        canonicalize_seed_url(bad)


def test_build_frontier_seeds_sets_seed_metadata():
    seeds = build_frontier_seeds([RawSeed(url="https://chicago.eater.com/", notes="news")])
    assert len(seeds) == 1
    s = seeds[0]
    assert s.is_seed is True
    assert s.topic_source == "seed"
    assert s.depth == 0
    assert s.host == "chicago.eater.com"
    assert s.notes == "news"
    assert s.url_hash == url_hash("https://chicago.eater.com/")


def test_build_frontier_seeds_dedupes_by_canonical_hash():
    seeds = build_frontier_seeds(
        [
            RawSeed(url="https://chicago.eater.com/"),
            RawSeed(url="https://Chicago.Eater.com/#top"),  # canonicalizes identically
        ]
    )
    assert len(seeds) == 1


def test_parse_seed_file_requires_seeds_list(tmp_path):
    bad = tmp_path / "seeds.yaml"
    bad.write_text("not_seeds: []\n", encoding="utf-8")
    with pytest.raises(SeedError):
        parse_seed_file(bad)


def test_parse_seed_file_accepts_strings_and_mappings(tmp_path):
    f = tmp_path / "seeds.yaml"
    f.write_text(
        "seeds:\n"
        "  - https://a-chicago-blog.com/\n"
        "  - url: https://b-chicago-blog.com/\n"
        "    notes: reviews\n",
        encoding="utf-8",
    )
    raw = parse_seed_file(f)
    assert raw[0].url == "https://a-chicago-blog.com/"
    assert raw[1].notes == "reviews"


def test_packaged_seeds_load_and_are_all_seed_rows():
    seeds = load_seeds()
    assert len(seeds) > 0
    assert all(s.is_seed and s.topic_source == "seed" and s.depth == 0 for s in seeds)
    # url_hashes are unique
    assert len({s.url_hash for s in seeds}) == len(seeds)


def test_insert_seeds_is_idempotent_through_sink():
    seeds = load_seeds()
    sink = InMemorySeedSink()

    first = insert_seeds(seeds, sink)
    assert first.inserted == len(seeds)
    assert first.skipped == 0

    second = insert_seeds(seeds, sink)
    assert second.inserted == 0
    assert second.skipped == len(seeds)
    assert len(sink) == len(seeds)
