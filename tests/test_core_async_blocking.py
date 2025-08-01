"""
Unit-tests for wxpath.core_concurrent.evaluate_wxpath_bfs_iter_concurrent.
"""

import asyncio
from types import SimpleNamespace

from wxpath import core
from wxpath import core_async_blocking


def _generate_fake_fetch_html(pages):
    """Return a stub that replaces core.fetch_html (used by sequential paths)."""
    def _fake_fetch_html(url):
        try:
            return pages[url]
        except KeyError:
            raise AssertionError(f"Unexpected URL fetched: {url!r}")
    return _fake_fetch_html


class MockCrawler:
    """
    Drop-in replacement for wxpath.crawler.Crawler that services requests
    from an in-memory *pages* mapping and invokes the async callback exactly
    like the real crawler would - but without network I/O.
    """
    def __init__(self, *a, pages=None, **kw):
        self.pages = pages or {}

    def run(self, urls, cb):
        async def _call(url):
            body = self.pages[url]
            # make a minimal fake aiohttp.ClientResponse
            resp = SimpleNamespace(status=200, url=url)
            await cb(url, resp, body)

        async def _runner():
            await asyncio.gather(*(_call(u) for u in urls))

        asyncio.run(_runner())


def test_concurrent_single_level(monkeypatch):
    pages = {
        "http://test/": b"<html><body><p>Hello</p></body></html>",
    }

    # stub out network
    monkeypatch.setattr(core, "fetch_html", _generate_fake_fetch_html(pages))
    monkeypatch.setattr(
        core_async_blocking,
        "Crawler",
        lambda *a, **k: MockCrawler(*a, pages=pages, **k),
    )

    expr = "url('http://test/')"
    segs = core.parse_wxpath_expr(expr)
    out = list(core_async_blocking.evaluate_wxpath_bfs_iter_async_blocking(None, segs))

    assert len(out) == 1
    root = out[0]
    assert root.get("depth") == "0"
    assert root.base_url == "http://test/"


def test_concurrent_two_levels(monkeypatch):
    pages = {
        "http://test/": b"""
            <html><body>
              <a href="a.html">A</a>
              <a href="b.html">B</a>
            </body></html>
        """,
        "http://test/a.html": b"<html><body><p>A</p></body></html>",
        "http://test/b.html": b"<html><body><p>B</p></body></html>",
    }

    monkeypatch.setattr(core, "fetch_html", _generate_fake_fetch_html(pages))
    monkeypatch.setattr(
        core_async_blocking,
        "Crawler",
        lambda *a, **k: MockCrawler(*a, pages=pages, **k),
    )

    expr = "url('http://test/')//url(@href)"
    segs = core.parse_wxpath_expr(expr)
    out = list(core_async_blocking.evaluate_wxpath_bfs_iter_async_blocking(None, segs, max_depth=1))

    assert [e.base_url for e in out] == [
        "http://test/a.html",
        "http://test/b.html",
    ]
    assert all(e.get("depth") == "1" for e in out)