"""Outbound-link extraction for crawl discovery.

Parses ``<a href>`` anchors from a fetched HTML page and pipes each href through
the :mod:`crawler.canonicalizer`, so discovered links share the frontier's
canonical form and ``url_hash``. Links are de-duplicated within a page.

We use the stdlib :class:`html.parser.HTMLParser` (lenient about malformed
markup, no extra dependency). ``rel`` is parsed for ``nofollow``/``ugc``/
``sponsored`` so the crawler can deprioritize or skip untrusted links; a URL is
only marked nofollow if *every* anchor pointing to it is nofollow.
"""

from __future__ import annotations

from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.parse import urljoin

from crawler.canonicalizer import CanonicalizeError, canonicalize, host_of

# rel tokens that mark a link as untrusted / not an endorsement.
_NOFOLLOW_RELS = frozenset({"nofollow", "ugc", "sponsored"})


@dataclass(frozen=True, slots=True)
class ExtractedLink:
    canonical_url: str
    host: str
    nofollow: bool


class _LinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.base_href: str | None = None
        # (href, nofollow) in document order.
        self.anchors: list[tuple[str, bool]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "base":
            attr = dict(attrs)
            href = (attr.get("href") or "").strip()
            if href and self.base_href is None:  # first <base href> wins
                self.base_href = href
            return
        if tag != "a":
            return
        attr = dict(attrs)
        href = attr.get("href")
        if not href:
            return
        rel_tokens = (attr.get("rel") or "").lower().split()
        nofollow = any(token in _NOFOLLOW_RELS for token in rel_tokens)
        self.anchors.append((href, nofollow))


def extract_links(html: str, base_url: str) -> list[ExtractedLink]:
    """Extract canonical outbound links from ``html`` served at ``base_url``.

    Relative hrefs resolve against the document base (a ``<base href>`` overrides
    ``base_url``). Pure-fragment (``#...``) and non-HTTP hrefs (``mailto:``,
    ``javascript:``, ...) are dropped. The result is de-duplicated by canonical
    URL in first-seen order; a URL is ``nofollow`` only if all its anchors were.
    """
    parser = _LinkParser()
    parser.feed(html)
    parser.close()

    effective_base = urljoin(base_url, parser.base_href) if parser.base_href else base_url

    order: list[str] = []
    nofollow_by_url: dict[str, bool] = {}
    host_by_url: dict[str, str] = {}

    for href, nofollow in parser.anchors:
        stripped = href.strip()
        if not stripped or stripped.startswith("#"):
            continue  # empty or same-page fragment
        try:
            canonical = canonicalize(stripped, base=effective_base)
        except CanonicalizeError:
            continue  # unsupported scheme or malformed
        if canonical not in nofollow_by_url:
            order.append(canonical)
            nofollow_by_url[canonical] = nofollow
            host_by_url[canonical] = host_of(canonical)
        else:
            # A single followed anchor makes the URL followed.
            nofollow_by_url[canonical] = nofollow_by_url[canonical] and nofollow

    return [
        ExtractedLink(canonical_url=url, host=host_by_url[url], nofollow=nofollow_by_url[url])
        for url in order
    ]
