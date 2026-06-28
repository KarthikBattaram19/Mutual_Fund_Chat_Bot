import json

import httpx
import pytest

from ingestion.fetcher import FetcherError, URLFetcher


HTML_BODY = "<html><body>" + ("factual scheme content " * 40) + "</body></html>"
JS_SHELL = "<html><body><noscript>Please enable JavaScript</noscript></body></html>"


class FakeResponse:
    def __init__(self, status_code: int, text: str = HTML_BODY) -> None:
        self.status_code = status_code
        self.text = text


class FakeClient:
    def __init__(self, responses) -> None:
        self.responses = list(responses)
        self.urls: list[str] = []
        self.closed = False

    def get(self, url: str):
        self.urls.append(url)
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response

    def close(self) -> None:
        self.closed = True


class FakeClock:
    def __init__(self) -> None:
        self.current = 1_000.0
        self.sleeps: list[float] = []

    def time(self) -> float:
        return self.current

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.current += seconds


class PlaywrightFetcher(URLFetcher):
    def _fetch_with_playwright(self, url: str) -> str:
        return HTML_BODY


def test_fetch_url_returns_successful_html() -> None:
    client = FakeClient([FakeResponse(200)])
    fetcher = URLFetcher(client=client, rate_limit_seconds=0, min_html_chars=10)

    result = fetcher.fetch_url("https://groww.in/mutual-funds/example")

    assert result.ok
    assert result.html == HTML_BODY
    assert result.status_code == 200
    assert result.used_playwright is False
    assert result.error is None


def test_fetch_url_retries_retryable_status_with_backoff() -> None:
    clock = FakeClock()
    client = FakeClient([FakeResponse(503, "busy"), FakeResponse(200)])
    fetcher = URLFetcher(
        client=client,
        max_retries=2,
        retry_backoff_seconds=2,
        rate_limit_seconds=0,
        min_html_chars=10,
        sleep=clock.sleep,
        clock=clock.time,
    )

    result = fetcher.fetch_url("https://groww.in/mutual-funds/example")

    assert result.ok
    assert client.urls == [
        "https://groww.in/mutual-funds/example",
        "https://groww.in/mutual-funds/example",
    ]
    assert clock.sleeps == [2]


def test_fetch_url_flags_unreachable_page_without_crashing_batch() -> None:
    client = FakeClient([httpx.ConnectError("connection failed")])
    fetcher = URLFetcher(client=client, max_retries=1, rate_limit_seconds=0)

    result = fetcher.fetch_url("https://groww.in/mutual-funds/example")

    assert result.ok is False
    assert result.html is None
    assert result.status_code is None
    assert result.error == "ConnectError"


def test_fetch_url_can_raise_on_failure() -> None:
    client = FakeClient([FakeResponse(404, "missing")])
    fetcher = URLFetcher(client=client, rate_limit_seconds=0)

    with pytest.raises(FetcherError, match="HTTP 404"):
        fetcher.fetch_url("https://groww.in/mutual-funds/example", raise_on_error=True)


def test_fetch_all_applies_rate_limit_between_urls() -> None:
    clock = FakeClock()
    client = FakeClient([FakeResponse(200), FakeResponse(200)])
    fetcher = URLFetcher(
        client=client,
        rate_limit_seconds=1.5,
        min_html_chars=10,
        sleep=clock.sleep,
        clock=clock.time,
    )
    corpus_entries = [
        {"source_url": "https://groww.in/mutual-funds/one"},
        {"source_url": "https://groww.in/mutual-funds/two"},
    ]

    results = fetcher.fetch_all(corpus_entries)

    assert [result.url for result in results] == [
        "https://groww.in/mutual-funds/one",
        "https://groww.in/mutual-funds/two",
    ]
    assert all(result.ok for result in results)
    assert clock.sleeps == [1.5]


def test_fetch_corpus_index_loads_source_urls(tmp_path) -> None:
    corpus_path = tmp_path / "corpus_index.json"
    corpus_path.write_text(
        json.dumps(
            [
                {"source_url": "https://groww.in/mutual-funds/one"},
                {"source_url": "https://groww.in/mutual-funds/two"},
            ]
        ),
        encoding="utf-8",
    )
    client = FakeClient([FakeResponse(200), FakeResponse(200)])
    fetcher = URLFetcher(client=client, rate_limit_seconds=0, min_html_chars=10)

    results = fetcher.fetch_corpus_index(corpus_path)

    assert [result.url for result in results] == [
        "https://groww.in/mutual-funds/one",
        "https://groww.in/mutual-funds/two",
    ]


def test_js_rendered_page_uses_playwright_fallback() -> None:
    client = FakeClient([FakeResponse(200, JS_SHELL)])
    fetcher = PlaywrightFetcher(client=client, rate_limit_seconds=0, min_html_chars=10)

    result = fetcher.fetch_url("https://groww.in/mutual-funds/example")

    assert result.ok
    assert result.html == HTML_BODY
    assert result.used_playwright is True


def test_next_data_page_does_not_require_playwright_fallback() -> None:
    html = (
        '<html><head><script id="__NEXT_DATA__" type="application/json">'
        '{"props":{"pageProps":{"scheme":{"nav":"Rs 100.00"}}}}'
        "</script></head><body><noscript>Please enable JavaScript</noscript></body></html>"
    )
    client = FakeClient([FakeResponse(200, html)])
    fetcher = PlaywrightFetcher(client=client, rate_limit_seconds=0, min_html_chars=10)

    result = fetcher.fetch_url("https://groww.in/mutual-funds/example")

    assert result.ok
    assert result.html == html
    assert result.used_playwright is False


def test_js_rendered_page_is_flagged_when_fallback_disabled() -> None:
    client = FakeClient([FakeResponse(200, JS_SHELL)])
    fetcher = URLFetcher(
        client=client,
        rate_limit_seconds=0,
        min_html_chars=10,
        use_playwright_fallback=False,
    )

    result = fetcher.fetch_url("https://groww.in/mutual-funds/example")

    assert result.ok is False
    assert result.error == "page appears JavaScript-rendered"
