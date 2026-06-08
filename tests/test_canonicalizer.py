from __future__ import annotations

import pytest

from crawler.canonicalizer import (
    CanonicalizeError,
    canonicalize,
    canonicalize_with_host,
    host_of,
    url_hash,
)


def test_lowercases_scheme_and_host_strips_fragment():
    assert canonicalize("HTTPS://Chicago.Eater.com/Page#section") == "https://chicago.eater.com/Page"


def test_path_case_preserved():
    # Host is case-insensitive; path is not.
    assert canonicalize("https://h.com/Foo/Bar") == "https://h.com/Foo/Bar"


def test_default_scheme_for_schemeless():
    assert canonicalize("example-chicago-eats.com") == "https://example-chicago-eats.com/"


def test_default_ports_dropped_custom_kept():
    assert canonicalize("https://h.com:443/") == "https://h.com/"
    assert canonicalize("http://h.com:80/") == "http://h.com/"
    assert canonicalize("http://h.com:8080/x") == "http://h.com:8080/x"


def test_userinfo_dropped():
    assert canonicalize("https://user:pass@h.com/x") == "https://h.com/x"


def test_trailing_slash_removed_except_root():
    assert canonicalize("https://h.com/") == "https://h.com/"
    assert canonicalize("https://h.com/section/") == "https://h.com/section"
    assert canonicalize("https://h.com/a/b/") == "https://h.com/a/b"


def test_dot_segments_resolved():
    assert canonicalize("https://h.com/a/./b/../c") == "https://h.com/a/c"
    assert canonicalize("https://h.com/../../etc") == "https://h.com/etc"


def test_duplicate_slashes_collapsed():
    assert canonicalize("https://h.com/a//b///c") == "https://h.com/a/b/c"


def test_percent_encoding_uppercased():
    assert canonicalize("https://h.com/a%2fb%3dc") == "https://h.com/a%2Fb%3Dc"


def test_relative_resolution_against_base():
    base = "https://h.com/dir/page.html"
    assert canonicalize("../other", base=base) == "https://h.com/other"
    assert canonicalize("sub/leaf", base=base) == "https://h.com/dir/sub/leaf"
    assert canonicalize("/abs", base=base) == "https://h.com/abs"


def test_protocol_relative_resolution():
    assert canonicalize("//cdn.h.com/x", base="https://h.com/p") == "https://cdn.h.com/x"
    # Without a base, default to https.
    assert canonicalize("//cdn.h.com/x") == "https://cdn.h.com/x"


def test_tracking_params_stripped():
    url = "https://h.com/post?utm_source=tw&utm_medium=social&id=5&fbclid=abc"
    assert canonicalize(url) == "https://h.com/post?id=5"


def test_query_params_sorted_for_stability():
    a = canonicalize("https://h.com/p?b=2&a=1&c=3")
    b = canonicalize("https://h.com/p?c=3&a=1&b=2")
    assert a == b == "https://h.com/p?a=1&b=2&c=3"


def test_query_can_be_left_unsorted_and_tracking_kept():
    url = "https://h.com/p?utm_source=x&b=2&a=1"
    out = canonicalize(url, strip_tracking=False, sort_query=False)
    assert out == "https://h.com/p?utm_source=x&b=2&a=1"


def test_equivalent_urls_canonicalize_identically():
    forms = [
        "https://Chicago.Eater.com/maps/#frag",
        "https://chicago.eater.com:443/maps/",
        "https://chicago.eater.com/maps",
        "HTTPS://chicago.eater.com/maps/./",
    ]
    canonized = {canonicalize(u) for u in forms}
    assert len(canonized) == 1
    assert canonized == {"https://chicago.eater.com/maps"}


@pytest.mark.parametrize(
    "bad",
    [
        "",
        "   ",
        "mailto:a@b.com",
        "javascript:alert(1)",
        "tel:+13125551234",
        "data:text/plain,hi",
        "ftp://h.com/f",
        "https://",
    ],
)
def test_rejects_unsupported_or_invalid(bad):
    with pytest.raises(CanonicalizeError):
        canonicalize(bad)


def test_canonicalize_with_host():
    canonical, host = canonicalize_with_host("https://Chicago.Eater.com/x/")
    assert canonical == "https://chicago.eater.com/x"
    assert host == "chicago.eater.com"


def test_host_of_and_url_hash_stability():
    canonical = canonicalize("https://h.com/p?a=1")
    assert host_of(canonical) == "h.com"
    assert url_hash(canonical) == url_hash("https://h.com/p?a=1")
    assert len(url_hash(canonical)) == 64
