import asyncio

from types import SimpleNamespace
from typing import Iterable
from wxpath.http.client.response import Response


class MockCrawler:
    """
    Drop-in replacement for `wxpath.crawler.Crawler`.

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


def _generate_fake_fetch_html(pages):
    def _fake_fetch_html(url):
        try:
            return pages[url]
        except KeyError:
            raise AssertionError(f"Unexpected URL fetched: {url}")

    return _fake_fetch_html
