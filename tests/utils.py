import asyncio

from types import SimpleNamespace
from typing import Iterable


class MockCrawler:
    """
    Drop‑in replacement for `wxpath.crawler.Crawler`.

    It provides an `run_async(urls, cb)` coroutine that feeds predefined HTML
    bodies to the callback without performing any network requests.
    """

    def __init__(self, *a, pages: dict[str, bytes] | None = None, **kw):
        self.pages = pages or {}

    async def run_async(self, urls: Iterable[str], cb):
        async def _one(url: str):
            body = self.pages[url]
            # Minimal stand‑in for `aiohttp.ClientResponse`.
            resp = SimpleNamespace(status=200, url=url)
            await cb(url, resp, body)

        await asyncio.gather(*(_one(u) for u in urls))


def _generate_fake_fetch_html(pages):
    def _fake_fetch_html(url):
        try:
            return pages[url]
        except KeyError:
            raise AssertionError(f"Unexpected URL fetched: {url}")

    return _fake_fetch_html
