from __future__ import annotations

from datetime import datetime, timedelta

import pytest
import sqlalchemy as sa
from sqlalchemy.pool import StaticPool

from crawler.frontier.repository import FrontierRepository
from crawler.robots.policy import PolitenessManager, RobotsResponse

UA = "ChiFoodCrawler/0.1 (+mailto:crawler@example.com)"


@pytest.fixture
def repo() -> FrontierRepository:
    eng = sa.create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    r = FrontierRepository(eng)
    r.create_schema()
    return r


class FakeFetcher:
    """Scripted robots.txt fetcher that records the URLs it was asked for."""

    def __init__(self, response: RobotsResponse) -> None:
        self.response = response
        self.calls: list[str] = []

    def __call__(self, robots_url: str) -> RobotsResponse:
        self.calls.append(robots_url)
        return self.response


class Clock:
    def __init__(self, start: datetime) -> None:
        self.now = start

    def __call__(self) -> datetime:
        return self.now


def _mgr(repo, fetcher, clock=None, **kw) -> PolitenessManager:
    return PolitenessManager(
        repo, fetcher, user_agent=UA, clock=clock or (lambda: datetime(2026, 1, 1)), **kw
    )


def test_authorize_fetches_and_caches_then_uses_cache(repo):
    fetcher = FakeFetcher(RobotsResponse(200, "User-agent: *\nDisallow: /private/\n"))
    mgr = _mgr(repo, fetcher)

    assert mgr.authorize("https://h.com/private/x").allowed is False
    assert mgr.authorize("https://h.com/public/x").allowed is True
    # robots.txt fetched exactly once; second call served from host_state cache.
    assert fetcher.calls == ["https://h.com/robots.txt"]

    state = repo.get_host_state("h.com")
    assert state.robots_txt == "User-agent: *\nDisallow: /private/\n"
    assert state.robots_fetched_at == datetime(2026, 1, 1)


def test_stale_cache_triggers_refetch(repo):
    fetcher = FakeFetcher(RobotsResponse(200, "User-agent: *\nDisallow: /a\n"))
    clock = Clock(datetime(2026, 1, 1))
    mgr = _mgr(repo, fetcher, clock=clock, robots_ttl_seconds=3600)

    mgr.authorize("https://h.com/a")
    clock.now = datetime(2026, 1, 1) + timedelta(seconds=3601)  # past TTL
    mgr.authorize("https://h.com/a")
    assert len(fetcher.calls) == 2


def test_404_allows_all_and_caches(repo):
    fetcher = FakeFetcher(RobotsResponse(404))
    mgr = _mgr(repo, fetcher)
    assert mgr.authorize("https://h.com/anything").allowed is True
    state = repo.get_host_state("h.com")
    assert state.robots_txt == ""
    assert state.crawl_delay_seconds == 5
    # Cached: a follow-up does not re-fetch.
    mgr.authorize("https://h.com/other")
    assert len(fetcher.calls) == 1


def test_5xx_is_transient_not_cached_and_blocks(repo):
    fetcher = FakeFetcher(RobotsResponse(503))
    mgr = _mgr(repo, fetcher)
    assert mgr.authorize("https://h.com/x").allowed is False
    assert repo.get_host_state("h.com") is None  # nothing cached
    mgr.authorize("https://h.com/x")
    assert len(fetcher.calls) == 2  # retried because not cached


def test_429_is_transient_not_allow_all(repo):
    # A rate-limited robots.txt must NOT be cached as "no robots = allow all".
    fetcher = FakeFetcher(RobotsResponse(429))
    mgr = _mgr(repo, fetcher)
    assert mgr.authorize("https://h.com/x").allowed is False
    assert repo.get_host_state("h.com") is None  # nothing cached
    mgr.authorize("https://h.com/x")
    assert len(fetcher.calls) == 2  # retried, not served from a bogus cache


def test_host_allow_false_is_kill_switch(repo):
    repo.update_host_state("h.com", allow=False)
    fetcher = FakeFetcher(RobotsResponse(200, ""))
    mgr = _mgr(repo, fetcher)
    assert mgr.authorize("https://h.com/x").allowed is False
    assert fetcher.calls == []  # short-circuits before fetching robots


def test_url_without_host_blocked(repo):
    mgr = _mgr(repo, FakeFetcher(RobotsResponse(200, "")))
    assert mgr.authorize("not-a-url").allowed is False


def test_host_ready_and_note_fetch_spacing(repo):
    fetcher = FakeFetcher(RobotsResponse(200, "User-agent: *\nCrawl-delay: 10\n"))
    clock = Clock(datetime(2026, 1, 1, 12, 0, 0))
    mgr = _mgr(repo, fetcher, clock=clock)

    assert mgr.host_ready("h.com") is True  # never fetched
    mgr.authorize("https://h.com/a")  # caches crawl_delay_seconds=10

    next_allowed = mgr.note_fetch("h.com")
    assert next_allowed == datetime(2026, 1, 1, 12, 0, 10)
    assert mgr.host_ready("h.com") is False  # within the 10s window

    clock.now = datetime(2026, 1, 1, 12, 0, 11)
    assert mgr.host_ready("h.com") is True


@pytest.mark.parametrize(
    "robots_delay,expected",
    [
        ("1", 5),  # below default floor -> 5
        ("30", 30),  # honored
        ("9999", 60),  # clamped to max
    ],
)
def test_effective_crawl_delay_clamping(repo, robots_delay, expected):
    fetcher = FakeFetcher(RobotsResponse(200, f"User-agent: *\nCrawl-delay: {robots_delay}\n"))
    mgr = _mgr(repo, fetcher)
    mgr.authorize("https://h.com/a")
    assert repo.get_host_state("h.com").crawl_delay_seconds == expected


def test_note_fetch_defaults_delay_when_no_state(repo):
    mgr = _mgr(repo, FakeFetcher(RobotsResponse(200, "")))
    nxt = mgr.note_fetch("fresh.com", when=datetime(2026, 1, 1))
    assert nxt == datetime(2026, 1, 1) + timedelta(seconds=5)


def test_note_fetch_window_is_monotonic(repo):
    # A racing worker already pushed the window far out; a later note_fetch with
    # an earlier proposed deadline must not shrink it.
    mgr = _mgr(repo, FakeFetcher(RobotsResponse(200, "")))
    mgr.note_fetch("h.com", when=datetime(2026, 1, 1, 12, 0, 0))  # -> 12:00:05
    repo.update_host_state("h.com", next_allowed_fetch_at=datetime(2026, 1, 1, 12, 0, 30))

    mgr.note_fetch("h.com", when=datetime(2026, 1, 1, 12, 0, 1))  # proposes 12:00:06
    assert repo.get_host_state("h.com").next_allowed_fetch_at == datetime(2026, 1, 1, 12, 0, 30)


def test_robots_refresh_does_not_clobber_allow_kill_switch(repo):
    # Operator disables the host; a successful robots refresh must leave allow=False.
    repo.update_host_state("h.com", allow=False)
    mgr = _mgr(repo, FakeFetcher(RobotsResponse(200, "User-agent: *\nDisallow: /x\n")))
    # Bypass authorize's early return to exercise the refresh path directly.
    mgr._resolve_rules("https://h.com/a", "h.com", repo.get_host_state("h.com"))
    assert repo.get_host_state("h.com").allow is False


def test_robots_url_normalized_to_hostname(repo):
    # Cache is keyed by hostname, so the robots URL drops port/userinfo for a
    # stable, consistent fetch origin.
    fetcher = FakeFetcher(RobotsResponse(200, ""))
    mgr = _mgr(repo, fetcher)
    mgr.authorize("https://h.com:8080/some/path")
    assert fetcher.calls == ["https://h.com/robots.txt"]
