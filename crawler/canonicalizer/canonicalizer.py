"""URL canonicalization.

Produces a single canonical form per logical resource so the frontier's
``url_hash`` dedup and idempotency work, and so a seed URL and the same URL
later discovered as a link collapse to one entry. This is the authoritative
implementation; :mod:`crawler.seeds.loader` delegates to it.

Normalization (deliberately dedup-oriented):

* resolve relative URLs against a base (``urljoin``);
* require ``http``/``https`` -- ``mailto:``/``javascript:``/``tel:``/``data:``/
  ``ftp:`` and friends are rejected;
* lowercase scheme and host, drop userinfo and default ports (80/443);
* drop the fragment;
* normalize the path: resolve ``.``/``..`` and duplicate slashes, uppercase
  percent-encoding, and strip a trailing slash except on root (``/``);
* normalize the query: drop tracking params (``utm_*``, ``gclid``, ``fbclid``,
  ...), then sort the remaining params for a stable ordering.

These last two are stricter than RFC 3986 equivalence but materially improve
deduplication, which is a core goal of the corpus pipeline.
"""

from __future__ import annotations

import hashlib
import posixpath
import re
from urllib.parse import (
    parse_qsl,
    urlencode,
    urljoin,
    urlsplit,
    urlunsplit,
)

ALLOWED_SCHEMES = frozenset({"http", "https"})
_DEFAULT_PORTS = {"http": 80, "https": 443}
_PCT = re.compile(r"%[0-9a-fA-F]{2}")
_LEADING_SLASHES = re.compile(r"^/+")

# Common analytics/click tracking params that don't affect content identity.
TRACKING_PARAMS = frozenset(
    {
        "gclid",
        "fbclid",
        "msclkid",
        "yclid",
        "dclid",
        "mc_cid",
        "mc_eid",
        "igshid",
        "ref",
        "ref_src",
        "ref_url",
        "_ga",
        "_gl",
        "spm",
        "vero_id",
    }
)


class CanonicalizeError(ValueError):
    """Raised when a URL is malformed or uses an unsupported scheme."""


def canonicalize(
    url: str,
    base: str | None = None,
    *,
    strip_tracking: bool = True,
    sort_query: bool = True,
) -> str:
    """Return the canonical form of ``url`` (optionally resolved against ``base``).

    Raises :class:`CanonicalizeError` for empty input, missing host, or an
    unsupported scheme.
    """
    if url is None:
        raise CanonicalizeError("url is missing")
    raw = url.strip()
    if not raw:
        raise CanonicalizeError("url is empty")

    if base:
        raw = urljoin(base, raw)

    parts = urlsplit(raw)
    scheme = parts.scheme.lower()
    if scheme == "":
        # No scheme: protocol-relative ("//host/..") keeps its netloc; otherwise
        # treat the whole string as a host-relative authority. Default to https.
        prefix = "https:" if raw.startswith("//") else "https://"
        parts = urlsplit(prefix + raw)
        scheme = parts.scheme.lower()

    if scheme not in ALLOWED_SCHEMES:
        raise CanonicalizeError(f"unsupported scheme {scheme!r} in {url!r}")

    host = (parts.hostname or "").lower()
    if not host:
        raise CanonicalizeError(f"url has no host: {url!r}")

    netloc = host
    if parts.port is not None and parts.port != _DEFAULT_PORTS[scheme]:
        netloc = f"{host}:{parts.port}"

    path = _normalize_path(parts.path)
    query = _normalize_query(parts.query, strip_tracking=strip_tracking, sort_query=sort_query)
    return urlunsplit((scheme, netloc, path, query, ""))


def canonicalize_with_host(url: str, base: str | None = None, **kwargs) -> tuple[str, str]:
    """Canonicalize and also return the (lowercased) host."""
    canonical = canonicalize(url, base, **kwargs)
    return canonical, host_of(canonical)


def host_of(url: str) -> str:
    return (urlsplit(url).hostname or "").lower()


def url_hash(canonical_url: str) -> str:
    """Stable content-addressed id for a canonical URL (sha256 hex)."""
    return hashlib.sha256(canonical_url.encode("utf-8")).hexdigest()


def _upper_percent(s: str) -> str:
    return _PCT.sub(lambda m: m.group(0).upper(), s)


def _normalize_path(path: str) -> str:
    if not path:
        return "/"
    collapsed = _LEADING_SLASHES.sub("/", path)
    # posixpath.normpath resolves "." / ".." / duplicate slashes and drops any
    # trailing slash; it never escapes above root for absolute paths.
    normalized = posixpath.normpath(collapsed)
    if normalized == ".":
        normalized = "/"
    if not normalized.startswith("/"):
        normalized = "/" + normalized
    return _upper_percent(normalized)


def _normalize_query(query: str, *, strip_tracking: bool, sort_query: bool) -> str:
    if not query:
        return ""
    pairs = parse_qsl(query, keep_blank_values=True)
    if strip_tracking:
        pairs = [
            (k, v)
            for (k, v) in pairs
            if k.lower() not in TRACKING_PARAMS and not k.lower().startswith("utm_")
        ]
    if sort_query:
        pairs = sorted(pairs)
    return urlencode(pairs)
