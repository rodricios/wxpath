import asyncio

import pytest

from wxpath.http.client.crawler import Crawler
from wxpath.http.client.request import Request

# ------------------------
# Fake HTTP primitives
# ------------------------

class FakeResponse:
    def __init__(self, status: int, body: bytes):
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


# ------------------------
# Tests
# ------------------------

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
