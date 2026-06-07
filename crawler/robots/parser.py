"""A focused ``robots.txt`` parser.

Implements the subset of the Robots Exclusion Protocol the crawler needs:
``User-agent`` groups, ``Allow``/``Disallow`` rules with ``*`` wildcards and the
``$`` end-anchor, and ``Crawl-delay``. Matching follows Google's rules:

* The most specific user-agent group wins (longest matching token; ``*`` is the
  lowest-priority fallback). Rules from every group declaring the winning token
  are combined.
* For a given path the *longest* matching rule wins; on a length tie ``Allow``
  beats ``Disallow``. If no rule matches, the path is allowed.

We deliberately avoid :mod:`urllib.robotparser`: it uses first-match (not
longest-match) precedence and exposes crawl-delay awkwardly, both of which make
correct, testable behavior harder.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from urllib.parse import urlsplit


@dataclass(frozen=True, slots=True)
class _Rule:
    allow: bool
    pattern: str  # original path pattern, e.g. "/private/*.json$"
    regex: re.Pattern[str]
    length: int  # specificity = length of the original pattern


@dataclass
class _Group:
    agents: list[str] = field(default_factory=list)
    rules: list[_Rule] = field(default_factory=list)
    crawl_delay: float | None = None


def _compile_pattern(pattern: str) -> re.Pattern[str]:
    """Translate a robots path pattern (``*`` wildcard, ``$`` anchor) to regex."""
    anchored_end = pattern.endswith("$")
    body = pattern[:-1] if anchored_end else pattern
    out = ["^"]
    for ch in body:
        if ch == "*":
            out.append(".*")
        else:
            out.append(re.escape(ch))
    if anchored_end:
        out.append("$")
    return re.compile("".join(out))


@dataclass(frozen=True, slots=True)
class RobotsRules:
    """Resolved rules for a single crawler user-agent."""

    crawl_delay: float | None
    _rules: tuple[_Rule, ...]

    def can_fetch(self, path: str) -> bool:
        """Return whether ``path`` (path + optional ``?query``) may be fetched."""
        if not path:
            path = "/"
        best: _Rule | None = None
        for rule in self._rules:
            if rule.regex.match(path):
                if best is None or rule.length > best.length or (
                    rule.length == best.length and rule.allow and not best.allow
                ):
                    best = rule
        return True if best is None else best.allow


_EMPTY_RULES = RobotsRules(crawl_delay=None, _rules=())


def _agent_specificity(agent: str, ua_token: str) -> int:
    """Match score for a ``User-agent`` value against our UA. -1 means no match."""
    a = agent.lower()
    if a == "*":
        return 0
    return len(a) if a in ua_token else -1


def parse_robots(content: str, user_agent: str) -> RobotsRules:
    """Parse ``robots.txt`` text into the effective :class:`RobotsRules` for ``user_agent``.

    ``user_agent`` may be a full UA string (e.g. ``"ChiFoodCrawler/0.1 (+...)"``);
    matching is done against its lowercased form.
    """
    ua_token = user_agent.lower()
    groups: list[_Group] = []
    current: _Group | None = None
    # A blank line / new User-agent after rules starts a fresh group; consecutive
    # User-agent lines (with no rules between) share one group.
    started_rules = False

    for raw_line in content.splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if not line or ":" not in line:
            continue
        field_name, _, value = line.partition(":")
        field_name = field_name.strip().lower()
        value = value.strip()

        if field_name == "user-agent":
            if current is None or started_rules:
                current = _Group()
                groups.append(current)
                started_rules = False
            current.agents.append(value)
            continue

        if current is None:
            continue  # rule before any user-agent: ignore

        if field_name in ("allow", "disallow"):
            started_rules = True
            if value == "":
                # Empty Disallow = allow all (no-op); empty Allow likewise no-op.
                continue
            current.rules.append(
                _Rule(
                    allow=(field_name == "allow"),
                    pattern=value,
                    regex=_compile_pattern(value),
                    length=len(value),
                )
            )
        elif field_name == "crawl-delay":
            started_rules = True
            try:
                current.crawl_delay = float(value)
            except ValueError:
                pass

    best_spec = -1
    for group in groups:
        for agent in group.agents:
            best_spec = max(best_spec, _agent_specificity(agent, ua_token))
    if best_spec < 0:
        return _EMPTY_RULES

    rules: list[_Rule] = []
    delays: list[float] = []
    for group in groups:
        if any(_agent_specificity(a, ua_token) == best_spec for a in group.agents):
            rules.extend(group.rules)
            if group.crawl_delay is not None:
                delays.append(group.crawl_delay)
    return RobotsRules(crawl_delay=max(delays) if delays else None, _rules=tuple(rules))


def robots_url_for(url: str) -> str:
    """Return the ``robots.txt`` URL for the host of ``url``."""
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}/robots.txt"
