"""URL leasing: safe concurrent claiming of frontier work."""

from __future__ import annotations

from .manager import (
    DEFAULT_LEASE_SECONDS,
    DEFAULT_MAX_RETRIES,
    DEFAULT_RETRY_DELAY_SECONDS,
    LeaseManager,
)

__all__ = [
    "LeaseManager",
    "DEFAULT_LEASE_SECONDS",
    "DEFAULT_MAX_RETRIES",
    "DEFAULT_RETRY_DELAY_SECONDS",
]
