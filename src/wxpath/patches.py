import elementpath
from elementpath.xpath3 import XPath3Parser
from lxml import etree, html


def html_element_repr(self):
    return (f"HtmlElement(tag={self.tag}, "
            f"depth={self.get('depth', -1)}, "
            f"base_url={getattr(self, 'base_url', None)!r})")

# Patch lxml.html.HtmlElement.__repr__ to improve debugging with base_url.
html.HtmlElement.__repr__ = html_element_repr


class XPath3Element(etree.ElementBase):
    def xpath3(self, expr, **kwargs):
        """
        Evaluate an XPath 3 expression using elementpath library,
        returning the results as a list.
        """
        kwargs.setdefault("parser", XPath3Parser)
        kwargs.setdefault(
            "uri", 
            getattr(self.getroottree().docinfo, "URL", None) or self.get("base_url")
        )
        return elementpath.select(self, expr, **kwargs)

    # --- Convenience property for backward‑compatibility -----------------
    @property
    def base_url(self):
        # 1) Per-element override (keeps our “multiple base URLs” feature)
        url = self.get("base_url")
        if url is not None:
            return url
        # 2) Fall back to document URL (O(1))
        return self.getroottree().docinfo.URL

    @base_url.setter
    def base_url(self, value):
        # Keep the per-element attribute (used by our crawler)
        self.set("base_url", value)
        # Set xml:base attribute so XPath base-uri() picks it up
        self.set("{http://www.w3.org/XML/1998/namespace}base", value)
        # Also store on the document so descendants can fetch it quickly
        self.getroottree().docinfo.URL = value

    @property
    def depth(self):
        return int(self.get("depth", -1))

    @depth.setter
    def depth(self, value):
        self.set("depth", str(value))
    
# Create and register custom parser that returns XPath3Element instances
lookup = etree.ElementDefaultClassLookup(element=XPath3Element)
parser = etree.HTMLParser()
parser.set_element_class_lookup(lookup)


# Expose parser for use in parse_html
html_parser_with_xpath3 = parser
html.HtmlElement.xpath3 = XPath3Element.xpath3