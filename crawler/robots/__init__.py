"""Robots.txt compliance and per-host politeness (component 5)."""

from __future__ import annotations

from .parser import RobotsRules, parse_robots, robots_url_for
from .policy import (
    DEFAULT_CRAWL_DELAY_SECONDS,
    DEFAULT_ROBOTS_TTL_SECONDS,
    MAX_CRAWL_DELAY_SECONDS,
    PolitenessDecision,
    PolitenessManager,
    RobotsFetcher,
    RobotsResponse,
)
from .useragent import DEFAULT_USER_AGENT, contact_email, user_agent

__all__ = [
    "RobotsRules",
    "parse_robots",
    "robots_url_for",
    "PolitenessManager",
    "PolitenessDecision",
    "RobotsResponse",
    "RobotsFetcher",
    "DEFAULT_ROBOTS_TTL_SECONDS",
    "DEFAULT_CRAWL_DELAY_SECONDS",
    "MAX_CRAWL_DELAY_SECONDS",
    "DEFAULT_USER_AGENT",
    "user_agent",
    "contact_email",
]
