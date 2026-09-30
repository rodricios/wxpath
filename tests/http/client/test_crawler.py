import asyncio
from socket import gaierror
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from wxpath.http.client.crawler import Crawler, PlaywrightCrawler
from wxpath.http.client.request import Request

# ------------------------
# Fake HTTP primitives
# ------------------------

class FakeResponse:
    def __init__(self, status: int, body: bytes):
        self.url = ""
        self.status = status
        self._body = body
        self.headers = {}

    async def read(self):
        return self._body

    async def text(self):
        return self._body.decode('utf-8')

    @property
    def content(self):
        """Simulate aiohttp ClientResponse.content for streaming."""
        class FakeContent:
            def __init__(self, body: bytes):
                self._body = body
                self._chunk_size = 8192

            async def iter_chunked(self, chunk_size: int):
                """Iterate over body in chunks."""
                for i in range(0, len(self._body), chunk_size):
                    yield self._body[i:i + chunk_size]

        return FakeContent(self._body)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        pass


class FakeSession:
    """
    Each .get() pops the next FakeResponse.
    """
    def __init__(self, responses):
        self._responses = list(responses)

    def get(self, *args, **kwargs):
        if not self._responses:
            raise RuntimeError("No more fake responses")
        return self._responses.pop(0)

    async def close(self):
        pass


class FakeCacheActions:
    """Cache action container used by Playwright crawler unit tests."""

    def __init__(self, *, skip_read: bool, key: str = "cache-key", expires=None):
        """Initialize cache actions.

        Args:
            skip_read: Whether cache read should be skipped.
            key: Cache key used for save operations.
            expires: Optional expiration timestamp.
        """
        self.skip_read = skip_read
        self.key = key
        self.expires = expires
        self.updated_response = None

    def update_from_response(self, response) -> None:
        """Record the response used to update cache actions."""
        self.updated_response = response


class FakeCacheBackend:
    """Minimal async cache backend for Playwright crawler tests."""

    def __init__(
        self,
        *,
        actions: FakeCacheActions,
        cached_response=None,
        cacheable: bool = True,
    ):
        """Initialize fake cache backend.

        Args:
            actions: Cache action instance returned by create_cache_actions.
            cached_response: Optional cached response returned by request().
            cacheable: Whether is_cacheable() should return True.
        """
        self.actions = actions
        self.cached_response = cached_response
        self.cacheable = cacheable
        self.saved = []

    def create_key(self, method: str, url: str, **kwargs) -> str:
        """Return deterministic cache key for tests."""
        return f"{method}:{url}"

    def create_cache_actions(self, key: str, url: str, **kwargs) -> FakeCacheActions:
        """Return the preconfigured fake actions object."""
        return self.actions

    async def request(self, actions: FakeCacheActions):
        """Return configured cached response."""
        return self.cached_response

    async def is_cacheable(self, response, actions: FakeCacheActions) -> bool:
        """Return cacheability flag."""
        return self.cacheable

    async def save_response(self, response, key: str, expires) -> None:
        """Capture saved cache entries for assertions."""
        self.saved.append((response, key, expires))

    async def close(self) -> None:
        """No-op close for test compatibility."""
        return None


class FakePage:
    """Simple async Playwright page test double."""

    def __init__(self, *, response, html: str, networkidle_error: Exception | None = None):
        """Initialize fake page.

        Args:
            response: Response object returned from goto().
            html: HTML string returned from content().
            networkidle_error: Optional exception raised for networkidle state.
        """
        self._response = response
        self._html = html
        self._networkidle_error = networkidle_error
        self.wait_calls: list[str] = []

    async def goto(self, url: str, wait_until: str):
        """Return configured response from navigation."""
        return self._response

    async def wait_for_load_state(self, state: str, timeout: int):
        """Simulate wait-for-load behavior, including fallback path."""
        self.wait_calls.append(state)
        if state == "networkidle" and self._networkidle_error is not None:
            raise self._networkidle_error

    async def content(self) -> str:
        """Return configured page content."""
        return self._html


class FakeContext:
    """Simple async Playwright browser context test double."""

    def __init__(self, page: FakePage):
        """Initialize fake context with one page.

        Args:
            page: Page object returned by new_page().
        """
        self._page = page
        self.closed = False

    async def new_page(self) -> FakePage:
        """Return the configured fake page."""
        return self._page

    async def close(self) -> None:
        """Mark context as closed."""
        self.closed = True


class FakeBrowser:
    """Simple async Playwright browser test double."""

    def __init__(self, context: FakeContext):
        """Initialize fake browser.

        Args:
            context: Context object returned by new_context().
        """
        self._context = context
        self.new_context_kwargs = None

    async def new_context(self, **kwargs) -> FakeContext:
        """Capture context options and return configured context."""
        self.new_context_kwargs = kwargs
        return self._context

    async def close(self) -> None:
        """No-op close for compatibility."""
        return None


# ------------------------
# Tests
# ------------------------

@pytest.mark.asyncio
async def test_dns_error_yields_error_response(monkeypatch):
    """DNS failures should yield an error response instead of hanging."""
    crawler = Crawler(concurrency=1, respect_robots=False, auto_throttle_start_delay=0.0)

    async def _raise_dns_error(self, req):
        raise gaierror("Name or service not known")

    monkeypatch.setattr(Crawler, "_fetch_one", _raise_dns_error)

    async with crawler:
        crawler.submit(Request("http://not-a-real-hostname.invalid", max_retries=0))
        resp = await asyncio.wait_for(crawler.__aiter__().__anext__(), timeout=0.2)

    assert resp.status == 0
    assert resp.error is not None
    assert isinstance(resp.error, gaierror)


@pytest.mark.asyncio
async def test_single_request_success():
    crawler = Crawler(concurrency=1, respect_robots=False)

    crawler._session = FakeSession([
        FakeResponse(200, b"ok"),
    ])

    req = Request("http://example.com")

    results = []

    async with crawler:
        crawler.submit(req)

        async for resp in crawler:
            results.append(resp.body)
            break

    assert results == [b"ok"]


@pytest.mark.asyncio
async def test_retry_then_success():
    crawler = Crawler(concurrency=1, respect_robots=False)

    crawler._session = FakeSession([
        FakeResponse(500, b"fail"),
        FakeResponse(200, b"ok"),
    ])

    req = Request("http://example.com", max_retries=2)

    results = []

    async with crawler:
        crawler.submit(req)

        async for resp in crawler:
            results.append(resp.body)
            break

    assert results == [b"ok"]


@pytest.mark.asyncio
async def test_retry_exhaustion_yields_nothing():
    crawler = Crawler(concurrency=1, respect_robots=False)

    crawler._session = FakeSession([
        FakeResponse(500, b"fail"),
        FakeResponse(500, b"fail-again"),
    ])

    req = Request("http://example.com", max_retries=1)

    async with crawler:
        crawler.submit(req)

        # Allow some time for retries to be processed
        await asyncio.sleep(0.05)

        # No responses should be yielded
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(crawler.__aiter__().__anext__(), timeout=0.05)


@pytest.mark.asyncio
async def test_multiple_requests_stream_as_ready():
    crawler = Crawler(concurrency=2, respect_robots=False)

    crawler._session = FakeSession([
        FakeResponse(200, b"a"),
        FakeResponse(200, b"b"),
    ])

    r1 = Request("http://a.com")
    r2 = Request("http://b.com")

    results = []

    async with crawler:
        crawler.submit(r1)
        crawler.submit(r2)

        async for resp in crawler:
            results.append(resp.body)
            if len(results) == 2:
                break

    assert set(results) == {b"a", b"b"}


@pytest.mark.asyncio
async def test_overlap_retry_does_not_block_other_requests():
    """
    This directly tests the scenario:

    - request A retries
    - request B completes immediately
    - B is yielded while A is retrying
    """
    crawler = Crawler(concurrency=2, respect_robots=False)

    crawler._session = FakeSession([
        FakeResponse(500, b"fail"),   # A fails -> retry
        FakeResponse(200, b"b"),      # B succeeds
        FakeResponse(200, b"a"),      # A retry succeeds
    ])

    slow = Request("http://slow.com", max_retries=1)
    fast = Request("http://fast.com")

    results = []

    async with crawler:
        crawler.submit(slow)
        crawler.submit(fast)

        async for resp in crawler:
            results.append(resp.body)
            if len(results) == 2:
                break

    # Order is not guaranteed — only non-blocking behavior is
    assert set(results) == {b"a", b"b"}


@pytest.mark.asyncio
async def test_submit_after_starting_iteration():
    """
    Ensures crawler can accept new work while results are being consumed.
    """
    crawler = Crawler(concurrency=1, respect_robots=False)

    crawler._session = FakeSession([
        FakeResponse(200, b"first"),
        FakeResponse(200, b"second"),
    ])

    results = []

    async with crawler:
        crawler.submit(Request("http://first.com"))

        async for resp in crawler:
            results.append(resp.body)

            if resp.body == b"first":
                crawler.submit(Request("http://second.com"))

            if len(results) == 2:
                break

    assert results == [b"first", b"second"]


@pytest.mark.asyncio
async def test_robots_txt_allowed():
    """Test that allowed URLs are fetched when robots.txt permits them."""
    crawler = Crawler(concurrency=1, respect_robots=True)

    crawler._session = FakeSession(
        [
            # robots.txt for example.com
            FakeResponse(200, b"User-agent: *\nDisallow: /private"),
            # the allowed page
            FakeResponse(200, b"ok"),
        ]
    )

    req = Request("http://example.com/allowed")

    results = []
    async with crawler:
        crawler.submit(req)
        async for resp in crawler:
            if resp.body:
                results.append(resp.body)
            break

    assert results == [b"ok"]


@pytest.mark.asyncio
async def test_robots_txt_disallowed():
    """Test that disallowed URLs return 403 when robots.txt blocks them."""
    crawler = Crawler(concurrency=1, respect_robots=True)

    # robots.txt is fetched first, then the request is checked
    crawler._session = FakeSession(
        [
            # robots.txt for example.com (fetched when can_fetch is called)
            FakeResponse(200, b"User-agent: *\nDisallow: /private"),
        ]
    )

    req = Request("http://example.com/private/page", max_retries=0)

    responses = []
    async with crawler:
        crawler.submit(req)
        # Collect all responses
        async for resp in crawler:
            responses.append(resp)
            # Stop after getting one response
            break

    # Should get a 403 response for disallowed URL
    assert len(responses) == 1
    assert responses[0].status == 403
    assert responses[0].error is not None
    assert "robots.txt" in str(responses[0].error)


@pytest.mark.asyncio
async def test_playwright_cache_silhouette_includes_request_headers():
    """Playwright cache objects must include request_info.headers for serialization."""
    crawler = PlaywrightCrawler(concurrency=1, respect_robots=False)
    response = SimpleNamespace(
        url="https://example.com/page",
        status_text="OK",
        status=200,
        headers={"Content-Type": "text/html; charset=utf-8"},
    )

    silhouette = crawler._build_cache_response_silhouette(response, "<html></html>")

    assert "User-Agent" in silhouette.request_info.headers
    assert silhouette.request_info.real_url == "https://example.com/page"
    assert isinstance(silhouette.raw_headers[0][0], bytes)
    assert isinstance(silhouette.raw_headers[0][1], bytes)


@pytest.mark.asyncio
async def test_playwright_aexit_cancels_workers_and_closes_resources():
    """Playwright crawler shutdown should close workers and managed resources."""
    crawler = PlaywrightCrawler(concurrency=1, respect_robots=False)
    crawler._workers = [asyncio.create_task(asyncio.sleep(60))]
    crawler._cache_backend = SimpleNamespace(close=AsyncMock())
    crawler._browser = SimpleNamespace(close=AsyncMock())
    crawler._playwright = SimpleNamespace(stop=AsyncMock())

    await crawler.__aexit__(None, None, None)

    assert crawler._closed is True
    assert crawler._workers == []
    assert crawler._cache_backend is None
    assert crawler._browser is None
    assert crawler._playwright is None


@pytest.mark.asyncio
async def test_playwright_fetch_one_uses_cached_response_without_browser_navigation():
    """Cache hits should return immediately without opening a browser context."""
    cached = SimpleNamespace(
        status=200,
        _body=b"<html>cached</html>",
        headers={"Content-Type": "text/html"},
    )
    backend = FakeCacheBackend(actions=FakeCacheActions(skip_read=True), cached_response=cached)
    browser = SimpleNamespace(new_context=AsyncMock())
    crawler = PlaywrightCrawler(concurrency=1, respect_robots=False)
    crawler._cache_backend = backend
    crawler._browser = browser

    response = await crawler._fetch_one(Request("https://example.com"))

    assert response.status == 200
    assert response.body == b"<html>cached</html>"
    browser.new_context.assert_not_awaited()


@pytest.mark.asyncio
async def test_playwright_fetch_one_without_optional_cache_backend():
    """Playwright navigation should work when optional cache support is absent."""
    playwright_response = SimpleNamespace(
        url="https://example.com/page",
        status_text="OK",
        status=200,
        headers={"Content-Type": "text/html"},
    )
    page = FakePage(response=playwright_response, html="<html>fresh</html>")
    context = FakeContext(page)
    crawler = PlaywrightCrawler(concurrency=1, respect_robots=False)
    crawler._browser = FakeBrowser(context)

    response = await crawler._fetch_one(Request("https://example.com/page"))

    assert response.status == 200
    assert response.body == "<html>fresh</html>"
    assert context.closed is True


@pytest.mark.asyncio
async def test_playwright_fetch_one_headless_navigation_and_cache_write():
    """Cache miss should navigate via browser context and persist cache entry."""
    actions = FakeCacheActions(skip_read=True, key="k1")
    backend = FakeCacheBackend(actions=actions, cached_response=None, cacheable=True)
    playwright_response = SimpleNamespace(
        url="https://example.com/page",
        status_text="OK",
        status=200,
        headers={"Content-Type": "text/html"},
    )
    page = FakePage(response=playwright_response, html="<html>fresh</html>")
    context = FakeContext(page)
    browser = FakeBrowser(context)

    crawler = PlaywrightCrawler(concurrency=1, respect_robots=False)
    crawler._cache_backend = backend
    crawler._browser = browser

    response = await crawler._fetch_one(Request("https://example.com/page"))

    assert response.status == 200
    assert response.body == "<html>fresh</html>"
    assert context.closed is True
    assert browser.new_context_kwargs["user_agent"] == crawler._headers.get("User-Agent")
    assert browser.new_context_kwargs["extra_http_headers"] == crawler._headers
    assert len(backend.saved) == 1
    saved_response, saved_key, _ = backend.saved[0]
    assert saved_key == "k1"
    assert saved_response.request_info.headers == crawler._headers


@pytest.mark.asyncio
async def test_playwright_fetch_one_falls_back_to_load_when_networkidle_times_out():
    """Playwright fetch should fall back to load state after networkidle timeout."""
    actions = FakeCacheActions(skip_read=True)
    backend = FakeCacheBackend(actions=actions, cached_response=None, cacheable=False)
    playwright_response = SimpleNamespace(
        url="https://example.com/page",
        status_text="OK",
        status=200,
        headers={"Content-Type": "text/html"},
    )
    page = FakePage(
        response=playwright_response,
        html="<html>fallback</html>",
        networkidle_error=TimeoutError("networkidle timeout"),
    )
    context = FakeContext(page)
    browser = FakeBrowser(context)

    crawler = PlaywrightCrawler(concurrency=1, respect_robots=False)
    crawler._cache_backend = backend
    crawler._browser = browser

    response = await crawler._fetch_one(Request("https://example.com/page"))

    assert response.status == 200
    assert page.wait_calls == ["networkidle", "load"]
