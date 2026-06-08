from __future__ import annotations

import hashlib
from datetime import datetime

import httpx
import pytest

from crawler.fetcher import (
    HttpClient,
    build_raw_record,
    make_robots_fetcher,
    sha256_hex,
)


def _client(handler, **kw) -> HttpClient:
    # No real sleeping/clock during tests; deterministic timestamp.
    return HttpClient(
        transport=httpx.MockTransport(handler),
        sleep=lambda _seconds: None,
        clock=lambda: datetime(2026, 1, 1, 18, 0, 0),
        **kw,
    )


def test_successful_fetch_captures_metadata():
    body = b"<html>hi</html>"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, content=body, headers={"content-type": "text/html; charset=utf-8"}
        )

    with _client(handler) as client:
        out = client.get("https://h.com/page")

    assert out.ok and out.is_success
    assert out.status_code == 200
    assert out.body == body
    assert out.content_type == "text/html; charset=utf-8"
    assert out.mime_type == "text/html"
    assert out.content_hash == "sha256:" + hashlib.sha256(body).hexdigest()
    assert out.content_length == len(body)
    assert out.error is None
    assert out.fetch_timestamp == datetime(2026, 1, 1, 18, 0, 0)


def test_follows_redirects_and_reports_final_url():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/old":
            return httpx.Response(301, headers={"location": "https://h.com/new"})
        return httpx.Response(200, content=b"ok")

    with _client(handler) as client:
        out = client.get("https://h.com/old")

    assert out.status_code == 200
    assert out.final_url == "https://h.com/new"
    assert out.num_redirects == 1


def test_retries_on_503_then_succeeds():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(503)
        return httpx.Response(200, content=b"recovered")

    with _client(handler, max_retries=2) as client:
        out = client.get("https://h.com/x")

    assert calls["n"] == 2
    assert out.status_code == 200
    assert out.body == b"recovered"


def test_retries_exhausted_returns_last_status():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    with _client(handler, max_retries=2) as client:
        out = client.get("https://h.com/x")

    assert out.ok is True  # we did get HTTP responses
    assert out.is_success is False
    assert out.status_code == 503


def test_transport_error_is_captured_not_raised():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom", request=request)

    with _client(handler, max_retries=1) as client:
        out = client.get("https://h.com/x")

    assert out.ok is False
    assert out.status_code is None
    assert out.content_hash is None
    assert "ConnectError" in out.error


def test_timeout_is_captured():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    with _client(handler, max_retries=0) as client:
        out = client.get("https://h.com/x")

    assert out.ok is False
    assert "ReadTimeout" in out.error


def test_body_is_capped_at_max_bytes():
    big = b"x" * 1000

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=big)

    with _client(handler, max_bytes=100) as client:
        out = client.get("https://h.com/big")

    assert out.truncated is True
    assert out.content_length == 100


def test_user_agent_header_sent():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["ua"] = request.headers.get("user-agent")
        return httpx.Response(200, content=b"")

    with _client(handler, user_agent="ChiFoodCrawler/0.1 (+mailto:me@x.com)") as client:
        client.get("https://h.com/x")

    assert seen["ua"] == "ChiFoodCrawler/0.1 (+mailto:me@x.com)"


def test_sha256_hex_prefix():
    assert sha256_hex(b"") == "sha256:" + hashlib.sha256(b"").hexdigest()


# --- raw crawl record ---


def _outcome(handler, url="https://blog.com/post"):
    with _client(handler) as client:
        return client.get(url)


def test_build_raw_record_matches_plan_shape():
    def handler(request):
        return httpx.Response(
            200, content=b"<html/>", headers={"content-type": "text/html; charset=utf-8"}
        )

    out = _outcome(handler)
    record = build_raw_record(
        out,
        crawl_id="2026-06-06",
        canonical_url="https://blog.com/post",
        host="blog.com",
        discovery_relevance=0.62,
        raw_gcs_uri="gs://chi-food-raw/2026-06-06/blog.com/abc.warc.zst",
    )
    d = record.to_dict()
    assert d == {
        "crawl_id": "2026-06-06",
        "url": "https://blog.com/post",
        "canonical_url": "https://blog.com/post",
        "host": "blog.com",
        "status_code": 200,
        "content_type": "text/html",  # charset stripped
        "fetch_timestamp": "2026-01-01T18:00:00Z",
        "content_hash": out.content_hash,
        "discovery_relevance": 0.62,
        "raw_gcs_uri": "gs://chi-food-raw/2026-06-06/blog.com/abc.warc.zst",
    }
    assert '"crawl_id":"2026-06-06"' in record.to_json()


# --- robots adapter (component 5 plug-in) ---


@pytest.mark.parametrize(
    "status,expected_status",
    [(200, 200), (404, 404), (503, 503)],
)
def test_robots_fetcher_maps_http_status(status, expected_status):
    def handler(request):
        assert request.url.path == "/robots.txt"
        return httpx.Response(status, content=b"User-agent: *\nDisallow: /x\n")

    with _client(handler, max_retries=0) as client:
        fetch = make_robots_fetcher(client)
        resp = fetch("https://h.com/robots.txt")

    assert resp.status == expected_status
    if status == 200:
        assert "Disallow: /x" in resp.text


def test_robots_fetcher_transport_error_is_status_zero():
    def handler(request):
        raise httpx.ConnectError("no route", request=request)

    with _client(handler, max_retries=0) as client:
        resp = make_robots_fetcher(client)("https://h.com/robots.txt")

    assert resp.status == 0  # transient -> PolitenessManager won't cache
