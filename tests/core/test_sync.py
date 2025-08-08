import pytest
from lxml import html

from tests.utils import _generate_fake_fetch_html
from wxpath.core.errors import use_error_policy, ErrorPolicy
from wxpath.core.sync import evaluate_wxpath_bfs_iter
from wxpath.core.helpers import _make_links_absolute
from wxpath.core.parser import (
    _extract_arg_from_url_xpath_op, 
    parse_wxpath_expr
)


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


def test_parse_wxpath_expr_filtered_inf_url_equality_filter():
    path_expr_1 = "url('https://en.wikipedia.org/wiki/Expression_language')///main//a/url(@href)"
    # The same expression written differently:
    path_expr_2 = "url('https://en.wikipedia.org/wiki/Expression_language')///url(//main//a/@href)"
    assert parse_wxpath_expr(path_expr_1) == parse_wxpath_expr(path_expr_2)


def test_extract_arg_with_quotes():
    assert _extract_arg_from_url_xpath_op("url('abc')") == 'abc'
    assert _extract_arg_from_url_xpath_op('url("def")') == 'def'


def test_extract_arg_without_quotes():
    assert _extract_arg_from_url_xpath_op('url(xyz)') == 'xyz'


def test_extract_arg_invalid_raises():
    with pytest.raises(ValueError):
        _extract_arg_from_url_xpath_op('url()')


def test_make_links_absolute():
    links = ['a.html', 'http://example.com/b']
    base = 'http://example.com/path/index.html'
    got = _make_links_absolute(links, base)
    assert got == [
        'http://example.com/path/a.html',
        'http://example.com/b'
    ]


def test_evaluate_wxpath_bfs_iter_url_with_elem_raises():
    elem = html.fromstring("<div></div>")
    segments = [('url', 'http://example.com')]
    
    with use_error_policy(ErrorPolicy.RAISE):
        with pytest.raises(ValueError) as excinfo:
            list(evaluate_wxpath_bfs_iter(elem, segments))
    assert "Cannot use 'url()' at the start of path_expr with an element provided." in str(excinfo.value)

def test_evaluate_wxpath_bfs_iter_url_from_attr_without_elem_raises():
    segments = [('url_from_attr', "//url(@href)")]
    with use_error_policy(ErrorPolicy.RAISE):
        with pytest.raises(ValueError) as excinfo:
            list(evaluate_wxpath_bfs_iter(None, segments))
    assert "Element must be provided when op is 'url_from_attr'." in str(excinfo.value)

def test_evaluate_wxpath_bfs_iter_url_from_attr_invalid_arg():
    elem = html.fromstring("<div></div>")
    segments = [('url_from_attr', "//url(abc)")]
    with use_error_policy(ErrorPolicy.RAISE):
        with pytest.raises(ValueError) as excinfo:
            list(evaluate_wxpath_bfs_iter(elem, segments))
    assert "Only '@*' is supported in url() segments not at the start of path_expr." in str(excinfo.value)

def test_evaluate_wxpath_bfs_iter_unknown_op():
    elem = html.fromstring("<div></div>")
    segments = [('foo', 'bar')]
    with use_error_policy(ErrorPolicy.RAISE):
        with pytest.raises(ValueError) as excinfo:
            list(evaluate_wxpath_bfs_iter(elem, segments))
    assert "Unknown operation: foo" in str(excinfo.value)


def test_evaluate_wxpath_bfs_iter_crawl_one_level(monkeypatch):
    # 1: define page HTML
    pages = {
        'http://test/': b"<html><body><p>Page A</p></body></html>",
    }

    # 2: stub out fetch_html
    monkeypatch.setattr('wxpath.core.helpers.fetch_html', _generate_fake_fetch_html(pages))

    # 3: build & run
    expr = "url('http://test/')"
    segments = parse_wxpath_expr(expr)
    results = list(evaluate_wxpath_bfs_iter(None, segments, max_depth=1))

    # 4: verify BFS order and base_url propagation
    assert len(results) == 1
    assert results[0].get('depth') == '0'
    assert results[0].base_url == 'http://test/'


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
    monkeypatch.setattr('wxpath.core.helpers.fetch_html', _generate_fake_fetch_html(pages))

    # 3: build & run
    expr = "url('http://test/')//url(@href)"
    segments = parse_wxpath_expr(expr)
    results = list(evaluate_wxpath_bfs_iter(None, segments, max_depth=1))

    # 4: verify BFS order and base_url propagation
    assert len(results) == 2
    assert results[0].get('depth') == '1'
    assert results[1].get('depth') == '1'
    assert [e.base_url for e in results] == [
        'http://test/a.html',
        'http://test/b.html',
    ]


def test_evaluate_wxpath_bfs_iter__crawl_xpath_crawl(monkeypatch):
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

    # 2: stub out fetch_html
    monkeypatch.setattr('wxpath.core.helpers.fetch_html', _generate_fake_fetch_html(pages))

    # 3: build & run
    expr = "url('http://test/')//main//a/url(@href)"
    segments = parse_wxpath_expr(expr)
    results = list(evaluate_wxpath_bfs_iter(None, segments, max_depth=1))

    # 4: verify BFS order and base_url propagation
    assert len(results) == 2
    assert results[0].get('depth') == '1'
    assert results[1].get('depth') == '1'
    assert [e.base_url for e in results] == [
        'http://test/a1.html',
        'http://test/a2.html',
    ]


def test_evaluate_wxpath_bfs_iter_crawl_three_levels(monkeypatch):
    pages = {
      'http://test/': b"<html><body><a href='lvl1.html'>L1</a></body></html>",
      'http://test/lvl1.html': b"<html><body><a href='lvl2.html'>L2</a></body></html>",
      'http://test/lvl2.html': b"<html><body><p>Reached L2</p></body></html>",
    }

    monkeypatch.setattr('wxpath.core.helpers.fetch_html', _generate_fake_fetch_html(pages))

    expr = "url('http://test/')//url(@href)//url(@href)"
    segments = parse_wxpath_expr(expr)
    results = list(evaluate_wxpath_bfs_iter(None, segments, max_depth=2))

    assert len(results) == 1
    assert results[0].get('depth') == '2'
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
    
    monkeypatch.setattr('wxpath.core.helpers.fetch_html', _generate_fake_fetch_html(pages))

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

    monkeypatch.setattr('wxpath.core.helpers.fetch_html', _generate_fake_fetch_html(pages))

    expr = "url('http://test/')//url(@href)//url(@href)//a/@href"
    segments = parse_wxpath_expr(expr)
    results = list(evaluate_wxpath_bfs_iter(None, segments, max_depth=2))

    assert len(results) == 1
    assert results[0] == 'lvl3.html'


def test_evaluate_wxpath_bfs_iter_crawl_four_levels_and_query_and_max_depth_2(monkeypatch):
    pages = {
      'http://test/': b"<html><body><a href='lvl1.html'>L1</a></body></html>",
      'http://test/lvl1.html': b"<html><body><a href='lvl2.html'>L2</a></body></html>",
      'http://test/lvl2.html': b"<html><body><a href='lvl3.html'>L3</a></body></html>",
      'http://test/lvl3.html': b"<html><body><a href='lvl4.html'>L4</a></body></html>",
      'http://test/lvl4.html': b"<html><body><a href='lvl5.html'>L4</a></body></html>",
    }

    monkeypatch.setattr('wxpath.core.helpers.fetch_html', _generate_fake_fetch_html(pages))

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
    
    monkeypatch.setattr('wxpath.core.helpers.fetch_html', _generate_fake_fetch_html(pages))

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
    
    monkeypatch.setattr('wxpath.core.helpers.fetch_html', _generate_fake_fetch_html(pages))

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
    
    monkeypatch.setattr('wxpath.core.helpers.fetch_html', _generate_fake_fetch_html(pages))

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
    
    monkeypatch.setattr('wxpath.core.helpers.fetch_html', _generate_fake_fetch_html(pages))

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
    
    monkeypatch.setattr('wxpath.core.helpers.fetch_html', _generate_fake_fetch_html(pages))

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


# Test evaluate_wxpath_bfs_iter() with filtered (argument) infinite crawl - type 1
def test_evaluate_wxpath_bfs_iter_infinite_crawl_with_inf_filter_before_url_op(monkeypatch):
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
    
    monkeypatch.setattr('wxpath.core.helpers.fetch_html', _generate_fake_fetch_html(pages))
    
    expr = "url('http://test/')///main/a/url(@href)"
    segments = parse_wxpath_expr(expr)
    results = list(evaluate_wxpath_bfs_iter(None, segments, max_depth=2))

    assert len(results) == 2
    assert [e.base_url for e in results] == [
        'http://test/a.html',
        'http://test/a1.html'
    ]
    
# Test evaluate_wxpath_bfs_iter() with filtered (argument) infinite crawl - type 1
def test_evaluate_wxpath_bfs_iter__crawl_xpath_crawl_max_depth_1(monkeypatch):
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
    
    monkeypatch.setattr('wxpath.core.helpers.fetch_html', _generate_fake_fetch_html(pages))
    
    expr = "url('http://test/')///main/a/url(@href)"
    segments = parse_wxpath_expr(expr)
    results = list(evaluate_wxpath_bfs_iter(None, segments, max_depth=1))

    assert len(results) == 1
    assert results[0].get('depth') == '1'
    assert [e.base_url for e in results] == [
        'http://test/a.html'
    ]


# Test evaluate_wxpath_bfs_iter() with filtered (argument) infinite crawl - type 2
def test_evaluate_wxpath_bfs_iter__crawl_inf_crawl_with_filter(monkeypatch): #infinite_crawl_with_inf_filter_as_url_op_arg(monkeypatch):
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
    
    monkeypatch.setattr('wxpath.core.helpers.fetch_html', _generate_fake_fetch_html(pages))
    
    expr = "url('http://test/')///url(//main/a/@href)"
    segments = parse_wxpath_expr(expr)
    results = list(evaluate_wxpath_bfs_iter(None, segments, max_depth=2))

    assert len(results) == 2
    assert [e.get('depth') for e in results if e.base_url == 'http://test/a.html'] == ['1']
    assert [e.get('depth') for e in results if e.base_url == 'http://test/a1.html'] == ['2']
    assert [e.base_url for e in results] == [
        'http://test/a.html',
        'http://test/a1.html'
    ]


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


def test_parse_wxpath_expr_object_segment():
    expr = "url('http://example.com')/map{ 'title':string(//h1/text()) }"
    parsed = parse_wxpath_expr(expr)
    assert parsed == [
        ('url', 'http://example.com'),
        ('xpath', "/map{ 'title':string(//h1/text()) }"),
    ]


def test_evaluate_wxpath_bfs_iter_object_extraction(monkeypatch):
    pages = {
        'http://test/': b"""
            <html><body>
              <h1>The Test Page</h1>
              <p>Alpha</p><p>Beta</p>
            </body></html>
        """
    }

    monkeypatch.setattr('wxpath.core.helpers.fetch_html', _generate_fake_fetch_html(pages))

    expr = (
        "url('http://test/')/map { "
        "'title'://h1/text()/string(), "
        "'paragraphs'://p/text() "
        "}"
    )
    segments = parse_wxpath_expr(expr)
    results = list(evaluate_wxpath_bfs_iter(None, segments, max_depth=0))

    assert len(results) == 1
    obj = results[0]
    assert obj['title'] == 'The Test Page'
    assert obj['paragraphs'] == ['Alpha', 'Beta']


def test_evaluate_wxpath_bfs_iter_object_indexing(monkeypatch):
    pages = {
        'http://test/': b"""
            <html><body>
              <p>One</p><p>Two</p><p>Three</p>
            </body></html>
        """
    }

    monkeypatch.setattr('wxpath.core.helpers.fetch_html', _generate_fake_fetch_html(pages))

    expr = (
        "url('http://test/')/ map{ "
        "'first':string((//p/text())[1]), "
        "'second':string((//p/text())[2]), "
        "'all'://p/text() "
        "}"
    )
    segments = parse_wxpath_expr(expr)
    results = list(evaluate_wxpath_bfs_iter(None, segments, max_depth=0))

    assert len(results) == 1
    obj = results[0]
    assert obj['first'] == 'One'
    assert obj['second'] == 'Two'
    assert obj['all'] == ['One', 'Two', 'Three']