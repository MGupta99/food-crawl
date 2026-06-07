"""Politeness: robots.txt caching + per-host fetch spacing.

:class:`PolitenessManager` sits between leasing and fetching. It answers two
questions for a leased URL:

* **May we fetch it at all?** -- :meth:`authorize` checks the host's cached
  robots.txt (fetching + caching it in ``host_state`` with a TTL when stale) and
  evaluates the path against the rules for our user-agent.
* **May we fetch it *now*?** -- :meth:`host_ready` enforces per-host spacing via
  ``host_state.next_allowed_fetch_at``; :meth:`note_fetch` advances that window
  after a request, honoring any ``Crawl-delay`` from robots.txt.

Network I/O is injected as a ``RobotsFetcher`` callable so this layer is testable
without sockets and stays decoupled from the HTTP fetcher (component 6). All
timestamps are naive UTC, matching the rest of the frontier.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol

from crawler.frontier.models import HostState
from crawler.frontier.repository import FrontierRepository

from .parser import RobotsRules, parse_robots, robots_url_for
from .useragent import DEFAULT_USER_AGENT

DEFAULT_ROBOTS_TTL_SECONDS = 24 * 60 * 60  # re-fetch robots.txt at most daily
DEFAULT_CRAWL_DELAY_SECONDS = 5  # polite floor when robots.txt is silent
MAX_CRAWL_DELAY_SECONDS = 60  # cap absurd Crawl-delay values


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


@dataclass(frozen=True, slots=True)
class RobotsResponse:
    """Result of fetching a ``robots.txt`` URL."""

    status: int
    text: str | None = None


class RobotsFetcher(Protocol):
    def __call__(self, robots_url: str) -> RobotsResponse: ...


@dataclass(frozen=True, slots=True)
class PolitenessDecision:
    allowed: bool
    reason: str


class PolitenessManager:
    def __init__(
        self,
        repo: FrontierRepository,
        fetcher: RobotsFetcher,
        *,
        user_agent: str = DEFAULT_USER_AGENT,
        robots_ttl_seconds: int = DEFAULT_ROBOTS_TTL_SECONDS,
        default_delay_seconds: int = DEFAULT_CRAWL_DELAY_SECONDS,
        max_delay_seconds: int = MAX_CRAWL_DELAY_SECONDS,
        clock: Callable[[], datetime] = _utcnow,
    ) -> None:
        self.repo = repo
        self.fetcher = fetcher
        self.user_agent = user_agent
        self.robots_ttl_seconds = robots_ttl_seconds
        self.default_delay_seconds = default_delay_seconds
        self.max_delay_seconds = max_delay_seconds
        self._clock = clock

    # --- authorization (path-level robots check) ---

    def authorize(self, canonical_url: str) -> PolitenessDecision:
        """Decide whether ``canonical_url`` may be fetched per robots.txt.

        Refreshes and caches the host's robots.txt when missing or stale. A
        manual ``host_state.allow = false`` kill-switch blocks the whole host. A
        transient robots.txt fetch failure (5xx / network error) yields a
        not-allowed decision *without* caching, so it is retried later.
        """
        host = _host_of(canonical_url)
        if not host:
            return PolitenessDecision(False, "url has no host")

        state = self.repo.get_host_state(host)
        if state is not None and not state.allow:
            return PolitenessDecision(False, "host disabled (host_state.allow=false)")

        rules = self._resolve_rules(canonical_url, host, state)
        if rules is None:
            return PolitenessDecision(False, "robots.txt unavailable")

        if rules.can_fetch(_path_of(canonical_url)):
            return PolitenessDecision(True, "allowed")
        return PolitenessDecision(False, "disallowed by robots.txt")

    def _resolve_rules(
        self, canonical_url: str, host: str, state: HostState | None
    ) -> RobotsRules | None:
        """Return the effective robots rules, refreshing the cache if stale.

        ``None`` signals a transient robots.txt fetch failure (caller should not
        proceed but the URL stays leasable).
        """
        if state is not None and self._robots_fresh(state):
            return parse_robots(state.robots_txt or "", self.user_agent)

        response = self.fetcher(robots_url_for(canonical_url))
        now = self._clock()

        if 200 <= response.status < 300:
            text = response.text or ""
            rules = parse_robots(text, self.user_agent)
            self.repo.update_host_state(
                host,
                robots_txt=text,
                robots_fetched_at=now,
                crawl_delay_seconds=self._effective_delay(rules),
                allow=True,
            )
            return rules

        if 400 <= response.status < 500:
            # No robots.txt (or client error): crawling is unrestricted.
            self.repo.update_host_state(
                host,
                robots_txt="",
                robots_fetched_at=now,
                crawl_delay_seconds=self.default_delay_seconds,
                allow=True,
            )
            return parse_robots("", self.user_agent)

        # 5xx or unreachable: treat as transient. Don't cache; retry next time.
        return None

    def _robots_fresh(self, state: HostState) -> bool:
        if state.robots_fetched_at is None:
            return False
        age = self._clock() - state.robots_fetched_at
        return age <= timedelta(seconds=self.robots_ttl_seconds)

    def _effective_delay(self, rules: RobotsRules) -> int:
        """Clamp robots Crawl-delay into ``[default, max]`` seconds (rounded up)."""
        delay = self.default_delay_seconds
        if rules.crawl_delay is not None:
            delay = max(delay, math.ceil(rules.crawl_delay))
        return min(delay, self.max_delay_seconds)

    # --- per-host spacing ---

    def host_ready(self, host: str, *, now: datetime | None = None) -> bool:
        """Whether ``host``'s crawl-delay window has elapsed (1 request at a time)."""
        now = now or self._clock()
        state = self.repo.get_host_state(host)
        if state is None or state.next_allowed_fetch_at is None:
            return True
        return state.next_allowed_fetch_at <= now

    def note_fetch(self, host: str, *, when: datetime | None = None) -> datetime:
        """Record a fetch and advance the host's window by its crawl delay.

        Call this when a host's URL is dispatched so concurrent workers honor a
        single in-flight request per host. Returns the new
        ``next_allowed_fetch_at``.
        """
        when = when or self._clock()
        state = self.repo.get_host_state(host)
        delay = state.crawl_delay_seconds if state is not None else self.default_delay_seconds
        next_allowed = when + timedelta(seconds=delay)
        self.repo.update_host_state(
            host, last_fetch_at=when, next_allowed_fetch_at=next_allowed
        )
        return next_allowed


def _host_of(url: str) -> str:
    from urllib.parse import urlsplit

    return (urlsplit(url).hostname or "").lower()


def _path_of(url: str) -> str:
    from urllib.parse import urlsplit

    parts = urlsplit(url)
    path = parts.path or "/"
    return f"{path}?{parts.query}" if parts.query else path
