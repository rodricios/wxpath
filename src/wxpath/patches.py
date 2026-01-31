import urllib.parse

import elementpath
from elementpath import XPathContext, XPathFunction
from elementpath.xpath3 import XPath3Parser
from lxml import etree, html

from wxpath.http.client import Response as Response
from wxpath.util.cleaners import main_text_extractor
from wxpath.util.common_paths import XPATH_PATH_TO_EXTERNAL_LINKS, XPATH_PATH_TO_INTERNAL_LINKS
from wxpath.util.logging import get_logger

log = get_logger(__name__)


def html_element_repr(self):
    return (f"HtmlElement(tag={self.tag}, "
            f"depth={self.get('depth', -1)}, "
            f"base_url={getattr(self, 'base_url', None)!r})")

# Patch lxml.html.HtmlElement.__repr__ to improve debugging with base_url.
html.HtmlElement.__repr__ = html_element_repr


class XPath3Element(etree.ElementBase):
    def __init__(self, tag, attrib=None, nsmap=None, **extra):
        super().__init__(tag, attrib, nsmap, **extra)
        self.response = None  # type: Response | None
        
    def xpath3(self, expr, request=None, **kwargs):
        """
        Evaluate an XPath 3 expression using elementpath library,
        returning the results as a list.
        """
        kwargs.setdefault("parser", WXPathParser)
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

# --- WXPATH functions ---
WX_NAMESPACE = "http://wxpath.dev/ns"

class WXPathParser(XPath3Parser):
    """Custom parser that includes wxpath-specific functions."""
    pass

# 2. Register the namespace mapping globally on the parser class
WXPathParser.DEFAULT_NAMESPACES['wx'] = WX_NAMESPACE

# 2. Helper to register functions easily
def register_wxpath_function(name, nargs=None, **kwargs):
    """Registers a function token on the custom parser."""
    
    # Define the token on the class (this registers the symbol)
    # Check if this is a prefixed function (e.g. 'wx:depth')
    if ':' in name:
        prefix, local_name = name.split(':', 1)
        kwargs['prefix'] = prefix
        # kwargs['namespace'] = WX_NAMESPACE
        name = local_name
        
    # Register the token symbol
    # WXPathParser.function(name, nargs=nargs, **kwargs)
    # Register the token symbol and capture the created class
    token_class = WXPathParser.function(name, nargs=nargs, **kwargs)
    # Return a decorator to define the 'evaluate' method
    def decorator(func):
        # @WXPathParser.method(name)
        # def evaluate(self, context=None):
        #     # 'self' is the Token instance. 
        #     # 'self.get_argument(context, index)' evaluates arguments.
        #     return func(self, context)
        # return evaluate
        token_class.evaluate = func
        return func
    return decorator


class XPathContextRequired(Exception):
    message = ('XPathContext is required. This usually arises when you call '
               'the function without a preceding axes expression ("/")')
    def __init__(self, *args):
        super().__init__(self.message, *args)
   

def _get_root(context: XPathContext):
    if context is None:
        raise XPathContextRequired
    
    if not hasattr(context.item, 'elem'):
        return context.item.parent.elem.getroottree().getroot()
    return context.item.elem.getroottree().getroot()


@register_wxpath_function('wx:depth', nargs=0)
def wx_depth(_: XPathFunction, context: XPathContext):
    if context is None:
        raise XPathContextRequired

    root = _get_root(context)

    depth = root.get('depth')
    return int(depth) if depth is not None else 0


@register_wxpath_function('wx:backlink', nargs=0)
def wx_backlink(_: XPathFunction, context: XPathContext):
    if context is None:
        raise XPathContextRequired

    item = context.item.elem
    if item is None:
        return ''
    return item.get('backlink') or ''


@register_wxpath_function('wx:current-url', nargs=0)
def wx_current_url(_: XPathFunction, context: XPathContext):
    if context is None:
        raise XPathContextRequired

    item = context.item.elem
    if item is None:
        return ''
    return item.base_url


@register_wxpath_function('wx:elapsed', nargs=0)
@register_wxpath_function('wx:fetch-time', nargs=0)
def wx_fetch_time(_: XPathFunction, context: XPathContext):
    if context is None:
        raise XPathContextRequired

    item = context.item.elem
    if item is None:
        return ''
    resp = item.response # type: Response
    return resp.latency


# @register_wxpath_function('wx:status-code', nargs=0)
@register_wxpath_function('wx:status-code', nargs=0)
def wx_status_code(_: XPathFunction, context: XPathContext) -> int:
    if context is None:
        raise XPathContextRequired

    item = context.item.elem
    if item is None:
        return ''
    
    resp = item.response # type: Response
    return resp.status


@register_wxpath_function('wx:elem', nargs=0)
def wx_elem(_: XPathFunction, context: XPathContext):
    if context is None:
        raise XPathContextRequired

    item = context.item.elem
    if item is None:
        return ''
    return item


def _get_root_domain(base_url: str) -> str:
    parsed_url = urllib.parse.urlparse(base_url)

    netloc = parsed_url.netloc
    parts = netloc.split('.')
    root_domain = netloc

    if len(parts) > 2:
        # Heuristic: If the last part is 2 chars (uk, au) and 2nd to last is < 4 (co, com, org)
        # It's likely a compound TLD like co.uk. This isn't perfect but better than [-2:].
        if len(parts[-1]) == 2 and len(parts[-2]) <= 3:
             root_domain = ".".join(parts[-3:]) # grab bbc.co.uk
        else:
             # grab books.toscrape.com -> toscrape.com
             root_domain = ".".join(parts[-2:]) 

    return root_domain


@register_wxpath_function('wx:internal-links', nargs=0)
def wx_internal_links(_: XPathFunction, context: XPathContext):
    """
    Returns a list of internal links.
    Allows for false positives.
    """
    if context is None:
        raise XPathContextRequired

    item = context.item.elem
    if item is None:
        return ''
    
    root_domain = _get_root_domain(item.base_url)
    _path = XPATH_PATH_TO_INTERNAL_LINKS.format(root_domain)
    return item.xpath3(_path)


@register_wxpath_function('wx:external-links', nargs=0)
def wx_external_links(_: XPathFunction, context: XPathContext):
    """
    Returns a list of external links.
    """
    if context is None:
        raise XPathContextRequired

    item = context.item.elem
    if item is None:
        return ''
    
    root_domain = _get_root_domain(item.base_url)
    _path = XPATH_PATH_TO_EXTERNAL_LINKS.format(root_domain)
    return item.xpath3(_path)


@register_wxpath_function('wx:main-article-text', nargs=0)
def wx_main_article_text(_: XPathFunction, context: XPathContext):
    if context is None:
        raise XPathContextRequired
    
    item = context.item.elem
    if item is None:
        return ''
    
    try:
        return main_text_extractor(item)
    except Exception:
        log.exception('Failed to extract main article text')
        return ''
