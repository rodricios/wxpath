"""
Unit tests for `wxpath.core_async.evaluate_wxpath_bfs_iter_concurrent_async`.

These mirror the synchronous tests found in `test_core_concurrent.py` but target
the **async** evaluator.  All network I/O is stubbed so the tests run fully
offline.

Run with:

    pytest tests/test_core_async.py
"""

from __future__ import annotations

import asyncio

from tests.utils import MockCrawler
from wxpath.core import parser
from wxpath.core import async_


def _generate_fake_fetch_html(pages: dict[str, bytes]):
    """Return a stub that replaces `core.fetch_html`."""
    def _fake_fetch_html(url: str) -> bytes:
        try:
            return pages[url]
        except KeyError as exc:
            raise AssertionError(f"Unexpected URL fetched: {url!r}") from exc
    return _fake_fetch_html


async def _collect_async(gen):
    """Consume an **async** generator and return a list of its items."""
    return [item async for item in gen]


# --------------------------------------------------------------------------- #
# Tests
# --------------------------------------------------------------------------- #
def test_async_single_level(monkeypatch):
    """A single `url()` segment should yield the parsed root element."""
    pages = {
        "http://test/": b"<html><body><p>Hello</p></body></html>",
    }

    # Monkey‑patch network helpers.
    monkeypatch.setattr(
        async_,
        "Crawler",
        lambda *a, **k: MockCrawler(*a, pages=pages, **k),
    )

    expr = "url('http://test/')"
    segments = parser.parse_wxpath_expr(expr)

    results = asyncio.run(
        _collect_async(
            async_.evaluate_wxpath_bfs_iter_async(None, segments)
        )
    )

    assert len(results) == 1
    root = results[0]
    assert root.get("depth") == "0"
    assert root.base_url == "http://test/"


def test_async_two_levels(monkeypatch):
    """
    Root page contains two links; both should be fetched concurrently at depth 1.
    """
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

    monkeypatch.setattr(
        async_,
        "Crawler",
        lambda *a, **k: MockCrawler(*a, pages=pages, **k),
    )

    expr = "url('http://test/')//url(@href)"
    segments = parser.parse_wxpath_expr(expr)

    results = asyncio.run(
        _collect_async(
            async_.evaluate_wxpath_bfs_iter_async(None, segments, max_depth=1)
        )
    )

    # Order should follow BFS discovery order.
    assert [e.base_url for e in results] == [
        "http://test/a.html",
        "http://test/b.html",
    ]
    assert all(e.get("depth") == "1" for e in results)