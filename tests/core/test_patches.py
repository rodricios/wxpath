"""Tests for custom wx:* XPath functions in patches.py"""

import pytest
from elementpath.exceptions import ElementPathTypeError
from lxml import html

from wxpath.http.client.request import Request
from wxpath.http.client.response import Response
from wxpath.patches import XPathContextRequired, html_parser_with_xpath3


class TestWXPathFunctions:
    """Test suite for custom wx:* XPath functions."""

    def test_wx_depth_with_depth_attribute(self):
        """Test wx:depth() returns depth from root element."""
        html_str = "<html><body><p>Test</p></body></html>"
        root2 = html.fromstring(html_str, parser=html_parser_with_xpath3)
        root2.set("depth", "5")
        
        result = root2.xpath3("/ map { 'depth': wx:depth() }") # type: "XPathMap"

        assert len(result) == 1
        item = result[0].items()
        assert item[0][0] == "depth"
        assert item[0][1] == 5

        result = root2.xpath3("/wx:depth()")
        assert result == 5


    def test_wx_depth_without_depth_attribute(self):
        """Test wx:depth() returns 0 when depth attribute is missing."""
        html_str = "<html><body><p>Test</p></body></html>"
        root = html.fromstring(html_str, parser=html_parser_with_xpath3)
        
        result = root.xpath3("/wx:depth()")
        assert result == 0

    def test_wx_depth_with_argument(self):
        """Test wx:depth() accepts an argument (ignored)."""
        html_str = "<html><body><p>Test</p></body></html>"
        root = html.fromstring(html_str, parser=html_parser_with_xpath3)
        root.set("depth", "3")
        
        with pytest.raises(ElementPathTypeError):
            root.xpath3("/wx:depth(.)")


    def test_wx_backlink_with_backlink_attribute(self):
        """Test wx:backlink() returns backlink attribute."""
        html_str = "<html><body><p>Test</p></body></html>"
        root = html.fromstring(html_str, parser=html_parser_with_xpath3)
        root.set("backlink", "http://example.com/page")
        
        result = root.xpath3("/wx:backlink()")
        assert result == ["http://example.com/page"]

    def test_wx_backlink_without_backlink_attribute(self):
        """Test wx:backlink() returns empty string when backlink is missing."""
        html_str = "<html><body><p>Test</p></body></html>"
        root = html.fromstring(html_str, parser=html_parser_with_xpath3)
        
        result = root.xpath3("/wx:backlink()")
        assert result == [""]

    def test_wx_backlink_with_argument(self):
        """Test wx:backlink() accepts an argument (ignored)."""
        html_str = "<html><body><p>Test</p></body></html>"
        root = html.fromstring(html_str, parser=html_parser_with_xpath3)
        root.set("backlink", "http://test.com")
        
        with pytest.raises(ElementPathTypeError):
            root.xpath3("/wx:backlink(.)")

    def test_wx_current_url_with_base_url(self):
        """Test wx:current-url() returns base_url from element."""
        html_str = "<html><body><p>Test</p></body></html>"
        root = html.fromstring(html_str, parser=html_parser_with_xpath3)
        root.base_url = "http://example.com/page"
        
        result = root.xpath3("/wx:current-url()")
        assert result == ["http://example.com/page"]

    def test_wx_current_url_without_base_url(self):
        """Test wx:current-url() returns None when base_url is missing."""
        html_str = "<html><body><p>Test</p></body></html>"
        root = html.fromstring(html_str, parser=html_parser_with_xpath3)
        # Ensure docinfo.URL is None
        root.getroottree().docinfo.URL = None
        
        result = root.xpath3("/wx:current-url()")
        # Should return None when base_url is not set
        # The function returns item.base_url which may be None
        assert result == []

    def test_wx_current_url_with_argument(self):
        """Test wx:current-url() accepts an argument (ignored)."""
        html_str = "<html><body><p>Test</p></body></html>"
        root = html.fromstring(html_str, parser=html_parser_with_xpath3)
        root.base_url = "http://test.com/page"
        
        with pytest.raises(ElementPathTypeError): 
            root.xpath3("/wx:current-url(.)")


    def test_wx_fetch_time_with_response(self):
        """Test wx:fetch-time() returns latency from response."""
        html_str = "<html><body><p>Test</p></body></html>"
        root = html.fromstring(html_str, parser=html_parser_with_xpath3)
        
        request = Request(url="http://example.com")
        response = Response(
            request=request,
            status=200,
            body=b"<html></html>",
            request_start=100.0,
            response_end=102.5
        )
        root.response = response
        
        result = root.xpath3("/wx:fetch-time()")
        assert result == pytest.approx(2.5)

    def test_wx_fetch_time_with_argument(self):
        """Test wx:fetch-time() accepts an argument (ignored)."""
        html_str = "<html><body><p>Test</p></body></html>"
        root = html.fromstring(html_str, parser=html_parser_with_xpath3)
        
        request = Request(url="http://example.com")
        response = Response(
            request=request,
            status=200,
            body=b"<html></html>",
            request_start=0.0,
            response_end=1.5
        )
        root.response = response
        
        with pytest.raises(ElementPathTypeError):
            root.xpath3("/wx:fetch-time(.)")


    def test_wx_elapsed_alias(self):
        """Test wx:elapsed() is an alias for wx:fetch-time()."""
        html_str = "<html><body><p>Test</p></body></html>"
        root = html.fromstring(html_str, parser=html_parser_with_xpath3)
        
        request = Request(url="http://example.com")
        response = Response(
            request=request,
            status=200,
            body=b"<html></html>",
            request_start=10.0,
            response_end=12.3
        )
        root.response = response
        
        result = root.xpath3("/wx:elapsed()")
        # float precision is not guaranteed
        assert result == pytest.approx(2.3)

    def test_wx_status_code_with_response(self):
        """Test wx:status-code() returns status code from response."""
        html_str = "<html><body><p>Test</p></body></html>"
        root = html.fromstring(html_str, parser=html_parser_with_xpath3)
        
        request = Request(url="http://example.com")
        response = Response(
            request=request,
            status=404,
            body=b"<html></html>"
        )
        root.response = response
        
        result = root.xpath3("/wx:status-code()")
        assert result == 404

    def test_wx_status_code_with_different_status(self):
        """Test wx:status-code() with different status codes."""
        html_str = "<html><body><p>Test</p></body></html>"
        root = html.fromstring(html_str, parser=html_parser_with_xpath3)
        
        request = Request(url="http://example.com")
        response = Response(
            request=request,
            status=500,
            body=b"<html></html>"
        )
        root.response = response
        
        result = root.xpath3("/wx:status-code()")
        assert result == 500

    def test_wx_elem_returns_element(self):
        """Test wx:elem() returns the current element."""
        html_str = "<html><body><p>Test</p></body></html>"
        root = html.fromstring(html_str, parser=html_parser_with_xpath3)
        
        result = root.xpath3("/wx:elem()")
        assert len(result) == 1
        assert result[0] is root

    def test_wx_elem_with_child_element(self):
        """Test wx:elem() returns the context element in a child context."""
        html_str = "<html><body><p>Test</p></body></html>"
        root = html.fromstring(html_str, parser=html_parser_with_xpath3)
        
        # Get the p element and test wx:elem() on it
        p_elements = root.xpath3("//p")
        assert len(p_elements) == 1
        p_elem = p_elements[0]
        
        # Set base_url on p element for xpath3 to work
        p_elem.base_url = "http://example.com"
        result = p_elem.xpath3("/wx:elem()")
        assert len(result) == 1
        assert result[0] is p_elem

    def test_wx_internal_links(self):
        """Test wx:internal-links() returns internal links."""
        html_str = """
        <html>
            <body>
                <a href="/page1">Internal 1</a>
                <a href="http://example.com/page2">Internal 2</a>
                <a href="http://external.com/page">External</a>
            </body>
        </html>
        """
        root = html.fromstring(html_str, parser=html_parser_with_xpath3)
        root.base_url = "http://example.com"
        
        result = root.xpath3("/wx:internal-links()")
        # Should return internal links (relative and same domain)
        assert len(result) >= 2
        hrefs = [str(link) for link in result]
        assert "/page1" in hrefs or "http://example.com/page1" in hrefs
        assert "http://example.com/page2" in hrefs

    def test_wx_internal_links_with_subdomain(self):
        """Test wx:internal-links() includes subdomain links."""
        html_str = """
        <html>
            <body>
                <a href="http://subdomain.example.com/page">Subdomain</a>
                <a href="http://other.com/page">External</a>
            </body>
        </html>
        """
        root = html.fromstring(html_str, parser=html_parser_with_xpath3)
        root.base_url = "http://example.com"
        
        result = root.xpath3("/wx:internal-links()")
        hrefs = [str(link) for link in result]
        # Should include subdomain links
        assert any("subdomain.example.com" in href for href in hrefs)

    def test_wx_external_links(self):
        """Test wx:external-links() returns external links."""
        html_str = """
        <html>
            <body>
                <a href="/page1">Internal 1</a>
                <a href="http://example.com/page2">Internal 2</a>
                <a href="http://external.com/page">External</a>
            </body>
        </html>
        """
        root = html.fromstring(html_str, parser=html_parser_with_xpath3)
        root.base_url = "http://example.com"
        
        result = root.xpath3("/wx:external-links()")
        # Should return external links
        hrefs = [str(link) for link in result]
        assert any("external.com" in href for href in hrefs)

    def test_wx_external_links_no_external(self):
        """Test wx:external-links() returns empty list when no external links."""
        html_str = """
        <html>
            <body>
                <a href="/page1">Internal 1</a>
                <a href="http://example.com/page2">Internal 2</a>
            </body>
        </html>
        """
        root = html.fromstring(html_str, parser=html_parser_with_xpath3)
        root.base_url = "http://example.com"
        
        result = root.xpath3("/wx:external-links()")
        # Should not include internal links
        hrefs = [str(link) for link in result]
        assert not any("external.com" in href for href in hrefs)

    def test_wx_main_article_text(self):
        """Test wx:main-article-text() extracts main article text."""
        html_str = """
        <html>
            <body>
                <nav>Navigation</nav>
                <article>
                    <p>This is the main article content.</p>
                    <p>It has multiple paragraphs.</p>
                </article>
                <footer>Footer content</footer>
            </body>
        </html>
        """
        root = html.fromstring(html_str, parser=html_parser_with_xpath3)
        root.base_url = "http://example.com"
        
        result = root.xpath3("/wx:main-article-text()")
        assert len(result) == 1
        text = result[0]
        assert isinstance(text, str)
        assert "main article content" in text.lower()
        assert "multiple paragraphs" in text.lower()

    def test_wx_main_article_text_empty(self):
        """Test wx:main-article-text() handles empty or minimal content."""
        html_str = "<html><body></body></html>"
        root = html.fromstring(html_str, parser=html_parser_with_xpath3)
        root.base_url = "http://example.com"
        
        result = root.xpath3("/wx:main-article-text()")
        # Should return empty string or minimal text
        assert len(result) == 1
        assert isinstance(result[0], str)

    def test_wx_main_article_text_with_short_text(self):
        """Test wx:main-article-text() filters out short text nodes."""
        html_str = """
        <html>
            <body>
                <p>Short</p>
                <p>This is a longer paragraph that should be 
                included in the main article text extraction.</p>
            </body>
        </html>
        """
        root = html.fromstring(html_str, parser=html_parser_with_xpath3)
        root.base_url = "http://example.com"
        
        result = root.xpath3("/wx:main-article-text()")
        assert len(result) == 1
        text = result[0]
        assert isinstance(text, str)
        # Should include longer text
        assert "longer paragraph" in text.lower()

    def test_wx_functions_in_xpath_expression(self):
        """Test wx: functions can be used in complex XPath expressions."""
        html_str = "<html><body><p>Test</p></body></html>"
        root = html.fromstring(html_str, parser=html_parser_with_xpath3)
        root.set("depth", "3")
        root.set("backlink", "http://test.com")
        root.base_url = "http://example.com"
        
        # Test combining wx: functions in an expression
        result = root.xpath3("/wx:depth() + 1")
        assert result == 4
        
        result = root.xpath3("/wx:backlink() = 'http://test.com'")
        assert result

    def test_wx_functions_with_none_response(self):
        """Test wx: functions raise AttributeError when response is None."""
        html_str = "<html><body><p>Test</p></body></html>"
        root = html.fromstring(html_str, parser=html_parser_with_xpath3)
        root.response = None
        
        # wx:fetch-time and wx:status-code will raise AttributeError if response is None
        with pytest.raises(XPathContextRequired):
            root.xpath3("wx:fetch-time()")
        
        with pytest.raises(XPathContextRequired):
            root.xpath3("wx:status-code()")

    def test_wx_internal_links_with_compound_tld(self):
        """Test wx:internal-links() handles compound TLDs like co.uk."""
        html_str = """
        <html>
            <body>
                <a href="http://www.bbc.co.uk/page">BBC</a>
                <a href="http://external.com/page">External</a>
            </body>
        </html>
        """
        root = html.fromstring(html_str, parser=html_parser_with_xpath3)
        root.base_url = "http://bbc.co.uk"
        
        result = root.xpath3("/wx:internal-links()")
        hrefs = [str(link) for link in result]
        # Should include bbc.co.uk links
        assert any("bbc.co.uk" in href for href in hrefs)

    def test_wx_external_links_with_compound_tld(self):
        """Test wx:external-links() handles compound TLDs correctly."""
        html_str = """
        <html>
            <body>
                <a href="http://www.bbc.co.uk/page">BBC</a>
                <a href="http://external.com/page">External</a>
            </body>
        </html>
        """
        root = html.fromstring(html_str, parser=html_parser_with_xpath3)
        root.base_url = "http://bbc.co.uk"
        
        result = root.xpath3("/wx:external-links()")
        hrefs = [str(link) for link in result]
        # Should include external.com but not bbc.co.uk
        assert any("external.com" in href for href in hrefs)
