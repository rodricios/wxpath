import pytest
from lxml import html

from wxpath.core import ops
from wxpath.core.models import CrawlIntent, DataIntent, InfiniteCrawlIntent, ProcessIntent
from wxpath.core.ops import OPS
from wxpath.core.parser import UrlInfAndXPathValue, XPathValue


# ---------------------------------------------------------------------------
# Registry basics
# ---------------------------------------------------------------------------
def test_get_operator_registry():
    assert callable(ops.get_operator(OPS.XPATH))
    assert callable(ops.get_operator(OPS.URL_EVAL))
    assert callable(ops.get_operator(OPS.URL_INF))
    assert callable(ops.get_operator(OPS.URL_INF_AND_XPATH))

    with pytest.raises(ValueError):
        ops.get_operator("does_not_exist")


# ---------------------------------------------------------------------------
# _handle_xpath_fn_map_frag
# ---------------------------------------------------------------------------
def test_xpath_fn_map_frag_yields_data_intents(monkeypatch):
    rest_segments = [(OPS.URL_EVAL, "url(.)")]

    op = ops.get_operator(OPS.XPATH_FN_MAP_FRAG)
    results = list(op(None, [(OPS.XPATH_FN_MAP_FRAG, 
                              XPathValue('', "(1 to 3)"))] + rest_segments, 
                              0))

    assert len(results) == 3
    assert isinstance(results[0], ProcessIntent)
    assert isinstance(results[1], ProcessIntent)
    assert isinstance(results[2], ProcessIntent)

    assert results[0].next_segments == rest_segments
    assert results[1].next_segments == rest_segments
    assert results[2].next_segments == rest_segments

    assert str(results[0].elem) == "1"
    assert str(results[1].elem) == "2"
    assert str(results[2].elem) == "3"


# ---------------------------------------------------------------------------
# _handle_url_eval
# ---------------------------------------------------------------------------
def test_url_eval_yields_crawl_intents(monkeypatch):
    def fake_links(elem, xpath_expr):
        return ["http://test/a.html", "http://test/b.html"]

    monkeypatch.setattr(ops, "get_absolute_links_from_elem_and_xpath", fake_links)

    elem = html.fromstring("<html><body></body></html>", base_url="http://test/")
    rest_segments = [(OPS.XPATH, XPathValue('', "//p/text()"))]

    op = ops.get_operator(OPS.URL_EVAL)
    results = list(op(elem, [(OPS.URL_EVAL, XPathValue(',', "//url(@href)"))] + rest_segments, 0))

    assert len(results) == 2
    for intent in results:
        assert isinstance(intent, CrawlIntent)
        assert intent.next_segments == rest_segments
        assert intent.url in ["http://test/a.html", "http://test/b.html"]


# ---------------------------------------------------------------------------
# _handle_url_inf
# ---------------------------------------------------------------------------
def test_url_inf_yields_infinite_crawl_intents(monkeypatch):
    def fake_links(elem, xpath_expr):
        return ["http://test/a.html"]

    monkeypatch.setattr(ops, "get_absolute_links_from_elem_and_xpath", fake_links)

    elem = html.fromstring("<html><body></body></html>", base_url="http://test/")
    rest_segments = [(OPS.XPATH, XPathValue('', "//p/text()"))]

    op = ops.get_operator(OPS.URL_INF)
    value = "///url(//main//a/@href)"
    results = list(op(elem, [(OPS.URL_INF, XPathValue('', value))] + rest_segments, 0))

    assert len(results) == 1
    intent = results[0]
    assert isinstance(intent, CrawlIntent)
    first_op, first_val = intent.next_segments[0]
    assert first_op == OPS.URL_INF_AND_XPATH
    assert first_val == UrlInfAndXPathValue('', "http://test/a.html", value)


# ---------------------------------------------------------------------------
# _handle_url_inf_and_xpath
# ---------------------------------------------------------------------------
def test_url_inf_and_xpath_yields_data_and_infinite(monkeypatch):
    elem = html.fromstring("<html><body></body></html>", base_url="http://test/")
    rest_segments = [(OPS.XPATH, "//p/text()")]
    op = ops.get_operator(OPS.URL_INF_AND_XPATH)
    value = UrlInfAndXPathValue('', "http://test/a.html", "//main//a/@href")
    results = list(op(elem, [(OPS.URL_INF_AND_XPATH, value)] + rest_segments, 0))

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
    op = ops.get_operator(OPS.XPATH)
    results = list(op(delem, [(OPS.XPATH, XPathValue('', "//p/text()"))], 1))

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
    op = ops.get_operator(OPS.XPATH)
    list(op(delem, [(OPS.XPATH, XPathValue('', "wx:backlink() and wx:depth()"))], 7))
    assert "string('" in delem.captured
    assert "number(2)" in delem.captured