"""URL canonicalization (component 7)."""

from __future__ import annotations

from .canonicalizer import (
    ALLOWED_SCHEMES,
    TRACKING_PARAMS,
    CanonicalizeError,
    canonicalize,
    canonicalize_with_host,
    host_of,
    url_hash,
)

__all__ = [
    "canonicalize",
    "canonicalize_with_host",
    "host_of",
    "url_hash",
    "CanonicalizeError",
    "ALLOWED_SCHEMES",
    "TRACKING_PARAMS",
]
