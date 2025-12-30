from __future__ import annotations

import asyncio

import pytest

from tests.utils import MockCrawler
from wxpath.core.runtime import engine
from wxpath.core.runtime.engine import WXPathEngine


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
def test_engine_run__crawl(monkeypatch):
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

    eng = engine.WXPathEngine()
    results = asyncio.run(
        _collect_async(
            eng.run(expr, max_depth=2)
        )
    )

    assert len(results) == 1
    root = results[0]
    assert root.get("depth") == "0"
    assert root.base_url == "http://test/"


def test_engine_run__crawl__crawl_with_xpath(monkeypatch):
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
    eng = engine.WXPathEngine()

    expr = "url('http://test/')//url(//@href)"

    
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


def test_engine_run__crawl_with_follow__extract(monkeypatch):
    """
    There are multiple links on the page; only one should be followed until the end.
    """
    pages = {
        "http://test/": b"""
            <html><body>
              <div class="quote"><p>"The only true wisdom is in knowing you know nothing."</p></div>
              <a class="next" href="a.html">A</a>
              <a href="X.html">X</a>
            </body></html>
        """,
        "http://test/a.html": b"""
            <html><body>
              <div class="quote"><p>"Knowing yourself is the beginning of all wisdom."</p></div>
              <a class="next" href="b.html">B</a>
              <a href="X.html">X</a>
            </body></html>
        """,
        "http://test/b.html": b"""
            <html><body>
              <div class="quote">
                <p>"There is only one good, knowledge, and one evil, ignorance."</p>
              </div>
              <a href="X.html">X</a>
            </body></html>
        """,
        "http://test/X.html": b"""
            <html><body>
              <div class="quote">
                <p>"You shall not pass!"</p>
              </div>
            </body></html>
        """,
    }

    monkeypatch.setattr(
        engine,
        "Crawler",
        lambda *a, **k: MockCrawler(*a, pages=pages, **k),
    )
    eng = engine.WXPathEngine()

    expr = """
        url('http://test/', follow=//a[@class='next']/@href)
    """
    
    results = asyncio.run(
        _collect_async(
            eng.run(expr, max_depth=2)
        )
    )

    assert [e.base_url for e in results] == [
        "http://test/",
        "http://test/a.html",
        "http://test/b.html",
    ]


def test_engine_run__crawl__crawl_with_xpath_2(monkeypatch):
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
    eng = engine.WXPathEngine()

    expr = "url('http://test/')//url(//main//a/@href)"
    results = asyncio.run(
        _collect_async(
            eng.run(expr, max_depth=1)
        )
    )

    assert len(results) == 2
    assert results[0].get('depth') == '1'
    assert results[1].get('depth') == '1'
    assert {e.base_url for e in results} == {
        'http://test/a1.html',
        'http://test/a2.html',
    }


def test_engine_run__crawl__crawl_with_xpath_3(monkeypatch):
    pages = {
        'http://test/': b"""
            <html><body>
              <main>
                <a href="a1.html">A</a>
                <a href="a2.html">B</a>
                <a href="http://different/a3.html">C</a>
              </main>
              <a href="b.html">B</a>
            </body></html>
        """,
        'http://test/a1.html': b"<html><body><p>Page A1</p></body></html>",
        'http://test/a2.html': b"<html><body><p>Page A2</p></body></html>",
        'http://test/b.html': b"<html><body><p>Page B</p></body></html>",
        'http://different/a3.html': b"<html><body><p>Page A3</p></body></html>",
    }

    monkeypatch.setattr(
        engine,
        "Crawler",
        lambda *a, **k: MockCrawler(*a, pages=pages, **k),
    )
    eng = engine.WXPathEngine()

    expr = "url('http://test/')//url(//main//a/@href)"
    results = asyncio.run(
        _collect_async(
            eng.run(expr, max_depth=1)
        )
    )

    assert len(results) == 3
    assert results[0].get('depth') == '1'
    assert results[1].get('depth') == '1'
    assert results[2].get('depth') == '1'
    assert {e.base_url for e in results} == {
        'http://test/a1.html',
        'http://test/a2.html',
        'http://different/a3.html'
    }


def test_engine_run__crawl__xpath__crawl_with_xpath(monkeypatch):
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
    eng = engine.WXPathEngine()

    expr = "url('http://test/')//main//a/url(@href)"
    results = asyncio.run(
        _collect_async(
            eng.run(expr, max_depth=1)
        )
    )

    assert len(results) == 2
    assert results[0].get('depth') == '1'
    assert results[1].get('depth') == '1'
    assert {e.base_url for e in results} == {
        'http://test/a1.html',
        'http://test/a2.html',
    }


def test_engine_run__crawl__xpath__crawl_2(monkeypatch):
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
    eng = engine.WXPathEngine()

    expr = "url('http://test/')//main//a/@href/url(.)"
    results = asyncio.run(
        _collect_async(
            eng.run(expr, max_depth=1)
        )
    )

    assert len(results) == 2
    assert results[0].get('depth') == '1'
    assert results[1].get('depth') == '1'
    assert {e.base_url for e in results} == {
        'http://test/a1.html',
        'http://test/a2.html',
    }


def test_engine_run__crawl__crawl__crawl(monkeypatch):
    pages = {
      'http://test/': b"<html><body><a href='lvl1.html'>L1</a></body></html>",
      'http://test/lvl1.html': b"<html><body><a href='lvl2.html'>L2</a></body></html>",
      'http://test/lvl2.html': b"<html><body><p>Reached L2</p></body></html>",
    }
    expr = "url('http://test/')//url(//@href)//url(//@href)"

    monkeypatch.setattr(
        engine,
        "Crawler",
        lambda *a, **k: MockCrawler(*a, pages=pages, **k),
    )
    eng = engine.WXPathEngine()
    results = asyncio.run(
        _collect_async(
            eng.run(expr, max_depth=2)
        )
    )

    assert len(results) == 1
    assert results[0].get('depth') == '2'
    assert results[0].base_url == 'http://test/lvl2.html'


def test_engine_run__crawl__crawl_with_xpath__xpath(monkeypatch):
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
    
    expr = "url('http://test/')//url(//@href)//a/@href"
    monkeypatch.setattr(
        engine,
        "Crawler",
        lambda *a, **k: MockCrawler(*a, pages=pages, **k),
    )
    eng = engine.WXPathEngine()
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


def test_engine_run__crawl__crawl_with_xpath__crawl_with_xpath__xpath(monkeypatch):
    pages = {
      'http://test/': b"<html><body><a href='lvl1.html'>L1</a></body></html>",
      'http://test/lvl1.html': b"<html><body><a href='lvl2.html'>L2</a></body></html>",
      'http://test/lvl2.html': b"<html><body><a href='lvl3.html'>L3</a></body></html>",
      'http://test/lvl3.html': b"<html><body><p>Reached L3</p></body></html>",
    }

    expr = "url('http://test/')//url(//@href)//url(//@href)//a/@href"

    monkeypatch.setattr(
        engine,
        "Crawler",
        lambda *a, **k: MockCrawler(*a, pages=pages, **k),
    )
    eng = engine.WXPathEngine()
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

    expr = "url('http://test/')//url(//@href)//url(//@href)//a/@href"
    monkeypatch.setattr(
        engine,
        "Crawler",
        lambda *a, **k: MockCrawler(*a, pages=pages, **k),
    )
    eng = engine.WXPathEngine()
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
    
    expr = "url('http://test/')//url(//@href[starts-with(., 'lvl1a')])//a/@href"
    monkeypatch.setattr(
        engine,
        "Crawler",
        lambda *a, **k: MockCrawler(*a, pages=pages, **k),
    )
    eng = engine.WXPathEngine()
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
    
    expr = "url('http://test/')///url(//@href)"
    monkeypatch.setattr(
        engine,
        "Crawler",
        lambda *a, **k: MockCrawler(*a, pages=pages, **k),
    )
    eng = engine.WXPathEngine()
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
    expr = "url('http://test/')///url(//@href)"
    monkeypatch.setattr(
        engine,
        "Crawler",
        lambda *a, **k: MockCrawler(*a, pages=pages, **k),
    )
    eng = engine.WXPathEngine()
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
    
    expr = "url('http://test/')///url(//@href)//a/@href"
    monkeypatch.setattr(
        engine,
        "Crawler",
        lambda *a, **k: MockCrawler(*a, pages=pages, **k),
    )
    eng = engine.WXPathEngine()
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
    expr = "url('http://test/')///url(//@href)//a/@href"
    
    monkeypatch.setattr(
        engine,
        "Crawler",
        lambda *a, **k: MockCrawler(*a, pages=pages, **k),
    )
    eng = engine.WXPathEngine()
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


def test_engine_run__crawl__inf_crawl__query__dupe_link__max_depth_2(monkeypatch):
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
    expr = "url('http://test/')///url(//@href)//a/@href"
    
    monkeypatch.setattr(
        engine,
        "Crawler",
        lambda *a, **k: MockCrawler(*a, pages=pages, **k),
    )
    eng = engine.WXPathEngine()
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


def test_engine_run__xpath_fn_map_frag__crawl(monkeypatch):
    pages = {
        'http://test/1': b"""
            <html><body></body></html>""",
        'http://test/2': b"""
            <html><body></body></html>""",
        'http://test/3': b"""
            <html><body></body></html>""",
    }
    expr = "(1 to 3) ! ('http://test/' || .) ! url(.)"
    
    monkeypatch.setattr(
        engine,
        "Crawler",
        lambda *a, **k: MockCrawler(*a, pages=pages, **k),
    )
    eng = engine.WXPathEngine()
    results = asyncio.run(
        _collect_async(
            eng.run(expr, max_depth=2)
        )
    )
    assert len(results) == 3
    assert set(r.base_url for r in results) == {
        'http://test/1',
        'http://test/2',
        'http://test/3',
    }


# NOTE: I'm considering removing the wxpath expr equality of
# ///main//a/url(@href) and url(//main//a/@href)
# Test evaluate_wxpath_bfs_iter() with filtered (argument) infinite crawl - type 1
# def test_engine_run__infinite_crawl_with_inf_filter_before_url_op(monkeypatch):
#     pages = {
#         'http://test/': b"""
#             <html><body>
#               <main><a href="a.html">A</a></main>
#               <a href="b.html">B</a>
#             </body></html>
#         """,
#         'http://test/a.html':
#             b"<html><body><main><a href='a1.html'>Depth 1</a></main></body></html>",
#         'http://test/b.html':
#             b"<html><body><main><a href='b1.html'>Depth 1</a></main></body></html>",
#         'http://test/a1.html': b"<html><body><a href='a2.html'>Depth 2</a></body></html>",
#         'http://test/b1.html': b"<html><body><a href='b2.html'>Depth 2</a></body></html>",
#     }
    
#     expr = "url('http://test/')///main/a/url(//@href)"

#     monkeypatch.setattr(
#         engine,
#         "Crawler",
#         lambda *a, **k: MockCrawler(*a, pages=pages, **k),
#     )
#     eng = engine.WXPathEngine()
#     results = asyncio.run(
#         _collect_async(
#             eng.run(expr, max_depth=2)
#         )
#     )
    
#     assert len(results) == 2
#     assert [e.base_url for e in results] == [
#         'http://test/a.html',
#         'http://test/a1.html'
#     ]
    

# NOTE: I'm considering removing the wxpath expr equality of
# ///main//a/url(@href) and url(//main//a/@href)
# Test evaluate_wxpath_bfs_iter() with filtered (argument) infinite crawl - type 1
# def test_engine_run___crawl_xpath_crawl_max_depth_1(monkeypatch):
#     pages = {
#         'http://test/': b"""
#             <html><body>
#               <main><a href="a.html">A</a></main>
#               <a href="b.html">B</a>
#             </body></html>
#         """,
#         'http://test/a.html': b"<html><body><main><a href='a1.html'>L2</a></main></body></html>",
#         'http://test/b.html': b"<html><body><main><a href='b1.html'>L2</a></main></body></html>",
#         'http://test/a1.html': b"<html><body><a href='a2.html'>L3</a></body></html>",
#         'http://test/b1.html': b"<html><body><a href='b2.html'>L3</a></body></html>",
#     }
#     expr = "url('http://test/')///main/a/url(//@href)"

#     monkeypatch.setattr(
#         engine,
#         "Crawler",
#         lambda *a, **k: MockCrawler(*a, pages=pages, **k),
#     )
#     eng = engine.WXPathEngine()
#     results = asyncio.run(
#         _collect_async(
#             eng.run(expr, max_depth=1)
#         )
#     )
#     assert len(results) == 1
#     assert results[0].get('depth') == '1'
#     assert [e.base_url for e in results] == [
#         'http://test/a.html'
#     ]


# Test evaluate_wxpath_bfs_iter() with filtered (argument) infinite crawl - type 2
def test_engine_run___crawl_inf_crawl_with_filter(monkeypatch):
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
    eng = engine.WXPathEngine()
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

# -----------------------------
# Test: infinite crawl with max depth
# -----------------------------
@pytest.mark.asyncio
async def test_engine_infinite_crawl_max_depth(monkeypatch):
    pages = {
        "http://root/": b"<html><a href='a.html'>A</a><a href='b.html'>B</a></html>",
        "http://root/a.html": b"<html></html>",
        "http://root/b.html": b"<html></html>",
    }

    monkeypatch.setattr(
        engine,
        "Crawler",
        lambda *a, **k: MockCrawler(*a, pages=pages, **k),
    )

    eng = WXPathEngine(concurrency=2)
    results = await _collect_async(eng.run("url('http://root/')///url(//@href)", max_depth=1))

    urls = [r.base_url for r in results]
    assert "http://root/a.html" in urls
    assert "http://root/b.html" in urls


# -----------------------------
# Test: engine does not hang on duplicate URLs
# -----------------------------
@pytest.mark.asyncio
async def test_engine_deduplicates_urls(monkeypatch):
    pages = {
        "http://root/": b"<html><a href='a.html'>A</a><a href='a.html'>A dup</a></html>",
        "http://root/a.html": b"<html></html>",
    }

    monkeypatch.setattr(
        engine,
        "Crawler",
        lambda *a, **k: MockCrawler(*a, pages=pages, **k),
    )

    eng = WXPathEngine(concurrency=2)
    results = await _collect_async(eng.run("url('http://root/')///url(//@href)", max_depth=1))

    urls = [r.base_url for r in results]
    # Only one instance of the duplicate URL should be returned
    assert urls.count("http://root/a.html") == 1


# -----------------------------
# Deadlock tests that need to be fixed
#  (likely need to rewrite the MockCrawler)
# -----------------------------

# -----------------------------
# Test: engine handles retry that eventually succeeds
# -----------------------------
# @pytest.mark.asyncio
# async def test_engine_retry_then_success(monkeypatch):
#     pages = {
#         "http://retry/": b"<html>success</html>",
#     }

#     crawler = MockCrawler(pages=pages)
#     original_submit = crawler.submit

#     # Make submit fail first time, then succeed
#     called = []

#     def submit_side_effect(req):
#         if not called:
#             called.append(True)
#             # Simulate retry by not putting response
#             return
#         original_submit(req)

#     crawler.submit = submit_side_effect

#     monkeypatch.setattr(engine, "Crawler", lambda *a, **k: crawler)

#     eng = WXPathEngine(concurrency=1)
#     results = await _collect_async(eng.run("url('http://retry/')", max_depth=0))

#     # Should eventually yield the page
#     assert results
#     assert b"success" in results[0].body


# -----------------------------
# Test: engine terminates cleanly with no pages
# -----------------------------
# @pytest.mark.asyncio
# async def test_engine_empty_pages(monkeypatch):
#     pages = {}

#     monkeypatch.setattr(
#         engine,
#         "Crawler",
#         lambda *a, **k: MockCrawler(*a, pages=pages, **k),
#     )

#     eng = WXPathEngine(concurrency=2)
#     results = await _collect_async(eng.run("url('http://root/')", max_depth=1))

#     # No results should be returned, but engine should not hang
#     assert results == []


# @pytest.mark.asyncio
# async def test_engine_does_not_hang_on_unexpected_response(monkeypatch):

#     pages = {
#         'http://test/': b"""
#             <html><body>
#               <main><a href="a.html">A</a></main>
#               <a href="b.html">B</a>
#             </body></html>
#         """
#     }

#     monkeypatch.setattr(
#         engine,
#         "Crawler",
#         lambda *a, **k: MockCrawler(*a, pages=pages, **k),
#     )
#     eng = engine.WXPathEngine()

#     # engine.crawler = crawler

#     async def run():
#         async for _ in eng.run("url('http://example.com')", max_depth=0):
#             pass

#     await asyncio.wait_for(run(), timeout=1.0)


# @pytest.mark.asyncio
# async def test_engine_does_not_hang_on_unexpected_response(monkeypatch):
#     class FakeRequest:
#         def __init__(self, url):
#             self.url = url


#     class FakeResponse:
#         def __init__(self, url, body=b"<html></html>", status=200, error=None):
#             self.request = FakeRequest(url)
#             self.body = body
#             self.status = status
#             self.error = error


#     class FakeCrawler:
#         def __init__(self, responses):
#             self._responses = asyncio.Queue()
#             for r in responses:
#                 self._responses.put_nowait(r)

#         async def __aenter__(self):
#             return self

#         async def __aexit__(self, *exc):
#             return False

#         def submit(self, request):
#             pass  # no-op for fake

#         def __aiter__(self):
#             return self

#         async def __anext__(self):
#             if self._responses.empty():
#                 await asyncio.sleep(3600)  # simulate hang
#             return await self._responses.get()
        
#     crawler = FakeCrawler([
#         FakeResponse("http://unexpected.com"),
#     ])

#     eng = engine.WXPathEngine()

#     eng.crawler = crawler

#     async def run():
#         async for _ in eng.run("url('http://example.com')", max_depth=0):
#             pass

#     await asyncio.wait_for(run(), timeout=1.0)



# @pytest.mark.asyncio
# async def test_engine_does_not_hang_on_request_failure(monkeypatch):
#     """
#     Verify that when a request fails after all retries, the engine
#     receives an error Response, yields an error result, and shuts down cleanly
#     instead of hanging.
#     """
#     failing_url = "http://will-always-fail.com"
#     expression = f"url('{failing_url}')"

#     eng = engine.WXPathEngine(concurrency=1)

#     # We patch the crawler's _fetch_one method to simulate a failed request
#     # that has exhausted all retries. The crawler should return a Response
#     # with an error, not raise an exception.
#     error = RuntimeError("All retries failed")
    
#     async def mock_fetch_one(self, req: Request):
#         if req.url == failing_url:
#             # Simulate crawler returning an error response after retries
#             return Response(request=req, status=0, body=b"", error=error)
#         # For any other URL, we can return a success to not interfere
#         return Response(request=req, status=200, body=b"<html></html>")

#     with patch('wxpath.http.client.crawler.Crawler._fetch_one', new=mock_fetch_one):
#         results = []
#         async for result in eng.run(expression, max_depth=0):
#             results.append(result)

#     assert len(results) == 1
#     assert results[0] == {'error': str(error), 'url': failing_url}

#     # The fact that the test completes without timing out proves the engine did not hang.


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

# Tests for WXPathEngine

# @pytest.mark.asyncio
# async def test_engine_deduplication():
#     """
#     Engine should not fetch the same URL twice.
#     """
#     pages = {
#         "http://test.com": 
#           b'<html><body><a href="/page">1</a><a href="/page">2</a></body></html>',
#         "http://test.com/page": b'<html><body>content</body></html>',
#     }
#     crawler = MockCrawler(pages=pages)
#     crawler.submit = MagicMock(wraps=crawler.submit)
#     engine = WXPathEngine()
#     engine.crawler = crawler
    
#     path_expr = "url('http://test.com')//url(@href)"
    
#     results = []
#     async for result in engine.run(path_expr, max_depth=1):
#         results.append(result)

#     # The crawler's submit method should have been called for 'http://test.com' and 'http://test.com/page'
#     assert crawler.submit.call_count == 2
#     urls_submitted = {call.args[0].url for call in crawler.submit.call_args_list}
#     assert urls_submitted == {"http://test.com", "http://test.com/page"}


# @pytest.mark.asyncio
# async def test_engine_handles_crawl_race_condition():
#     """
#     Test that the engine correctly handles a race condition where a URL is
#     queued for crawling multiple times before it has been marked as 'seen'.
#     """
#     pages = {
#         "http://test.com": b'<html><body><a href="http://test.com">self</a><a href="http://test.com/target">target</a></body></html>',
#         "http://test.com/target": b'<html><body>target page</body></html>',
#     }

#     crawler = MockCrawler(pages=pages)
#     crawler.submit = MagicMock(wraps=crawler.submit)
    
#     crawled_pages_queue = asyncio.Queue()

#     original_anext = crawler.__anext__
#     async def controlled_anext():
#         resp = await crawled_pages_queue.get()
#         if resp is None:
#             raise StopAsyncIteration
#         await asyncio.sleep(0) 
#         return resp
    
#     crawler.__anext__ = controlled_anext

#     engine = WXPathEngine()
#     engine.crawler = crawler
#     path_expr = "url('http://test.com')//url(@href)"

#     async def run_crawler():
#         results = []
#         async for result in engine.run(path_expr, max_depth=2):
#             results.append(result)
#         return results

#     crawler_task = asyncio.create_task(run_crawler())

#     await asyncio.sleep(0.01)
    
#     resp1 = await original_anext()
#     await crawled_pages_queue.put(resp1)
#     await asyncio.sleep(0.01)

#     resp2 = await original_anext()
#     await crawled_pages_queue.put(resp2)
    
#     await asyncio.sleep(0.01)
#     await crawled_pages_queue.put(None) 
    
#     results = await crawler_task
    
#     assert crawler.submit.call_count == 2
#     urls_submitted = {call.args[0].url for call in crawler.submit.call_args_list}
#     assert urls_submitted == {"http://test.com", "http://test.com/target"}
    
#     # We should get two results (the elements for the two pages)
#     result_urls = {r.base_url for r in results}
#     assert result_urls == {"http://test.com", "http://test.com/target"}
#     assert len(results) == 2

# @pytest.mark.asyncio
# async def test_engine_hangs_on_url_mismatch_with_non_terminating_crawler():
#     """
#     If a response URL does not match the inflight key AND
#     the crawler iterator never terminates, the engine hangs.
#     """

#     from wxpath.core.runtime.engine import WXPathEngine
#     from wxpath.http.client.response import Response
#     from wxpath.http.client.request import Request

#     class HangingMismatchCrawler:
#         async def __aenter__(self): return self
#         async def __aexit__(self, *_): pass

#         def submit(self, req):
#             self._submitted = True

#         def __aiter__(self):
#             async def gen():
#                 # First response: URL mismatch
#                 yield Response(
#                     Request("http://example.com/"),
#                     200,
#                     b"<html></html>"
#                 )
#                 # Then hang forever (like real crawler does)
#                 # while True:
#                 await asyncio.sleep(1)
#             return gen()

#     eng = WXPathEngine()
#     eng.crawler = HangingMismatchCrawler()

#     async def run():
#         async for _ in eng.run("url('http://example.com')", max_depth=0):
#             pass
    
#     with pytest.raises(asyncio.TimeoutError):
#         await asyncio.wait_for(run(), timeout=0.3)