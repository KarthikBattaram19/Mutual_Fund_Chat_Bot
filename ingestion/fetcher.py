from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

import httpx


DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0 Safari/537.36 MutualFundFAQAssistant/1.0"
)


@dataclass(frozen=True)
class FetchResult:
    """Structured fetch outcome for one corpus URL."""

    url: str
    html: str | None
    status_code: int | None
    fetched_at: str
    used_playwright: bool = False
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None and self.html is not None and 200 <= (self.status_code or 0) < 300


class FetcherError(RuntimeError):
    """Raised when a URL cannot be fetched and callers request hard failure."""


class URLFetcher:
    """Fetch corpus pages with polite throttling, retries, and browser fallback."""

    def __init__(
        self,
        *,
        client: httpx.Client | None = None,
        timeout_seconds: float = 20.0,
        max_retries: int = 3,
        retry_backoff_seconds: float = 1.0,
        rate_limit_seconds: float = 1.0,
        min_html_chars: int = 500,
        use_playwright_fallback: bool = True,
        sleep: Any = time.sleep,
        clock: Any = time.time,
    ) -> None:
        if max_retries < 1:
            raise ValueError("max_retries must be at least 1")
        if retry_backoff_seconds < 0:
            raise ValueError("retry_backoff_seconds cannot be negative")
        if rate_limit_seconds < 0:
            raise ValueError("rate_limit_seconds cannot be negative")

        self._owns_client = client is None
        self._client = client or httpx.Client(
            timeout=timeout_seconds,
            follow_redirects=True,
            headers={"User-Agent": DEFAULT_USER_AGENT, "Accept": "text/html,application/xhtml+xml"},
        )
        self._max_retries = max_retries
        self._retry_backoff_seconds = retry_backoff_seconds
        self._rate_limit_seconds = rate_limit_seconds
        self._min_html_chars = min_html_chars
        self._use_playwright_fallback = use_playwright_fallback
        self._sleep = sleep
        self._clock = clock
        self._last_request_at: float | None = None

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> URLFetcher:
        return self

    def __exit__(self, *_exc_info: object) -> None:
        self.close()

    def fetch_url(self, url: str, *, raise_on_error: bool = False) -> FetchResult:
        """Fetch one URL and return a structured result instead of crashing the batch."""

        result = self._fetch_url(url)
        if raise_on_error and not result.ok:
            raise FetcherError(result.error or f"Failed to fetch {url}")
        return result

    def fetch_all(
        self,
        corpus_entries: Iterable[Mapping[str, Any]],
        *,
        raise_on_error: bool = False,
    ) -> list[FetchResult]:
        """Fetch every corpus entry; each item must include a source_url field."""

        results: list[FetchResult] = []
        for entry in corpus_entries:
            url = str(entry["source_url"])
            results.append(self.fetch_url(url, raise_on_error=raise_on_error))
        return results

    def fetch_corpus_index(
        self,
        corpus_index_path: str | Path = Path("data/corpus_index.json"),
        *,
        raise_on_error: bool = False,
    ) -> list[FetchResult]:
        """Load the authoritative corpus index and fetch all configured URLs."""

        corpus_path = Path(corpus_index_path)
        corpus_entries = json.loads(corpus_path.read_text(encoding="utf-8"))
        return self.fetch_all(corpus_entries, raise_on_error=raise_on_error)

    def _fetch_url(self, url: str) -> FetchResult:
        last_error: str | None = None
        last_status_code: int | None = None

        for attempt in range(1, self._max_retries + 1):
            self._throttle()
            try:
                response = self._client.get(url)
                last_status_code = response.status_code

                if 200 <= response.status_code < 300:
                    html = response.text
                    if self._looks_js_rendered(html):
                        return self._fetch_with_playwright_or_flag(url, response.status_code)
                    return self._success(url, html, response.status_code, used_playwright=False)

                last_error = f"HTTP {response.status_code}"
                if not self._is_retryable_status(response.status_code):
                    break
            except httpx.HTTPError as exc:
                last_error = exc.__class__.__name__

            if attempt < self._max_retries:
                self._sleep(self._retry_backoff_seconds * attempt)

        return self._failure(url, last_status_code, last_error or "unknown fetch error")

    def _fetch_with_playwright_or_flag(self, url: str, original_status_code: int) -> FetchResult:
        if not self._use_playwright_fallback:
            return self._failure(url, original_status_code, "page appears JavaScript-rendered")

        try:
            html = self._fetch_with_playwright(url)
        except Exception as exc:  # pragma: no cover - exact Playwright exceptions vary by install.
            return self._failure(url, original_status_code, f"Playwright fallback failed: {exc.__class__.__name__}")

        if self._looks_js_rendered(html):
            return self._failure(url, original_status_code, "Playwright returned incomplete page content")

        return self._success(url, html, 200, used_playwright=True)

    def _fetch_with_playwright(self, url: str) -> str:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            try:
                page = browser.new_page(user_agent=DEFAULT_USER_AGENT)
                page.goto(url, wait_until="networkidle", timeout=30_000)
                return page.content()
            finally:
                browser.close()

    def _throttle(self) -> None:
        if self._last_request_at is None:
            self._last_request_at = self._clock()
            return

        elapsed = self._clock() - self._last_request_at
        remaining = self._rate_limit_seconds - elapsed
        if remaining > 0:
            self._sleep(remaining)
        self._last_request_at = self._clock()

    def _looks_js_rendered(self, html: str) -> bool:
        lowered = html.lower()
        if len(html.strip()) < self._min_html_chars:
            return True
        if "__NEXT_DATA__" in html or "self.__next_f.push" in html:
            return False

        js_markers = (
            "enable javascript",
            "please enable js",
            "you need to enable javascript",
            "<noscript",
        )
        return any(marker in lowered for marker in js_markers)

    @staticmethod
    def _is_retryable_status(status_code: int) -> bool:
        return status_code == 429 or 500 <= status_code < 600

    def _success(self, url: str, html: str, status_code: int, *, used_playwright: bool) -> FetchResult:
        return FetchResult(
            url=url,
            html=html,
            status_code=status_code,
            fetched_at=self._utc_now(),
            used_playwright=used_playwright,
        )

    def _failure(self, url: str, status_code: int | None, error: str) -> FetchResult:
        return FetchResult(
            url=url,
            html=None,
            status_code=status_code,
            fetched_at=self._utc_now(),
            error=error,
        )

    def _utc_now(self) -> str:
        return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(self._clock()))
