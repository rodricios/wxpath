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
    def __new__(cls, value, base_url=None):
        obj = super().__new__(cls, value)
        obj.base_url = base_url
        return obj

    def __repr__(self):
        return f"ExtractedStr({super().__repr__()}, base_url={self.base_url!r})"


class Task:
    def __init__(self, elem, segments, depth, backlink=None, parent_page_url=None, session_id=None, discovered_from_url=None):
        self.elem = elem
        self.segments = segments
        self.depth = depth
        self.backlink = backlink
        # Graph context fields
        self.parent_page_url = parent_page_url
        self.session_id = session_id
        self.discovered_from_url = discovered_from_url  # URL where this task's URL was discovered
    
    def __repr__(self):
        return f"Task(elem={self.elem}, segments={self.segments}, depth={self.depth}, backlink={self.backlink}, parent_page_url={self.parent_page_url}, session_id={self.session_id})"
    
    def __iter__(self):
        return iter((self.elem, self.segments, self.depth, self.backlink))
    
    def with_graph_context(self, parent_page_url=None, session_id=None, discovered_from_url=None):
        """Create a copy of this task with updated graph context."""
        return Task(
            elem=self.elem,
            segments=self.segments,
            depth=self.depth,
            backlink=self.backlink,
            parent_page_url=parent_page_url or self.parent_page_url,
            session_id=session_id or self.session_id,
            discovered_from_url=discovered_from_url or self.discovered_from_url
        )
    
