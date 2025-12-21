"""
Unit tests for `wxpath.engine_async.evaluate_wxpath_bfs_iter_concurrent_async`.

These mirror the synchronous tests found in `test_core_concurrent.py` but target
the **async** evaluator.  All network I/O is stubbed so the tests run fully
offline.

Run with:

    pytest tests/test_core_async.py
"""

from __future__ import annotations

import pytest
import asyncio

from tests.utils import MockCrawler
from wxpath.core import parser
from wxpath.core.runtime import engine as engine


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
        engine,
        "Crawler",
        lambda *a, **k: MockCrawler(*a, pages=pages, **k),
    )

    expr = "url('http://test/')"
    segments = parser.parse_wxpath_expr(expr)

    eng = engine.WXPathEngine(concurrency=32)
    results = asyncio.run(
        _collect_async(
            eng.run(expr, max_depth=2)
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
        engine,
        "Crawler",
        lambda *a, **k: MockCrawler(*a, pages=pages, **k),
    )
    eng = engine.WXPathEngine(concurrency=32)

    expr = "url('http://test/')//url(@href)"

    
    results = asyncio.run(
        _collect_async(
            eng.run(expr, max_depth=1)
        )
    )

    # Order should follow BFS discovery order.
    assert [e.base_url for e in results] == [
        "http://test/a.html",
        "http://test/b.html",
    ]
    assert all(e.get("depth") == "1" for e in results)


def test_engine_run___crawl_xpath_crawl(monkeypatch):
    # 1: define page HTML
    pages = {
        'http://test/': b"""
            <html><body>
              <main>
                <a href="a1.html">A</a>
                <a href="a2.html">B</a>
              </main>
              <a href="b.html">B</a>
            </body></html>
        """,
        'http://test/a1.html': b"<html><body><p>Page A1</p></body></html>",
        'http://test/a2.html': b"<html><body><p>Page A2</p></body></html>",
        'http://test/b.html': b"<html><body><p>Page B</p></body></html>",
    }

    monkeypatch.setattr(
        engine,
        "Crawler",
        lambda *a, **k: MockCrawler(*a, pages=pages, **k),
    )
    eng = engine.WXPathEngine(concurrency=32)

    # 3: build & run
    expr = "url('http://test/')//main//a/url(@href)"
    results = asyncio.run(
        _collect_async(
            eng.run(expr, max_depth=1)
        )
    )

    # 4: verify BFS order and base_url propagation
    assert len(results) == 2
    assert results[0].get('depth') == '1'
    assert results[1].get('depth') == '1'
    assert {e.base_url for e in results} == {
        'http://test/a1.html',
        'http://test/a2.html',
    }


def test_engine_run__crawl_three_levels(monkeypatch):
    pages = {
      'http://test/': b"<html><body><a href='lvl1.html'>L1</a></body></html>",
      'http://test/lvl1.html': b"<html><body><a href='lvl2.html'>L2</a></body></html>",
      'http://test/lvl2.html': b"<html><body><p>Reached L2</p></body></html>",
    }
    expr = "url('http://test/')//url(@href)//url(@href)"

    monkeypatch.setattr(
        engine,
        "Crawler",
        lambda *a, **k: MockCrawler(*a, pages=pages, **k),
    )
    eng = engine.WXPathEngine(concurrency=32)
    results = asyncio.run(
        _collect_async(
            eng.run(expr, max_depth=2)
        )
    )

    assert len(results) == 1
    assert results[0].get('depth') == '2'
    assert results[0].base_url == 'http://test/lvl2.html'


def test_engine_run__crawl_two_levels_and_query(monkeypatch):
    pages = {
        'http://test/': b"""
            <html><body>
              <a href="a.html">A</a>
              <a href="b.html">B</a>
            </body></html>
        """,
        'http://test/a.html': b"<html><body><a href='page1.html'>L2</a></body></html>",
        'http://test/b.html': b"<html><body><a href='page2.html'>L2</a></body></html>",
    }
    
    expr = "url('http://test/')//url(@href)//a/@href"
    monkeypatch.setattr(
        engine,
        "Crawler",
        lambda *a, **k: MockCrawler(*a, pages=pages, **k),
    )
    eng = engine.WXPathEngine(concurrency=32)
    results = asyncio.run(
        _collect_async(
            eng.run(expr, max_depth=1)
        )
    )

    assert len(results) == 2
    assert results == [
        'page1.html',
        'page2.html',
    ]


def test_engine_run__crawl_three_levels_and_query(monkeypatch):
    pages = {
      'http://test/': b"<html><body><a href='lvl1.html'>L1</a></body></html>",
      'http://test/lvl1.html': b"<html><body><a href='lvl2.html'>L2</a></body></html>",
      'http://test/lvl2.html': b"<html><body><a href='lvl3.html'>L3</a></body></html>",
      'http://test/lvl3.html': b"<html><body><p>Reached L3</p></body></html>",
    }

    expr = "url('http://test/')//url(@href)//url(@href)//a/@href"

    monkeypatch.setattr(
        engine,
        "Crawler",
        lambda *a, **k: MockCrawler(*a, pages=pages, **k),
    )
    eng = engine.WXPathEngine(concurrency=32)
    results = asyncio.run(
        _collect_async(
            eng.run(expr, max_depth=2)
        )
    )
    assert len(results) == 1
    assert results[0] == 'lvl3.html'


def test_engine_run__crawl_four_levels_and_query_and_max_depth_2(monkeypatch):
    pages = {
      'http://test/': b"<html><body><a href='lvl1.html'>L1</a></body></html>",
      'http://test/lvl1.html': b"<html><body><a href='lvl2.html'>L2</a></body></html>",
      'http://test/lvl2.html': b"<html><body><a href='lvl3.html'>L3</a></body></html>",
      'http://test/lvl3.html': b"<html><body><a href='lvl4.html'>L4</a></body></html>",
      'http://test/lvl4.html': b"<html><body><a href='lvl5.html'>L4</a></body></html>",
    }

    expr = "url('http://test/')//url(@href)//url(@href)//a/@href"
    monkeypatch.setattr(
        engine,
        "Crawler",
        lambda *a, **k: MockCrawler(*a, pages=pages, **k),
    )
    eng = engine.WXPathEngine(concurrency=32)
    results = asyncio.run(
        _collect_async(
            eng.run(expr, max_depth=2)
        )
    )
    assert len(results) == 1
    assert results[0] == 'lvl3.html'


# Test multiple crawls with filtered (e.g., `url(@href[starts-with(., '/wiki/')])`) crawl
def test_engine_run__filtered_crawl(monkeypatch):
    pages = {
      'http://test/': b"""
            <html><body>
              <a href="lvl1a.html">A</a>
              <a href="lvl1b.html">B</a>
            </body></html>
        """,
      'http://test/lvl1a.html': b"<html><body><a href='lvl2.html'>L2</a></body></html>",
      'http://test/lvl1b.html': b"<html><body><a href='lvl99999.html'>L99999</a></body></html>",
      'http://test/lvl2.html': b"<html><body><a href='lvl3.html'>L3</a></body></html>",
      'http://test/lvl3.html': b"<html><body><p>Reached L3</p></body></html>",
    }
    
    expr = "url('http://test/')//url(@href[starts-with(., 'lvl1a')])//a/@href"
    monkeypatch.setattr(
        engine,
        "Crawler",
        lambda *a, **k: MockCrawler(*a, pages=pages, **k),
    )
    eng = engine.WXPathEngine(concurrency=32)
    results = asyncio.run(
        _collect_async(
            eng.run(expr, max_depth=2)
        )
    )
    assert len(results) == 1
    assert results[0] == 'lvl2.html'


# Test infinite crawl using ///url()
def test_engine_run__infinite_crawl_max_depth_uncapped(monkeypatch):
    pages = {
        'http://test/': b"""
            <html><body>
              <a href="a.html">A</a>
              <a href="b.html">B</a>
            </body></html>
        """,
        'http://test/a.html': b"<html><body><a href='a1.html'>L2</a></body></html>",
        'http://test/b.html': b"<html><body><a href='b1.html'>L2</a></body></html>",
        'http://test/a1.html': b"<html><body></body></html>",
        'http://test/b1.html': b"<html><body></body></html>",
    }
    
    expr = "url('http://test/')///url(@href)"
    monkeypatch.setattr(
        engine,
        "Crawler",
        lambda *a, **k: MockCrawler(*a, pages=pages, **k),
    )
    eng = engine.WXPathEngine(concurrency=32)
    results = asyncio.run(
        _collect_async(
            eng.run(expr, max_depth=9999)
        )
    )

    assert len(results) == 4
    assert [e.base_url for e in results] == [
        'http://test/a.html',
        'http://test/b.html',
        'http://test/a1.html',
        'http://test/b1.html',
    ]


def test_engine_run__infinite_crawl_max_depth_1(monkeypatch):
    pages = {
        'http://test/': b"""
            <html><body>
              <a href="a.html">A</a>
              <a href="b.html">B</a>
            </body></html>
        """,
        'http://test/a.html': b"<html><body><a href='a1.html'>L2</a></body></html>",
        'http://test/b.html': b"<html><body><a href='b1.html'>L2</a></body></html>",
        'http://test/a1.html': b"<html><body><a href='a2.html'>L3</a></body></html>",
        'http://test/b1.html': b"<html><body><a href='b2.html'>L3</a></body></html>",
    }
    expr = "url('http://test/')///url(@href)"
    monkeypatch.setattr(
        engine,
        "Crawler",
        lambda *a, **k: MockCrawler(*a, pages=pages, **k),
    )
    eng = engine.WXPathEngine(concurrency=32)
    results = asyncio.run(
        _collect_async(
            eng.run(expr, max_depth=1)
        )
    )
    assert len(results) == 2
    assert [e.base_url for e in results] == [
        'http://test/a.html',
        'http://test/b.html',
    ]


def test_engine_run__infinite_crawl__query__max_depth_1(monkeypatch):
    pages = {
        'http://test/': b"""
            <html><body>
              <a href="a.html">A</a>
              <a href="b.html">B</a>
            </body></html>
        """,
        'http://test/a.html': b"<html><body><a href='a1.html'>L2</a></body></html>",
        'http://test/b.html': b"<html><body><a href='b1.html'>L2</a></body></html>",
        'http://test/a1.html': b"<html><body><a href='a2.html'>L3</a></body></html>",
        'http://test/b1.html': b"<html><body><a href='b2.html'>L3</a></body></html>",
    }
    
    expr = "url('http://test/')///url(@href)//a/@href"
    monkeypatch.setattr(
        engine,
        "Crawler",
        lambda *a, **k: MockCrawler(*a, pages=pages, **k),
    )
    eng = engine.WXPathEngine(concurrency=32)
    results = asyncio.run(
        _collect_async(
            eng.run(expr, max_depth=1)
        )
    )

    assert len(results) == 2
    assert results == [
        'a1.html',
        'b1.html',
    ]


# # TODO: refactor with fixtures
def test_engine_run__crawl__inf_crawl__query__max_depth_2(monkeypatch):
    pages = {
        'http://test/': b"""
            <html><body>
              <a href="a.html">A</a>
              <a href="b.html">B</a>
            </body></html>
        """,
        'http://test/a.html': b"<html><body><a href='a1.html'>L2</a></body></html>",
        'http://test/b.html': b"<html><body><a href='b1.html'>L2</a></body></html>",
        'http://test/a1.html': b"<html><body><a href='a2.html'>L3</a></body></html>",
        'http://test/b1.html': b"<html><body><a href='b2.html'>L3</a></body></html>",
    }
    expr = "url('http://test/')///url(@href)//a/@href"
    
    monkeypatch.setattr(
        engine,
        "Crawler",
        lambda *a, **k: MockCrawler(*a, pages=pages, **k),
    )
    eng = engine.WXPathEngine(concurrency=32)
    results = asyncio.run(
        _collect_async(
            eng.run(expr, max_depth=2)
        )
    )
    assert len(results) == 4
    assert results == [
        'a1.html',
        'b1.html',
        'a2.html',
        'b2.html',
    ]


def test_engine_run__crawl__inf_crawl__query__dupe_link__dedupe_urls_per_depth_True__max_depth_2(monkeypatch):
    pages = {
        'http://test/': b"""
            <html><body>
              <a href="a.html">A</a>
              <a href="b.html">B</a>
              <a href="a.html">A dupe</a>
            </body></html>
        """,
        'http://test/a.html': b"<html><body><a href='a1.html'>L2</a></body></html>",
        'http://test/b.html': b"<html><body><a href='b1.html'>L2</a></body></html>",
        'http://test/a1.html': b"<html><body><a href='a2.html'>L3</a></body></html>",
        'http://test/b1.html': b"<html><body><a href='b2.html'>L3</a></body></html>",
    }
    expr = "url('http://test/')///url(@href)//a/@href"
    
    monkeypatch.setattr(
        engine,
        "Crawler",
        lambda *a, **k: MockCrawler(*a, pages=pages, **k),
    )
    eng = engine.WXPathEngine(concurrency=32)
    results = asyncio.run(
        _collect_async(
            eng.run(expr, max_depth=2)
        )
    )
    assert len(results) == 4
    assert results == [
        'a1.html',
        'b1.html',
        'a2.html',
        'b2.html',
    ]


# Test evaluate_wxpath_bfs_iter() with filtered (argument) infinite crawl - type 1
def test_engine_run__infinite_crawl_with_inf_filter_before_url_op(monkeypatch):
    pages = {
        'http://test/': b"""
            <html><body>
              <main><a href="a.html">A</a></main>
              <a href="b.html">B</a>
            </body></html>
        """,
        'http://test/a.html': b"<html><body><main><a href='a1.html'>Depth 1</a></main></body></html>",
        'http://test/b.html': b"<html><body><main><a href='b1.html'>Depth 1</a></main></body></html>",
        'http://test/a1.html': b"<html><body><a href='a2.html'>Depth 2</a></body></html>",
        'http://test/b1.html': b"<html><body><a href='b2.html'>Depth 2</a></body></html>",
    }
    
    expr = "url('http://test/')///main/a/url(@href)"

    monkeypatch.setattr(
        engine,
        "Crawler",
        lambda *a, **k: MockCrawler(*a, pages=pages, **k),
    )
    eng = engine.WXPathEngine(concurrency=32)
    results = asyncio.run(
        _collect_async(
            eng.run(expr, max_depth=2)
        )
    )
    
    assert len(results) == 2
    assert [e.base_url for e in results] == [
        'http://test/a.html',
        'http://test/a1.html'
    ]
    

# Test evaluate_wxpath_bfs_iter() with filtered (argument) infinite crawl - type 1
def test_engine_run___crawl_xpath_crawl_max_depth_1(monkeypatch):
    pages = {
        'http://test/': b"""
            <html><body>
              <main><a href="a.html">A</a></main>
              <a href="b.html">B</a>
            </body></html>
        """,
        'http://test/a.html': b"<html><body><main><a href='a1.html'>L2</a></main></body></html>",
        'http://test/b.html': b"<html><body><main><a href='b1.html'>L2</a></main></body></html>",
        'http://test/a1.html': b"<html><body><a href='a2.html'>L3</a></body></html>",
        'http://test/b1.html': b"<html><body><a href='b2.html'>L3</a></body></html>",
    }
    expr = "url('http://test/')///main/a/url(@href)"

    monkeypatch.setattr(
        engine,
        "Crawler",
        lambda *a, **k: MockCrawler(*a, pages=pages, **k),
    )
    eng = engine.WXPathEngine(concurrency=32)
    results = asyncio.run(
        _collect_async(
            eng.run(expr, max_depth=1)
        )
    )
    assert len(results) == 1
    assert results[0].get('depth') == '1'
    assert [e.base_url for e in results] == [
        'http://test/a.html'
    ]


# Test evaluate_wxpath_bfs_iter() with filtered (argument) infinite crawl - type 2
def test_engine_run___crawl_inf_crawl_with_filter(monkeypatch): #infinite_crawl_with_inf_filter_as_url_op_arg(monkeypatch):
    pages = {
        'http://test/': b"""
            <html><body>
              <main><a href="a.html">A</a></main>
              <a href="b.html">B</a>
            </body></html>
        """,
        'http://test/a.html': b"<html><body><main><a href='a1.html'>L2</a></main></body></html>",
        'http://test/b.html': b"<html><body><main><a href='b1.html'>L2</a></main></body></html>",
        'http://test/a1.html': b"<html><body><a href='a2.html'>L3</a></body></html>",
        'http://test/b1.html': b"<html><body><a href='b2.html'>L3</a></body></html>",
    }
    expr = "url('http://test/')///url(//main/a/@href)"
    monkeypatch.setattr(
        engine,
        "Crawler",
        lambda *a, **k: MockCrawler(*a, pages=pages, **k),
    )
    eng = engine.WXPathEngine(concurrency=32)
    results = asyncio.run(
        _collect_async(
            eng.run(expr, max_depth=2)
        )
    )
    assert len(results) == 2
    assert [e.get('depth') for e in results if e.base_url == 'http://test/a.html'] == ['1']
    assert [e.get('depth') for e in results if e.base_url == 'http://test/a1.html'] == ['2']
    assert [e.base_url for e in results] == [
        'http://test/a.html',
        'http://test/a1.html'
    ]

## Obsolete
# def test_engine_run__object_extraction(monkeypatch):
#     pages = {
#         'http://test/': b"""
#             <html><body>
#               <h1>The Test Page</h1>
#               <p>Alpha</p><p>Beta</p>
#             </body></html>
#         """
#     }

#     monkeypatch.setattr('wxpath.engine.helpers.fetch_html', _generate_fake_fetch_html(pages))

#     expr = (
#         "url('http://test/')/map { "
#         "'title'://h1/text()/string(), "
#         "'paragraphs'://p/text() "
#         "}"
#     )
#     segments = parse_wxpath_expr(expr)
#     results = list(evaluate_wxpath_bfs_iter(None, segments, max_depth=0))

#     assert len(results) == 1
#     obj = results[0]
#     assert obj['title'] == 'The Test Page'
#     assert obj['paragraphs'] == ['Alpha', 'Beta']


# def test_engine_run__object_indexing(monkeypatch):
#     pages = {
#         'http://test/': b"""
#             <html><body>
#               <p>One</p><p>Two</p><p>Three</p>
#             </body></html>
#         """
#     }

#     monkeypatch.setattr('wxpath.engine.helpers.fetch_html', _generate_fake_fetch_html(pages))

#     expr = (
#         "url('http://test/')/ map{ "
#         "'first':string((//p/text())[1]), "
#         "'second':string((//p/text())[2]), "
#         "'all'://p/text() "
#         "}"
#     )
#     segments = parse_wxpath_expr(expr)
#     results = list(evaluate_wxpath_bfs_iter(None, segments, max_depth=0))

#     assert len(results) == 1
#     obj = results[0]
#     assert obj['first'] == 'One'
#     assert obj['second'] == 'Two'
#     assert obj['all'] == ['One', 'Two', 'Three']
