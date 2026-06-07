from __future__ import annotations

import pytest

from crawler.robots.parser import parse_robots, robots_url_for

UA = "ChiFoodCrawler/0.1 (+mailto:crawler@example.com)"

BASIC = """
User-agent: *
Disallow: /private/
Allow: /private/public/
Crawl-delay: 7
"""


def test_disallow_blocks_matching_prefix():
    rules = parse_robots(BASIC, UA)
    assert rules.can_fetch("/private/secret.html") is False
    assert rules.can_fetch("/about") is True


def test_allow_overrides_more_general_disallow_by_length():
    rules = parse_robots(BASIC, UA)
    # /private/public/ (16) is longer/more specific than /private/ (9) -> Allow wins.
    assert rules.can_fetch("/private/public/page") is True


def test_crawl_delay_parsed():
    assert parse_robots(BASIC, UA).crawl_delay == 7.0


def test_empty_disallow_means_allow_all():
    rules = parse_robots("User-agent: *\nDisallow:\n", UA)
    assert rules.can_fetch("/anything") is True


def test_disallow_root_blocks_everything():
    rules = parse_robots("User-agent: *\nDisallow: /\n", UA)
    assert rules.can_fetch("/") is False
    assert rules.can_fetch("/page") is False


def test_specific_agent_group_beats_wildcard():
    content = """
    User-agent: *
    Disallow: /

    User-agent: ChiFoodCrawler
    Disallow: /admin/
    """
    rules = parse_robots(content, UA)
    # Our specific group only blocks /admin/, not everything.
    assert rules.can_fetch("/recipes") is True
    assert rules.can_fetch("/admin/panel") is False


def test_no_matching_group_allows_all():
    content = "User-agent: SomeOtherBot\nDisallow: /\n"
    rules = parse_robots(content, UA)
    assert rules.can_fetch("/") is True


def test_wildcard_and_end_anchor():
    content = """
    User-agent: *
    Disallow: /*.pdf$
    Disallow: /tmp/*/cache
    """
    rules = parse_robots(content, UA)
    assert rules.can_fetch("/docs/report.pdf") is False
    assert rules.can_fetch("/docs/report.pdf?download=1") is True  # $ anchors the end
    assert rules.can_fetch("/tmp/abc/cache") is False
    assert rules.can_fetch("/tmp/cache") is True


def test_allow_beats_disallow_on_length_tie():
    content = "User-agent: *\nDisallow: /a\nAllow: /a\n"
    rules = parse_robots(content, UA)
    assert rules.can_fetch("/a") is True


def test_consecutive_user_agents_share_group():
    content = """
    User-agent: ChiFoodCrawler
    User-agent: AnotherBot
    Disallow: /shared/
    """
    rules = parse_robots(content, UA)
    assert rules.can_fetch("/shared/x") is False


def test_comments_and_blank_lines_ignored():
    content = """
    # a comment
    User-agent: *   # inline comment

    Disallow: /x  # trailing
    """
    rules = parse_robots(content, UA)
    assert rules.can_fetch("/x") is False


def test_empty_robots_allows_all():
    rules = parse_robots("", UA)
    assert rules.can_fetch("/whatever") is True
    assert rules.crawl_delay is None


def test_invalid_crawl_delay_ignored():
    rules = parse_robots("User-agent: *\nCrawl-delay: soon\n", UA)
    assert rules.crawl_delay is None


def test_crawl_delay_combines_max_across_matching_groups():
    content = """
    User-agent: *
    Crawl-delay: 3

    User-agent: chifoodcrawler
    Crawl-delay: 10
    """
    # Specific group wins outright (higher specificity), so 10.
    assert parse_robots(content, UA).crawl_delay == 10.0


@pytest.mark.parametrize(
    "url,expected",
    [
        ("https://a.com/path?q=1", "https://a.com/robots.txt"),
        ("http://b.org:8080/x", "http://b.org:8080/robots.txt"),
    ],
)
def test_robots_url_for(url, expected):
    assert robots_url_for(url) == expected
