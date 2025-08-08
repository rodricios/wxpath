import asyncio

from types import SimpleNamespace
from typing import Iterable


class MockCrawler:
    """
    Drop-in replacement for `wxpath.crawler.Crawler`.

    It provides an `run_async(urls, cb)` coroutine that feeds predefined HTML
    bodies to the callback without performing any network requests.
    """
    def __init__(self, *args, pages=None, **kwargs):
        self.pages = pages or {}

    async def __aenter__(self):
        # No-op, but mirrors the real Crawler API
        return self

    async def __aexit__(self, exc_type, exc, tb):
        # No-op
        return False

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
