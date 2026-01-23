import asyncio

from wxpath.http.client.response import Response


class MockCrawler:
    """Drop-in replacement for `wxpath.crawler.Crawler`.

    It provides an `run_async(urls, cb)` coroutine that feeds predefined HTML
    bodies to the callback without performing any network requests.
    """
    def __init__(self, *args, pages=None, **kwargs):
        self.pages = pages
        self._queue = asyncio.Queue()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        pass

    def submit(self, request):
        body = self.pages.get(request.url)
        resp = Response(
            request=request,
            status=200,
            body=body,
            headers={}
        )
        self._queue.put_nowait(resp)

    def __aiter__(self):
        return self

    async def __anext__(self):
        return await self._queue.get()
    
    async def run_async(self, urls, cb):
        # Support sync or async callback
        if not asyncio.iscoroutinefunction(cb):
            async def _cb(u, r, b):
                return cb(u, r, b)
        else:
            _cb = cb

        class _Resp:
            __slots__ = ("status",)
            def __init__(self, status):
                self.status = status

        for url in urls:
            body = self.pages.get(url)
            resp = _Resp(200 if body is not None else 404)
            await _cb(url, resp, body or b"")


class MockCrawlerWithErrors(MockCrawler):
    """Mock crawler that can simulate various error scenarios."""
    def __init__(self, responses_by_url, error_responses=None, unexpected_responses=None):
        """
        Args:
            responses_by_url: Dict mapping URL to Response object (normal responses)
            error_responses: Dict mapping URL to Exception (network errors)
            unexpected_responses: List of Response objects for unexpected URLs (URLs not submitted)
        """
        self._queue = asyncio.Queue()
        self._responses_by_url = responses_by_url or {}
        self._error_responses = error_responses or {}
        self._unexpected_responses = unexpected_responses or []
        self._unexpected_index = 0
        self._submitted_urls = set()

    def submit(self, request):
        self._submitted_urls.add(request.url)
        # Check for error response first
        if request.url in self._error_responses:
            error = self._error_responses[request.url]
            resp = Response(
                request=request,
                status=0,
                body=b"",
                headers={},
                error=error
            )
            self._queue.put_nowait(resp)
        elif request.url in self._responses_by_url:
            resp = self._responses_by_url[request.url]
            self._queue.put_nowait(resp)

    async def __anext__(self):
        # If we have unexpected responses queued, yield them first
        # These are responses for URLs that were never submitted
        if self._unexpected_index < len(self._unexpected_responses):
            resp = self._unexpected_responses[self._unexpected_index]
            self._unexpected_index += 1
            return resp
        
        # Otherwise, wait for normal responses
        return await self._queue.get()




def _generate_fake_fetch_html(pages):
    def _fake_fetch_html(url):
        try:
            return pages[url]
        except KeyError:
            raise AssertionError(f"Unexpected URL fetched: {url}") from None

    return _fake_fetch_html
