"""Polite HTTP client for the crawler.

A thin wrapper over :mod:`httpx` that enforces the behavior the crawler needs:
connect/read timeouts, bounded redirect following, retries with exponential
backoff on transient failures (network errors and 429/5xx), a hard body-size
cap (streamed, so we stop reading oversized responses), and a descriptive
User-Agent. Every fetch returns a :class:`FetchOutcome`; transport failures are
captured as ``error`` rather than raised, so a worker can record the failure and
move on.

Network I/O goes through an injectable ``httpx`` transport, so tests drive it
with :class:`httpx.MockTransport` and never touch the network.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from datetime import UTC, datetime
from types import TracebackType

import httpx

from crawler.robots.policy import RobotsFetcher, RobotsResponse
from crawler.robots.useragent import DEFAULT_USER_AGENT

from .models import FetchOutcome, sha256_hex

DEFAULT_TIMEOUT_SECONDS = 15.0
DEFAULT_MAX_RETRIES = 2  # total attempts = max_retries + 1
DEFAULT_MAX_REDIRECTS = 5
DEFAULT_MAX_BYTES = 5 * 1024 * 1024  # 5 MiB
DEFAULT_BACKOFF_BASE_SECONDS = 0.5
RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class HttpClient:
    def __init__(
        self,
        *,
        user_agent: str = DEFAULT_USER_AGENT,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        max_retries: int = DEFAULT_MAX_RETRIES,
        max_redirects: int = DEFAULT_MAX_REDIRECTS,
        max_bytes: int = DEFAULT_MAX_BYTES,
        backoff_base_seconds: float = DEFAULT_BACKOFF_BASE_SECONDS,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], datetime] = _utcnow,
    ) -> None:
        self.user_agent = user_agent
        self.max_retries = max_retries
        self.max_bytes = max_bytes
        self.backoff_base_seconds = backoff_base_seconds
        self._sleep = sleep
        self._clock = clock
        self._client = httpx.Client(
            follow_redirects=True,
            max_redirects=max_redirects,
            timeout=timeout_seconds,
            headers={"User-Agent": user_agent},
            transport=transport,
        )

    def __enter__(self) -> HttpClient:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()

    def close(self) -> None:
        self._client.close()

    def get(self, url: str) -> FetchOutcome:
        """Fetch ``url``, following redirects and retrying transient failures."""
        started = self._clock()
        start_perf = time.perf_counter()
        last_error: str | None = None

        for attempt in range(self.max_retries + 1):
            try:
                outcome = self._attempt(url, started)
            except httpx.TooManyRedirects as exc:
                # Deterministic (a redirect loop / over-long chain): retrying
                # won't help, so fail immediately with the error captured.
                last_error = f"{type(exc).__name__}: {exc}"
                break
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                last_error = f"{type(exc).__name__}: {exc}"
            else:
                if outcome.status_code in RETRYABLE_STATUS and attempt < self.max_retries:
                    self._sleep(self.backoff_base_seconds * (2**attempt))
                    continue
                return outcome

            if attempt < self.max_retries:
                self._sleep(self.backoff_base_seconds * (2**attempt))

        # All attempts failed at the transport layer.
        return FetchOutcome(
            url=url,
            final_url=url,
            status_code=None,
            content_type=None,
            body=b"",
            content_hash=None,
            fetch_timestamp=started,
            elapsed_seconds=time.perf_counter() - start_perf,
            num_redirects=0,
            truncated=False,
            error=last_error or "request failed",
        )

    def _attempt(self, url: str, started: datetime) -> FetchOutcome:
        start_perf = time.perf_counter()
        with self._client.stream("GET", url) as response:
            # On a retryable status, skip downloading the (often error-page) body.
            if response.status_code in RETRYABLE_STATUS:
                body, truncated = b"", False
            else:
                body, truncated = self._read_capped(response)
        return FetchOutcome(
            url=url,
            final_url=str(response.url),
            status_code=response.status_code,
            content_type=response.headers.get("content-type"),
            body=body,
            content_hash=sha256_hex(body),
            fetch_timestamp=started,
            elapsed_seconds=time.perf_counter() - start_perf,
            num_redirects=len(response.history),
            truncated=truncated,
            error=None,
        )

    def _read_capped(self, response: httpx.Response) -> tuple[bytes, bool]:
        """Stream the body, stopping once ``max_bytes`` is reached."""
        chunks: list[bytes] = []
        total = 0
        truncated = False
        for chunk in response.iter_bytes():
            chunks.append(chunk)
            total += len(chunk)
            # Only truncated if the body actually exceeds the cap; a body exactly
            # equal to max_bytes is kept whole.
            if total > self.max_bytes:
                truncated = True
                break
        body = b"".join(chunks)[: self.max_bytes]
        return body, truncated


def make_robots_fetcher(client: HttpClient) -> RobotsFetcher:
    """Adapt an :class:`HttpClient` into a :class:`RobotsFetcher` for the
    politeness layer (component 5). A transport failure maps to status ``0`` so
    :class:`~crawler.robots.policy.PolitenessManager` treats it as transient and
    does not cache it."""

    def fetch(robots_url: str) -> RobotsResponse:
        outcome = client.get(robots_url)
        if not outcome.ok:
            return RobotsResponse(status=0)
        text = outcome.body.decode("utf-8", errors="replace")
        return RobotsResponse(status=outcome.status_code, text=text)

    return fetch
