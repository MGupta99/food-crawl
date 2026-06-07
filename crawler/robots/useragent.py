"""Crawler user-agent string.

A descriptive User-Agent with a contact address is required for polite crawling
(per ``plan.md`` and the Robots Exclusion Protocol's spirit). The contact email
is sourced from the ``CRAWLER_CONTACT_EMAIL`` environment variable, which in
production is populated from the ``chi-food-<env>-crawler-contact`` Secret
Manager secret created by the Terraform foundation.
"""

from __future__ import annotations

import os

PRODUCT = "ChiFoodCrawler"
VERSION = "0.1"
_DEFAULT_CONTACT = "crawler@example.com"
CONTACT_ENV_VAR = "CRAWLER_CONTACT_EMAIL"


def contact_email() -> str:
    return os.environ.get(CONTACT_ENV_VAR) or _DEFAULT_CONTACT


def user_agent(contact: str | None = None) -> str:
    """Return the crawler UA, e.g. ``ChiFoodCrawler/0.1 (+mailto:you@example.com)``."""
    return f"{PRODUCT}/{VERSION} (+mailto:{contact or contact_email()})"


DEFAULT_USER_AGENT = user_agent()
