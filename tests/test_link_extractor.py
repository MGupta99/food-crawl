from __future__ import annotations

from crawler.link_extractor import extract_links

BASE = "https://blog.com/dir/post.html"


def _by_url(links):
    return {link.canonical_url: link for link in links}


def test_extracts_and_canonicalizes_relative_and_absolute():
    html = """
    <html><body>
      <a href="/about">About</a>
      <a href="next/page">Next</a>
      <a href="https://other.com/x?utm_source=blog&id=1">Other</a>
    </body></html>
    """
    links = extract_links(html, BASE)
    urls = [link.canonical_url for link in links]
    assert urls == [
        "https://blog.com/about",
        "https://blog.com/dir/next/page",
        "https://other.com/x?id=1",  # tracking param stripped by canonicalizer
    ]


def test_nofollow_detection():
    html = """
      <a href="/a" rel="nofollow">a</a>
      <a href="/b" rel="ugc sponsored">b</a>
      <a href="/c">c</a>
    """
    links = _by_url(extract_links(html, BASE))
    assert links["https://blog.com/a"].nofollow is True
    assert links["https://blog.com/b"].nofollow is True
    assert links["https://blog.com/c"].nofollow is False


def test_dedupe_within_page_collapses_equivalent_urls():
    html = """
      <a href="/page">1</a>
      <a href="/page/">2</a>
      <a href="https://BLOG.com/page#frag">3</a>
    """
    links = extract_links(html, BASE)
    assert len(links) == 1
    assert links[0].canonical_url == "https://blog.com/page"


def test_followed_wins_over_nofollow_when_mixed():
    html = """
      <a href="/x" rel="nofollow">nofollow first</a>
      <a href="/x">followed later</a>
    """
    links = _by_url(extract_links(html, BASE))
    assert links["https://blog.com/x"].nofollow is False


def test_all_nofollow_stays_nofollow():
    html = """
      <a href="/x" rel="nofollow">1</a>
      <a href="/x" rel="nofollow">2</a>
    """
    links = _by_url(extract_links(html, BASE))
    assert links["https://blog.com/x"].nofollow is True


def test_skips_non_http_and_fragment_only():
    html = """
      <a href="mailto:chef@blog.com">email</a>
      <a href="javascript:void(0)">js</a>
      <a href="tel:+13125550000">call</a>
      <a href="#section">jump</a>
      <a href="">empty</a>
      <a href="/real">real</a>
    """
    links = extract_links(html, BASE)
    assert [link.canonical_url for link in links] == ["https://blog.com/real"]


def test_base_href_overrides_document_base():
    html = """
      <head><base href="https://cdn.blog.com/app/"></head>
      <body><a href="img/page">x</a></body>
    """
    links = extract_links(html, BASE)
    assert links[0].canonical_url == "https://cdn.blog.com/app/img/page"


def test_anchor_without_href_ignored():
    html = '<a name="anchor">no href</a><a href="/ok">ok</a>'
    links = extract_links(html, BASE)
    assert [link.canonical_url for link in links] == ["https://blog.com/ok"]


def test_malformed_html_is_tolerated():
    html = '<a href="/a">unclosed <a href="/b" rel=nofollow>second<div><a href="/c">third'
    links = _by_url(extract_links(html, BASE))
    assert set(links) == {
        "https://blog.com/a",
        "https://blog.com/b",
        "https://blog.com/c",
    }
    assert links["https://blog.com/b"].nofollow is True


def test_host_is_populated():
    links = extract_links('<a href="https://Other.COM/p">x</a>', BASE)
    assert links[0].host == "other.com"


def test_empty_html_returns_no_links():
    assert extract_links("", BASE) == []
