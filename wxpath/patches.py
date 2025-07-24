from lxml import html

def html_element_repr(self):
    return f"HtmlElement(tag={self.tag}, base_url={getattr(self, 'base_url', None)!r})"

# Patch lxml.html.HtmlElement.__repr__ to improve debugging with base_url.
html.HtmlElement.__repr__ = html_element_repr
