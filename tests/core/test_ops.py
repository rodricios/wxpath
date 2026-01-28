import pytest
from lxml import html

from wxpath.core import ops
from wxpath.core.models import (
    CrawlIntent,
    DataIntent,
    ExtractIntent,
    InfiniteCrawlIntent,
    ProcessIntent,
)
from wxpath.core.ops import (
    OPS_REGISTER,
    RuntimeSetupError,
    WxStr,
    get_operator,
    register,
)
from wxpath.core.parser import Binary, ContextItem, Segments, String, Url, UrlCrawl, Xpath


# ---------------------------------------------------------------------------
# WxStr class
# ---------------------------------------------------------------------------
class TestWxStr:
    def test_wxstr_creation(self):
        s = WxStr("hello", base_url="http://test/", depth=3)
        assert str(s) == "hello"
        assert s.base_url == "http://test/"
        assert s.depth == 3

    def test_wxstr_default_values(self):
        s = WxStr("world")
        assert str(s) == "world"
        assert s.base_url is None
        assert s.depth == -1

    def test_wxstr_repr(self):
        s = WxStr("test", base_url="http://example.com", depth=5)
        r = repr(s)
        assert "WxStr" in r
        assert "'test'" in r
        assert "http://example.com" in r
        assert "depth=5" in r

    def test_wxstr_is_string(self):
        s = WxStr("hello")
        assert isinstance(s, str)
        assert s + " world" == "hello world"


# ---------------------------------------------------------------------------
# Registry basics
# ---------------------------------------------------------------------------
class TestRegistry:
    def test_get_operator_for_xpath(self):
        xpath_node = Xpath("//p/text()")
        assert callable(get_operator(xpath_node))

    def test_get_operator_for_url_with_string(self):
        url_node = Url("url", [String("http://example.com")])
        assert callable(get_operator(url_node))

    def test_get_operator_for_url_with_xpath(self):
        url_node = Url("url", [Xpath("//a/@href")])
        assert callable(get_operator(url_node))

    def test_get_operator_for_binary(self):
        binary = Binary(Xpath("(1 to 3)"), "!", Segments([Xpath(".")]))
        assert callable(get_operator(binary))

    def test_get_operator_unknown_type_raises(self):
        class UnknownType:
            pass

        with pytest.raises(ValueError, match="Unknown operation"):
            get_operator(UnknownType())

    def test_register_duplicate_raises(self):
        # Create a temporary type to test registration
        class TempType:
            pass

        # Store original registrar state
        original = OPS_REGISTER.copy()

        try:
            @register(TempType)
            def handler1(elem, segments, depth, **kwargs):
                pass

            with pytest.raises(RuntimeSetupError, match="already registered"):
                @register(TempType)
                def handler2(elem, segments, depth, **kwargs):
                    pass
        finally:
            # Restore original state
            OPS_REGISTER.clear()
            OPS_REGISTER.update(original)


# ---------------------------------------------------------------------------
# handle_url - url() with string literal
# ---------------------------------------------------------------------------
class TestHandleUrlStringLiteral:
    def test_url_string_literal_yields_crawl_intent(self):
        elem = html.fromstring("<html><body></body></html>", base_url="http://test/")
        url_node = Url("url", [String("http://example.com")])
        segments = Segments([url_node])

        op = get_operator(url_node)
        results = list(op(elem, segments, 0))

        assert len(results) == 1
        assert isinstance(results[0], CrawlIntent)
        assert results[0].url == "http://example.com"
        assert results[0].next_segments == []

    def test_url_string_literal_with_follow_arg(self):
        elem = html.fromstring("<html><body></body></html>", base_url="http://test/")
        # url('http://example.com', follow=//a/@href)
        url_node = Url("url", [String("http://example.com"), Xpath("//a/@href")])
        segments = Segments([url_node])

        op = get_operator(url_node)
        results = list(op(elem, segments, 0))

        assert len(results) == 1
        assert isinstance(results[0], CrawlIntent)
        assert results[0].url == "http://example.com"
        # First segment should be UrlCrawl with ///url
        first_seg = results[0].next_segments[0]
        assert isinstance(first_seg, UrlCrawl)
        assert first_seg.func == "///url"
        assert first_seg.args[1] == "http://example.com"
        assert first_seg.args[0].value == "//a/@href"

    def test_url_string_literal_preserves_next_segments(self):
        elem = html.fromstring("<html><body></body></html>", base_url="http://test/")
        next_xpath = Xpath("//p/text()")
        url_node = Url("url", [String("http://example.com")])
        segments = Segments([url_node, next_xpath])

        op = get_operator(url_node)
        results = list(op(elem, segments, 0))

        assert len(results) == 1
        assert results[0].next_segments == [next_xpath]


# ---------------------------------------------------------------------------
# handle_url - /url() and //url() (url_eval)
# ---------------------------------------------------------------------------
class TestHandleUrlEval:
    def test_url_eval_yields_crawl_intents(self, monkeypatch):
        def fake_links(elem, xpath_expr):
            return ["http://test/a.html", "http://test/b.html"]

        monkeypatch.setattr(ops, "get_absolute_links_from_elem_and_xpath", fake_links)

        elem = html.fromstring("<html><body></body></html>", base_url="http://test/")
        rest_xpath = Xpath("//p/text()")
        url_node = Url("/url", [Xpath("//a/@href")])
        segments = Segments([url_node, rest_xpath])

        op = get_operator(url_node)
        results = list(op(elem, segments, 0))

        assert len(results) == 2
        for intent in results:
            assert isinstance(intent, CrawlIntent)
            assert intent.next_segments == [rest_xpath]
            assert intent.url in ["http://test/a.html", "http://test/b.html"]

    def test_url_eval_double_slash_yields_crawl_intents(self, monkeypatch):
        def fake_links(elem, xpath_expr):
            return ["http://test/page.html"]

        monkeypatch.setattr(ops, "get_absolute_links_from_elem_and_xpath", fake_links)

        elem = html.fromstring("<html><body></body></html>", base_url="http://test/")
        url_node = Url("//url", [Xpath("//a/@href")])
        segments = Segments([url_node])

        op = get_operator(url_node)
        results = list(op(elem, segments, 0))

        assert len(results) == 1
        assert isinstance(results[0], CrawlIntent)
        assert results[0].url == "http://test/page.html"

    def test_url_eval_with_context_item(self):
        """When url has ContextItem arg, should use curr_elem as URL."""
        elem = WxStr("/page.html", base_url="http://test/", depth=1)
        url_node = Url("/url", [ContextItem()])
        segments = Segments([url_node])

        op = get_operator(url_node)
        results = list(op(elem, segments, 0))

        assert len(results) == 1
        assert isinstance(results[0], CrawlIntent)
        assert results[0].url == "http://test/page.html"

    def test_url_eval_deduplicates_urls(self, monkeypatch):
        """URL eval should deduplicate links."""
        def fake_links(elem, xpath_expr):
            return ["http://test/a.html", "http://test/a.html", "http://test/b.html"]

        monkeypatch.setattr(ops, "get_absolute_links_from_elem_and_xpath", fake_links)

        elem = html.fromstring("<html><body></body></html>", base_url="http://test/")
        url_node = Url("/url", [Xpath("//a/@href")])
        segments = Segments([url_node])

        op = get_operator(url_node)
        results = list(op(elem, segments, 0))

        # Should deduplicate to 2 unique URLs
        assert len(results) == 2
        urls = [r.url for r in results]
        assert "http://test/a.html" in urls
        assert "http://test/b.html" in urls


# ---------------------------------------------------------------------------
# handle_url - ///url() (url_inf)
# ---------------------------------------------------------------------------
class TestHandleUrlInf:
    def test_url_inf_yields_crawl_intents_with_url_crawl(self, monkeypatch):
        def fake_links(elem, xpath_expr):
            return ["http://test/a.html"]

        monkeypatch.setattr(ops, "get_absolute_links_from_elem_and_xpath", fake_links)

        elem = html.fromstring("<html><body></body></html>", base_url="http://test/")
        rest_xpath = Xpath("//p/text()")
        url_node = Url("///url", [Xpath("//main//a/@href")])
        segments = Segments([url_node, rest_xpath])

        op = get_operator(url_node)
        results = list(op(elem, segments, 0))

        assert len(results) == 1
        intent = results[0]
        assert isinstance(intent, CrawlIntent)
        assert intent.url == "http://test/a.html"

        # First segment should be UrlCrawl with ///url
        first_seg = intent.next_segments[0]
        assert isinstance(first_seg, UrlCrawl)
        assert first_seg.func == "///url"
        assert first_seg.args[1] == "http://test/a.html"
        assert first_seg.args[0].value == "//main//a/@href"

        # Rest of segments should follow
        assert intent.next_segments[1:] == [rest_xpath]

    def test_url_inf_deduplicates_urls(self, monkeypatch):
        def fake_links(elem, xpath_expr):
            return ["http://test/a.html", "http://test/a.html"]

        monkeypatch.setattr(ops, "get_absolute_links_from_elem_and_xpath", fake_links)

        elem = html.fromstring("<html><body></body></html>", base_url="http://test/")
        url_node = Url("///url", [Xpath("//a/@href")])
        segments = Segments([url_node])

        op = get_operator(url_node)
        results = list(op(elem, segments, 0))

        assert len(results) == 1


# ---------------------------------------------------------------------------
# _handle_url_inf_and_xpath (UrlCrawl with Xpath and str args)
# ---------------------------------------------------------------------------
class TestHandleUrlInfAndXpath:
    def test_yields_data_and_infinite_crawl_intents(self):
        elem = html.fromstring("<html><body></body></html>", base_url="http://test/")
        url_crawl = UrlCrawl("///url", [Xpath("//main//a/@href"), "http://test/a.html"])
        rest_xpath = Xpath("//p/text()")
        segments = Segments([url_crawl, rest_xpath])

        op = get_operator(url_crawl)
        results = list(op(elem, segments, 0))

        # Should yield ExtractIntent and InfiniteCrawlIntent
        assert len(results) == 2
        types = {type(r) for r in results}
        assert ExtractIntent in types
        assert InfiniteCrawlIntent in types

    def test_yields_data_intent_when_no_next_segments(self):
        elem = html.fromstring("<html><body></body></html>", base_url="http://test/")
        url_crawl = UrlCrawl("///url", [Xpath("//main//a/@href"), "http://test/a.html"])
        segments = Segments([url_crawl])

        op = get_operator(url_crawl)
        results = list(op(elem, segments, 0))

        # Should yield DataIntent and InfiniteCrawlIntent
        assert len(results) == 2
        types = {type(r) for r in results}
        assert DataIntent in types
        assert InfiniteCrawlIntent in types

    def test_infinite_crawl_intent_contains_url_crawl_node(self):
        elem = html.fromstring("<html><body></body></html>", base_url="http://test/")
        url_crawl = UrlCrawl("///url", [Xpath("//nav//a/@href"), "http://test/a.html"])
        rest_xpath = Xpath("//article/text()")
        segments = Segments([url_crawl, rest_xpath])

        op = get_operator(url_crawl)
        results = list(op(elem, segments, 0))

        infinite_intent = next(r for r in results if isinstance(r, InfiniteCrawlIntent))
        first_seg = infinite_intent.next_segments[0]
        assert isinstance(first_seg, UrlCrawl)
        assert first_seg.func == "///url"
        assert first_seg.args[0].value == "//nav//a/@href"

    def test_raises_when_elem_is_none(self):
        url_crawl = UrlCrawl("///url", [Xpath("//a/@href"), "http://test/a.html"])
        segments = Segments([url_crawl])

        op = get_operator(url_crawl)
        # Should not raise but log error (exception is caught internally)
        # The function catches exceptions and logs them
        results = list(op(None, segments, 0))
        # No results due to caught exception
        assert len(results) == 0


# ---------------------------------------------------------------------------
# _handle_xpath
# ---------------------------------------------------------------------------
class TestHandleXpath:
    def test_xpath_yields_data_intent_for_terminal(self):
        elem = html.fromstring(
            "<html><body><p>Hello</p></body></html>",
            base_url="http://test/"
        )
        elem.set("backlink", "http://test/")
        elem.getroottree().getroot().set("depth", "1")

        # Patch xpath3 method
        class DummyElem:
            def __init__(self, elem):
                self._elem = elem

            def __getattr__(self, name):
                return getattr(self._elem, name)

            def xpath3(self, expr):
                return ["Hello"]

        delem = DummyElem(elem)
        xpath_node = Xpath("//p/text()")
        segments = Segments([xpath_node])

        op = get_operator(xpath_node)
        results = list(op(delem, segments, 1))

        assert len(results) == 1
        assert isinstance(results[0], DataIntent)
        assert str(results[0].value) == "Hello"

    def test_xpath_yields_process_intent_with_next_segments(self):
        elem = html.fromstring(
            "<html><body><p>Hello</p></body></html>",
            base_url="http://test/"
        )
        elem.set("backlink", "http://test/")
        elem.getroottree().getroot().set("depth", "1")

        class DummyElem:
            def __init__(self, elem):
                self._elem = elem

            def __getattr__(self, name):
                return getattr(self._elem, name)

            def xpath3(self, expr):
                return ["test"]

        delem = DummyElem(elem)
        next_url = Url("/url", [Xpath(".")])
        xpath_node = Xpath("//p/text()")
        segments = Segments([xpath_node, next_url])

        op = get_operator(xpath_node)
        results = list(op(delem, segments, 1))

        assert len(results) == 1
        assert isinstance(results[0], ProcessIntent)
        assert results[0].next_segments == [next_url]

    def test_xpath_yields_wxstr_for_string_results(self):
        elem = html.fromstring(
            "<html><body><p>World</p></body></html>",
            base_url="http://site/"
        )
        elem.set("backlink", "http://site/")
        elem.getroottree().getroot().set("depth", "2")

        class DummyElem:
            def __init__(self, elem):
                self._elem = elem

            def __getattr__(self, name):
                return getattr(self._elem, name)

            def xpath3(self, expr):
                return ["extracted text"]

        delem = DummyElem(elem)
        xpath_node = Xpath("//p/text()")
        segments = Segments([xpath_node])

        op = get_operator(xpath_node)
        results = list(op(delem, segments, 3))

        assert len(results) == 1
        value = results[0].value
        assert isinstance(value, WxStr)
        assert value.base_url == "http://site/"
        assert value.depth == 3

    def test_xpath_raises_when_elem_is_none(self):
        xpath_node = Xpath("//p/text()")
        segments = Segments([xpath_node])

        op = get_operator(xpath_node)
        with pytest.raises(ValueError, match="Element must be provided"):
            list(op(None, segments, 0))

    def test_xpath_with_url_node_and_string_elem_delegates_to_url_eval(self, monkeypatch):
        """When curr_elem is string and segment is Url, should delegate to _handle_url_eval."""
        elem = WxStr("/page.html", base_url="http://test/", depth=1)
        # This is actually a Url node masquerading - the code checks isinstance(xpath_node, Url)
        url_node = Url("/url", [ContextItem()])
        segments = Segments([url_node])

        op = get_operator(url_node)
        results = list(op(elem, segments, 0))

        assert len(results) == 1
        assert isinstance(results[0], CrawlIntent)


# ---------------------------------------------------------------------------
# _handle_binary
# ---------------------------------------------------------------------------
class TestHandleBinary:
    def test_binary_xpath_with_segments_yields_process_intents(self, monkeypatch):
        elem = html.fromstring(
            "<html><body><p>Test</p></body></html>",
            base_url="http://test/"
        )

        # Binary: xpath ! segments
        left = Xpath("(1 to 3)")
        right = Segments([Url("/url", [Xpath(".")])])
        binary = Binary(left, "!", right)

        op = get_operator(binary)
        results = list(op(elem, binary, 0))

        assert len(results) == 3
        for r in results:
            assert isinstance(r, ProcessIntent)
            assert r.next_segments == right

    def test_binary_yields_wxstr_for_string_results(self):
        elem = html.fromstring(
            "<html><body><p>Test</p></body></html>",
            base_url="http://site/"
        )

        left = Xpath("('a', 'b')")
        right = Segments([Xpath(".")])
        binary = Binary(left, "!", right)

        op = get_operator(binary)
        results = list(op(elem, binary, 2))

        assert len(results) == 2
        for r in results:
            assert isinstance(r.elem, WxStr)
            assert r.elem.base_url == "http://site/"
            assert r.elem.depth == 2

    def test_binary_raises_when_right_is_empty(self):
        elem = html.fromstring("<html><body></body></html>", base_url="http://test/")

        left = Xpath("(1 to 2)")
        right = Segments([])  # Empty segments
        binary = Binary(left, "!", right)

        op = get_operator(binary)
        with pytest.raises(
            ValueError, 
            match="Binary operation on segments expects non-empty segments"
        ):
            list(op(elem, binary, 0))
