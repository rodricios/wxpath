import pytest
from wxpath.core import (
    parse_wxpath_expr,
    extract_arg_from_url_xpath_op,
    make_links_absolute,
)

from wxpath.core import evaluate_wxpath_bfs_iter
from lxml import html


def test_parse_wxpath_expr_single_url():
    expr = "url('http://example.com')"
    assert parse_wxpath_expr(expr) == [
        ('url', 'http://example.com')
    ]


def test_parse_wxpath_expr_mixed_segments():
    expr = (
        "url('https://en.wikipedia.org/wiki/Expression_language')"
        "//url(@href[starts-with(., '/wiki/')])"
        "//url(@href)"
    )
    expected = [
        ('url', 'https://en.wikipedia.org/wiki/Expression_language'),
        ('url_from_attr', "//url(@href[starts-with(., '/wiki/')])"),
        ('url_from_attr', "//url(@href)"),
    ]
    assert parse_wxpath_expr(expr) == expected


def test_extract_arg_with_quotes():
    assert extract_arg_from_url_xpath_op("url('abc')") == 'abc'
    assert extract_arg_from_url_xpath_op('url("def")') == 'def'


def test_extract_arg_without_quotes():
    assert extract_arg_from_url_xpath_op('url(xyz)') == 'xyz'


def test_extract_arg_invalid_raises():
    with pytest.raises(ValueError):
        extract_arg_from_url_xpath_op('url()')


def test_make_links_absolute():
    links = ['a.html', 'http://example.com/b']
    base = 'http://example.com/path/index.html'
    got = make_links_absolute(links, base)
    assert got == [
        'http://example.com/path/a.html',
        'http://example.com/b'
    ]


def test_evaluate_wxpath_bfs_iter_url_with_elem_raises():
    elem = html.fromstring("<div></div>")
    segments = [('url', 'http://example.com')]
    with pytest.raises(ValueError) as excinfo:
        list(evaluate_wxpath_bfs_iter(elem, segments))
    assert "Cannot use 'url()' at the start of path_expr with an element provided." in str(excinfo.value)

def test_evaluate_wxpath_bfs_iter_url_from_attr_without_elem_raises():
    segments = [('url_from_attr', "//url(@href)")]
    with pytest.raises(ValueError) as excinfo:
        list(evaluate_wxpath_bfs_iter(None, segments))
    assert "Element must be provided when op is 'url_from_attr'." in str(excinfo.value)

def test_evaluate_wxpath_bfs_iter_url_from_attr_invalid_arg():
    elem = html.fromstring("<div></div>")
    segments = [('url_from_attr', "//url(abc)")]
    with pytest.raises(ValueError) as excinfo:
        list(evaluate_wxpath_bfs_iter(elem, segments))
    assert "Only '@*' is supported in url() segments not at the start of path_expr." in str(excinfo.value)

def test_evaluate_wxpath_bfs_iter_unknown_op():
    elem = html.fromstring("<div></div>")
    segments = [('foo', 'bar')]
    with pytest.raises(ValueError) as excinfo:
        list(evaluate_wxpath_bfs_iter(elem, segments))
    assert "Unknown operation: foo" in str(excinfo.value)


def test_evaluate_wxpath_bfs_iter_crawl_two_levels(monkeypatch):
    # 1: define page HTML
    pages = {
        'http://test/': b"""
            <html><body>
              <a href="a.html">A</a>
              <a href="b.html">B</a>
            </body></html>
        """,
        'http://test/a.html': b"<html><body><p>Page A</p></body></html>",
        'http://test/b.html': b"<html><body><p>Page B</p></body></html>",
    }

    # 2: stub out fetch_html
    def fake_fetch_html(url):
        try:
            return pages[url]
        except KeyError:
            raise AssertionError(f"Unexpected URL fetched: {url}")
    monkeypatch.setattr('wxpath.core.fetch_html', fake_fetch_html)

    # 3: build & run
    expr = "url('http://test/')//url(@href)"
    segments = parse_wxpath_expr(expr)
    results = list(evaluate_wxpath_bfs_iter(None, segments, max_depth=1))

    # 4: verify BFS order and base_url propagation
    assert len(results) == 2
    assert [e.base_url for e in results] == [
        'http://test/a.html',
        'http://test/b.html',
    ]
    

def test_evaluate_wxpath_bfs_iter_crawl_three_levels(monkeypatch):
    pages = {
      'http://test/': b"<html><body><a href='lvl1.html'>L1</a></body></html>",
      'http://test/lvl1.html': b"<html><body><a href='lvl2.html'>L2</a></body></html>",
      'http://test/lvl2.html': b"<html><body><p>Reached L2</p></body></html>",
    }

    def fake_fetch_html(url):
        try:
            return pages[url]
        except KeyError:
            raise AssertionError(f"Unexpected URL fetched: {url}")
    monkeypatch.setattr('wxpath.core.fetch_html', fake_fetch_html)

    expr = "url('http://test/')//url(@href)//url(@href)"
    segments = parse_wxpath_expr(expr)
    results = list(evaluate_wxpath_bfs_iter(None, segments, max_depth=2))

    assert len(results) == 1
    assert results[0].base_url == 'http://test/lvl2.html'
    

def test_evaluate_wxpath_bfs_iter_crawl_two_levels_and_query(monkeypatch):
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
    
    def fake_fetch_html(url):
        try:
            return pages[url]
        except KeyError:
            raise AssertionError(f"Unexpected URL fetched: {url}")
    monkeypatch.setattr('wxpath.core.fetch_html', fake_fetch_html)

    expr = "url('http://test/')//url(@href)//a/@href"
    segments = parse_wxpath_expr(expr)
    results = list(evaluate_wxpath_bfs_iter(None, segments, max_depth=1))

    assert len(results) == 2
    assert results == [
        'page1.html',
        'page2.html',
    ]
    
def test_evaluate_wxpath_bfs_iter_crawl_three_levels_and_query(monkeypatch):
    pages = {
      'http://test/': b"<html><body><a href='lvl1.html'>L1</a></body></html>",
      'http://test/lvl1.html': b"<html><body><a href='lvl2.html'>L2</a></body></html>",
      'http://test/lvl2.html': b"<html><body><a href='lvl3.html'>L3</a></body></html>",
      'http://test/lvl3.html': b"<html><body><p>Reached L3</p></body></html>",
    }

    def fake_fetch_html(url):
        try:
            return pages[url]
        except KeyError:
            raise AssertionError(f"Unexpected URL fetched: {url}")
    monkeypatch.setattr('wxpath.core.fetch_html', fake_fetch_html)

    expr = "url('http://test/')//url(@href)//url(@href)//a/@href"
    segments = parse_wxpath_expr(expr)
    results = list(evaluate_wxpath_bfs_iter(None, segments, max_depth=2))

    assert len(results) == 1
    assert results[0] == 'lvl3.html'


# Test multiple crawls with filtered (e.g., `url(@href[starts-with(., '/wiki/')])`) crawl
def test_evaluate_wxpath_bfs_iter_filtered_crawl(monkeypatch):
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
    
    def fake_fetch_html(url):
        try:
            return pages[url]
        except KeyError:
            raise AssertionError(f"Unexpected URL fetched: {url}")
    monkeypatch.setattr('wxpath.core.fetch_html', fake_fetch_html)

    expr = "url('http://test/')//url(@href[starts-with(., 'lvl1a')])//a/@href"
    segments = parse_wxpath_expr(expr)
    results = list(evaluate_wxpath_bfs_iter(None, segments, max_depth=2))

    assert len(results) == 1
    assert results[0] == 'lvl2.html'


# Test infinite crawl using ///url()
def test_evaluate_wxpath_bfs_iter_infinite_crawl_max_depth_uncapped(monkeypatch):
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
    
    def fake_fetch_html(url):
        try:
            return pages[url]
        except KeyError:
            raise AssertionError(f"Unexpected URL fetched: {url}")
    monkeypatch.setattr('wxpath.core.fetch_html', fake_fetch_html)

    expr = "url('http://test/')///url(@href)"
    segments = parse_wxpath_expr(expr)
    results = list(evaluate_wxpath_bfs_iter(None, segments, max_depth=9999))

    assert len(results) == 4
    assert [e.base_url for e in results] == [
        'http://test/a.html',
        'http://test/b.html',
        'http://test/a1.html',
        'http://test/b1.html',
    ]


def test_evaluate_wxpath_bfs_iter_infinite_crawl_max_depth_1(monkeypatch):
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
    
    def fake_fetch_html(url):
        try:
            return pages[url]
        except KeyError:
            raise AssertionError(f"Unexpected URL fetched: {url}")
    monkeypatch.setattr('wxpath.core.fetch_html', fake_fetch_html)

    expr = "url('http://test/')///url(@href)"
    segments = parse_wxpath_expr(expr)
    results = list(evaluate_wxpath_bfs_iter(None, segments, max_depth=1))

    assert len(results) == 2
    assert [e.base_url for e in results] == [
        'http://test/a.html',
        'http://test/b.html',
    ]

def test_evaluate_wxpath_bfs_iter_infinite_crawl_and_query_max_depth_1(monkeypatch):
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
    
    def fake_fetch_html(url):
        try:
            return pages[url]
        except KeyError:
            raise AssertionError(f"Unexpected URL fetched: {url}")
    monkeypatch.setattr('wxpath.core.fetch_html', fake_fetch_html)

    expr = "url('http://test/')///url(@href)//a/@href"
    segments = parse_wxpath_expr(expr)
    results = list(evaluate_wxpath_bfs_iter(None, segments, max_depth=1))

    assert len(results) == 2
    assert results == [
        'a1.html',
        'b1.html',
    ]

# TODO: refactor with fixtures
def test_evaluate_wxpath_bfs_iter_infinite_crawl_and_query_max_depth_2(monkeypatch):
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
    
    def fake_fetch_html(url):
        try:
            return pages[url]
        except KeyError:
            raise AssertionError(f"Unexpected URL fetched: {url}")
    monkeypatch.setattr('wxpath.core.fetch_html', fake_fetch_html)

    expr = "url('http://test/')///url(@href)//a/@href"
    segments = parse_wxpath_expr(expr)
    results = list(evaluate_wxpath_bfs_iter(None, segments, max_depth=2))

    assert len(results) == 4
    assert results == [
        'a1.html',
        'b1.html',
        'a2.html',
        'b2.html',
    ]


# Test evaluate_wxpath_bfs_iter() with filtered (argument) infinite crawl
def test_evaluate_wxpath_bfs_iter_filtered_infinite_crawl(monkeypatch):
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
    
    def fake_fetch_html(url):
        try:
            return pages[url]
        except KeyError:
            raise AssertionError(f"Unexpected URL fetched: {url}")
    monkeypatch.setattr('wxpath.core.fetch_html', fake_fetch_html)




# Raises when there are multiple ///url() segments
def test_parse_wxpath_expr_multiple_inf_url_segments():
    expr = "url('http://example.com/')///url(@href)///url(@href)"
    with pytest.raises(ValueError) as excinfo:
        parse_wxpath_expr(expr)
    assert "Only one ///url() is allowed" in str(excinfo.value)


# Raise error if url() with fixed-length argument is preceded by navigation slashes
def test_parse_wxpath_expr_fixed_length_url_preceded_by_slashes():
    expr = "url('http://example.com/')//url('http://example2.com/')"
    with pytest.raises(ValueError) as excinfo:
        parse_wxpath_expr(expr)
    assert \
        "url() segment cannot have fixed-length argument and preceding navigation slashes (/|//): //url('http://example2.com/')" \
        in str(excinfo.value)
    

# Raises when expr starts with //url_from_attr()
def test_parse_wxpath_expr_url_from_attr_without_elem():
    expr = "//url(@href)"
    with pytest.raises(ValueError) as excinfo:
        parse_wxpath_expr(expr)
    assert "Path expr cannot start with [//]url(@<attr>)" in str(excinfo.value)