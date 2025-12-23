import pytest
from lxml import html

from wxpath.core import ops
from wxpath.core.models import CrawlIntent, DataIntent, ProcessIntent, InfiniteCrawlIntent


# ---------------------------------------------------------------------------
# Registry basics
# ---------------------------------------------------------------------------
def test_get_operator_registry():
    assert callable(ops.get_operator("xpath"))
    assert callable(ops.get_operator("url_from_attr"))
    assert callable(ops.get_operator("url_inf"))
    assert callable(ops.get_operator("url_inf_and_xpath"))

    with pytest.raises(ValueError):
        ops.get_operator("does_not_exist")


# ---------------------------------------------------------------------------
# _handle_url_from_attr__no_return
# ---------------------------------------------------------------------------
def test_url_from_attr_yields_crawl_intents(monkeypatch):
    def fake_links(elem, xpath_expr):
        return ["http://test/a.html", "http://test/b.html"]

    monkeypatch.setattr(ops, "get_absolute_links_from_elem_and_xpath", fake_links)

    elem = html.fromstring("<html><body></body></html>", base_url="http://test/")
    rest_segments = [("xpath", "//p/text()")]

    op = ops.get_operator("url_from_attr")
    results = list(op(elem, [("url_from_attr", "//url(@href)")] + rest_segments, 0))

    assert len(results) == 2
    for intent in results:
        assert isinstance(intent, CrawlIntent)
        assert intent.next_segments == rest_segments
        assert intent.url in ["http://test/a.html", "http://test/b.html"]


# ---------------------------------------------------------------------------
# _handle_url_inf__no_return
# ---------------------------------------------------------------------------
def test_url_inf_yields_infinite_crawl_intents(monkeypatch):
    def fake_links(elem, xpath_expr):
        return ["http://test/a.html"]

    monkeypatch.setattr(ops, "get_absolute_links_from_elem_and_xpath", fake_links)

    elem = html.fromstring("<html><body></body></html>", base_url="http://test/")
    rest_segments = [("xpath", "//p/text()")]

    op = ops.get_operator("url_inf")
    value = "///url(//main//a/@href)"
    results = list(op(elem, [("url_inf", value)] + rest_segments, 0, dedupe_urls_per_page=True))

    assert len(results) == 1
    intent = results[0]
    assert isinstance(intent, CrawlIntent)
    first_op, first_val = intent.next_segments[0]
    assert first_op == "url_inf_and_xpath"
    assert first_val == ("http://test/a.html", value)


# ---------------------------------------------------------------------------
# _handle_url_inf_and_xpath__no_return
# ---------------------------------------------------------------------------
def test_url_inf_and_xpath_yields_data_and_infinite(monkeypatch):
    elem = html.fromstring("<html><body></body></html>", base_url="http://test/")
    rest_segments = [("xpath", "//p/text()")]
    op = ops.get_operator("url_inf_and_xpath")
    value = ("http://test/a.html", "//main//a/@href")
    results = list(op(elem, [("url_inf_and_xpath", value)] + rest_segments, 0))

    assert any(isinstance(r, (DataIntent, ProcessIntent, InfiniteCrawlIntent)) for r in results)


# ---------------------------------------------------------------------------
# _handle_xpath
# ---------------------------------------------------------------------------
def test_xpath_yields_wxstr_for_string_results():
    elem = html.fromstring("<html><body></body></html>", base_url="http://test/")
    elem.set("backlink", "http://test/")
    elem.getroottree().getroot().set("depth", "3")

    class DummyElem:
        def __init__(self, elem):
            self._elem = elem
        def __getattr__(self, name):
            return getattr(self._elem, name)
        def xpath3(self, value):
            return ["hello"]

    delem = DummyElem(elem)
    op = ops.get_operator("xpath")
    results = list(op(delem, [("xpath", "//p/text()")], 1))

    assert len(results) == 1
    s = results[0]

    assert hasattr(s.value, "base_url")
    assert hasattr(s.value, "depth")
    assert str(s.value) == "hello"


def test_xpath_macro_expansion_applied():
    elem = html.fromstring("<html><body></body></html>", base_url="http://site/page")
    elem.set("backlink", "http://site/page")
    elem.getroottree().getroot().set("depth", "2")

    class DummyElem:
        def __init__(self, elem):
            self._elem = elem
            self.captured = None
        def __getattr__(self, name):
            return getattr(self._elem, name)
        def xpath3(self, value):
            self.captured = value
            return []

    delem = DummyElem(elem)
    op = ops.get_operator("xpath")
    list(op(delem, [("xpath", "wx:backlink() and wx:depth()")], 7))
    assert "string('" in delem.captured
    assert "number(2)" in delem.captured