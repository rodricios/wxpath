import re
from lxml import html, etree

class WxElement(html.HtmlElement):
    def __repr__(self):
        return f"WxElement(tag={self.tag}, attrib={dict(self.attrib)}, base_url={getattr(self, 'base_url', None)!r})"
        
    def wxpath(self, expr, depth=1, **kwargs):
        # If no custom DSL, use standard XPath
        if not re.split(r"(url\(.+?\))", expr):
            return self.xpath(expr, **kwargs)
        from wxpath.core import wxpath  # your DSL function
        return wxpath(self, expr, depth=depth)


class WxStr(str):
    def __new__(cls, value, base_url=None, depth=-1):
        obj = super().__new__(cls, value)
        obj.base_url = base_url
        obj.depth = depth
        return obj

    def __repr__(self):
        return f"ExtractedStr({super().__repr__()}, base_url={self.base_url!r}, depth={self.depth})"


class Task:
    def __init__(self, elem, segments, depth, backlink=None):
        self.elem = elem
        self.segments = segments
        self.depth = depth
        self.backlink = backlink
    
    def __repr__(self):
        return f"Task(elem={self.elem}, segments={self.segments}, depth={self.depth}, backlink={self.backlink})"
    
    def __iter__(self):
        return iter((self.elem, self.segments, self.depth, self.backlink))
    
