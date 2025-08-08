# tests/test_op_handlers.py
import pytest
from lxml import html

from wxpath.core.task import Task
from wxpath.core import async_  # ensures patches (xpath3) are installed globally
from wxpath.core import op_handlers as ops


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
class DummyElem:
    """Wrap a real HtmlElement and allow overriding xpath3 in tests.

    Not subclassing HtmlElement avoids lxml C-level properties (like base_url)
    from trying to operate on a non-tree-backed proxy instance.
    """
    def __init__(self, elem):
        self._elem = elem

    def __getattr__(self, name):
        return getattr(self._elem, name)

    def xpath3(self, value):  # default: delegate to normal xpath
        return self._elem.xpath(value)


# ---------------------------------------------------------------------------
# Registry basics
# ---------------------------------------------------------------------------
def test_get_operator_registry():
    assert callable(ops.get_operator("url"))
    with pytest.raises(ValueError):
        ops.get_operator("does_not_exist")


# ---------------------------------------------------------------------------
# _handle_url
# ---------------------------------------------------------------------------
def test_handle_url_enqueues_next_task(monkeypatch):
    q = []
    seen = set()

    def fake_load(url, backlink, depth, _seen):
        el = html.fromstring("<html><body></body></html>", base_url=url)
        return el

    monkeypatch.setattr(ops, "_load_page_as_element", fake_load)

    op = ops.get_operator("url")
    rest = [("xpath", "//p/text()")]
    gen = op(
        curr_elem=None,
        curr_segments=[("url", "http://test/")] + rest,
        curr_depth=0,
        queue=q,
        backlink=None,
        max_depth=1,
        seen_urls=seen,
    )

    assert list(gen) == []  # realize generator for side effects
    assert len(q) == 1
    t = q[0]
    assert isinstance(t, Task)
    assert t.depth == 1               # incremented
    assert t.segments == rest         # moved to next segment(s)
    assert t.backlink == "http://test/"


def test_handle_url_yields_on_max_depth(monkeypatch):
    seen = set()

    def fake_load(url, backlink, depth, _seen):
        el = html.fromstring("<html><body><p>A</p></body></html>", base_url=url)
        return el

    monkeypatch.setattr(ops, "_load_page_as_element", fake_load)

    op = ops.get_operator("url")
    q = []
    gen = op(None, [("url", "http://test/")], 1, q, None, 0, seen)
    out = list(gen)

    assert len(out) == 1
    assert getattr(out[0], "base_url", None) == "http://test/"
    assert q == []


# ---------------------------------------------------------------------------
# _handle_url_from_attr__no_return
# ---------------------------------------------------------------------------
def test_url_from_attr_enqueues_urls(monkeypatch):
    q = []
    seen = set()

    def fake_links(elem, xpath_expr):
        return [
            "http://test/a.html",
            "http://test/b.html",
        ]

    monkeypatch.setattr(ops, "_get_absolute_links_from_elem_and_xpath", fake_links)

    curr = html.fromstring("<html><body></body></html>", base_url="http://test/")
    rest = [("xpath", "//p/text()")]

    op = ops.get_operator("url_from_attr")
    gen = op(curr, [("url_from_attr", "//url(@href)")] + rest, 0, q, curr.base_url, 2, seen)
    assert gen is None

    assert len(q) == 2
    urls = [task.segments[0][1] for task in q]
    assert urls == ["http://test/a.html", "http://test/b.html"]
    assert all(t.depth == 0 for t in q)                 # depth unchanged
    assert all(t.backlink == curr.base_url for t in q)  # backlink preserved


# ---------------------------------------------------------------------------
# _handle_url_inf__no_return
# ---------------------------------------------------------------------------
def test_url_inf_enqueues_inf_and_xpath(monkeypatch):
    q = []
    seen = set()

    def fake_links(elem, xpath_expr):
        return ["http://test/a.html"]

    monkeypatch.setattr(ops, "_get_absolute_links_from_elem_and_xpath", fake_links)

    curr = html.fromstring("<html><body></body></html>", base_url="http://test/")
    rest = [("xpath", "//p/text()")]

    op = ops.get_operator("url_inf")
    value = "///url(//main//a/@href)"
    gen = op(curr, [("url_inf", value)] + rest, 0, q, curr.base_url, 2, seen)
    assert gen is None

    assert len(q) == 1
    t = q[0]
    assert t.depth == 0                         # not incremented here
    assert t.segments[0][0] == "url_inf_and_xpath"
    assert t.segments[0][1] == ("http://test/a.html", value)


# ---------------------------------------------------------------------------
# _handle_url_inf_and_xpath__no_return
# ---------------------------------------------------------------------------
def test_url_inf_and_xpath_fetches_and_requeues(monkeypatch):
    q = []
    seen = set()

    def fake_load(url, backlink, depth, _seen):
        el = html.fromstring("<html><body><p>A</p></body></html>", base_url=url)
        return el

    monkeypatch.setattr(ops, "_load_page_as_element", fake_load)

    rest = [("xpath", "//p/text()")]
    op = ops.get_operator("url_inf_and_xpath")
    prev_val = "//main//a/@href"
    gen = op(
        curr_elem=None,
        curr_segments=[("url_inf_and_xpath", ("http://test/a.html", prev_val))] + rest,
        curr_depth=0,
        queue=q,
        backlink=None,
        max_depth=2,
        seen_urls=seen,
    )
    assert gen is None

    # Two tasks at depth+1: continue + re-enqueue url_inf
    assert len(q) == 2
    assert all(t.depth == 1 for t in q)
    assert q[0].segments == rest
    assert q[1].segments[0] == ("url_inf", prev_val)


# ---------------------------------------------------------------------------
# _handle_xpath
# ---------------------------------------------------------------------------
def test_xpath_yields_wxstr_for_strings():
    base = "http://test/"
    elem = html.fromstring("<html><body></body></html>", base_url=base)
    elem.set("backlink", base)
    elem.getroottree().getroot().set("depth", "3")

    delem = DummyElem(elem)

    def fake_xpath3(value):
        return ["hello"]  # force string result

    delem.xpath3 = fake_xpath3

    op = ops.get_operator("xpath")
    q = []
    gen = op(delem, [("xpath", "//p/text()")], 1, q, base, 5, set())
    out = list(gen)

    assert len(out) == 1
    s = out[0]
    assert isinstance(s, ops.WxStr)
    assert str(s) == "hello"
    assert s.base_url == base
    assert s.depth == 1


def test_xpath_macro_expansion_is_applied():
    base = "http://site/page"
    elem = html.fromstring("<html><body></body></html>", base_url=base)
    elem.set("backlink", base)
    elem.getroottree().getroot().set("depth", "2")

    delem = DummyElem(elem)
    captured = {}

    def spy_xpath3(value):
        captured["expr"] = value
        return []

    delem.xpath3 = spy_xpath3

    op = ops.get_operator("xpath")
    q = []
    list(op(delem, [("xpath", "wx:backlink() and wx:depth()")], 7, q, base, 9, set()))

    expr = captured["expr"]
    assert "string('" in expr         # backlink expansion
    assert "number(2)" in expr        # depth expansion