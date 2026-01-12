from typing import Callable, Iterable
from urllib.parse import urljoin

import elementpath
from elementpath.datatypes import AnyAtomicType
from elementpath.xpath3 import XPath3Parser
from lxml import html

from wxpath.core.dom import get_absolute_links_from_elem_and_xpath
from wxpath.core.models import (
    CrawlIntent,
    DataIntent,
    ExtractIntent,
    InfiniteCrawlIntent,
    Intent,
    ProcessIntent,
)
from wxpath.core.parser import (
    Binary,
    Call,
    ContextItem,
    Segment,
    Segments,
    String,
    Url,
    UrlCrawl,
    Xpath,
)
from wxpath.util.logging import get_logger

log = get_logger(__name__)


class WxStr(str):
    """
    A string that has a base_url and depth associated with it. Purely for debugging.
    """
    def __new__(cls, value, base_url=None, depth=-1):
        obj = super().__new__(cls, value)
        obj.base_url = base_url
        obj.depth = depth
        return obj

    def __repr__(self):
        return f"WxStr({super().__repr__()}, base_url={self.base_url!r}, depth={self.depth})"


class RuntimeSetupError(Exception):
    pass


OPS_REGISTER: dict[str, Callable] = {}

def register(func_name_or_type: str | type, args_types: tuple = None):
    def _register(func):
        global OPS_REGISTER
        _key = (func_name_or_type, args_types) if args_types else func_name_or_type
        if _key in OPS_REGISTER:
            raise RuntimeSetupError(f"The operation handler for \"{_key}\" already registered")
        OPS_REGISTER[_key] = func
        return func
    return _register


def get_operator(
        binary_or_segment: Binary | Segment
    ) -> Callable[[html.HtmlElement, list[Url | Xpath], int], Iterable[Intent]]:
    func_name_or_type = getattr(binary_or_segment, 'func', None) or binary_or_segment.__class__

    args_types = None
    if isinstance(binary_or_segment, Binary):
        args_types = (binary_or_segment.left.__class__, binary_or_segment.right.__class__)
    elif isinstance(binary_or_segment, Call):
        args_types = tuple(arg.__class__ for arg in binary_or_segment.args)

    _key = (func_name_or_type, args_types) if args_types else func_name_or_type
    if _key not in OPS_REGISTER:
        raise ValueError(f"Unknown operation: {_key}")
    return OPS_REGISTER[_key]


@register('url', (String,))
@register('url', (String, Xpath))
def _handle_url_str_lit(curr_elem: html.HtmlElement, 
                        curr_segments: list[Url | Xpath], 
                        curr_depth: int, **kwargs) -> Iterable[Intent]:
    url_call = curr_segments[0] # type: Url

    next_segments = curr_segments[1:]

    if len(url_call.args) == 2:
        _segments = [
            UrlCrawl('///url', [url_call.args[1], url_call.args[0].value])
        ] + next_segments
        
        yield CrawlIntent(url=url_call.args[0].value, next_segments=_segments)
    else:
        yield CrawlIntent(url=url_call.args[0].value, next_segments=next_segments)


# @register2('url', (Xpath,))
@register(Xpath)
def _handle_xpath(curr_elem: html.HtmlElement,
                  curr_segments: Segments,
                  curr_depth: int,
                  **kwargs) -> Iterable[Intent]:
    xpath_node = curr_segments[0] # type: Xpath

    expr = xpath_node.value

    if curr_elem is None:
        raise ValueError("Element must be provided when path_expr does not start with 'url()'.")
    base_url = getattr(curr_elem, 'base_url', None)
    log.debug("base url", extra={"depth": curr_depth, "op": 'xpath', "base_url": base_url})

    _backlink_str = f"string('{curr_elem.get('backlink')}')"
    # We use the root tree's depth and not curr_depth because curr_depth accounts for a +1 
    # increment after each url*() hop
    _depth_str = f"number({curr_elem.getroottree().getroot().get('depth')})"
    expr = expr.replace('wx:backlink()', _backlink_str)
    expr = expr.replace('wx:backlink(.)', _backlink_str)
    expr = expr.replace('wx:depth()', _depth_str)
    expr = expr.replace('wx:depth(.)', _depth_str)

    elems = curr_elem.xpath3(expr)
    
    next_segments = curr_segments[1:]
    for elem in elems:
        value_or_elem = WxStr(
            elem, base_url=base_url, 
            depth=curr_depth
        ) if isinstance(elem, str) else elem
        if len(curr_segments) == 1:
            yield DataIntent(value=value_or_elem)
        else:
            yield ProcessIntent(elem=value_or_elem, next_segments=next_segments)


@register('//url', (ContextItem,))
@register('//url', (Xpath,))
@register('/url', (ContextItem,))
@register('/url', (Xpath,))
@register('url', (ContextItem,))
@register('url', (Xpath,))
def _handle_url_eval(curr_elem: html.HtmlElement | str, 
                     curr_segments: list[Url | Xpath], 
                     curr_depth: int, 
                     **kwargs) -> Iterable[Intent]:
    url_call = curr_segments[0] # type: Url

    if isinstance(url_call.args[0], ContextItem):
        urls = [urljoin(getattr(curr_elem, 'base_url', None) or '', curr_elem)]
    else:
        _path_exp = url_call.args[0].value
        # TODO: If prior xpath operation is XPATH_FN_MAP_FRAG, then this will likely fail.
        # It should be handled in the parser.
        urls = get_absolute_links_from_elem_and_xpath(curr_elem, _path_exp)
        urls = dict.fromkeys(urls)

    next_segments = curr_segments[1:]
    for url in urls:
        # log.debug("queueing", extra={"depth": curr_depth, "op": op, "url": url})
        yield CrawlIntent(url=url, next_segments=next_segments)


@register('///url', (Xpath,))
def _handle_url_inf(curr_elem: html.HtmlElement, 
                    curr_segments: list[Url | Xpath], 
                    curr_depth: int, 
                    **kwargs) -> Iterable[CrawlIntent]:
    """
    Handles the ///url() segment of a wxpath expression. This operation is also 
    generated internally by the parser when a `///<xpath>/[/]url()` segment is
    encountered by the parser.
    This operation does not fetch URLs; instead, it XPaths the current element
    for URLs, then queues them for further processing (see 
    _handle_url_inf_and_xpath).
    """
    url_call = curr_segments[0] # type: Url

    _path_exp = url_call.args[0].value

    urls = get_absolute_links_from_elem_and_xpath(curr_elem, _path_exp)

    tail_segments = curr_segments[1:]
    for url in dict.fromkeys(urls):
        _segments = [
            UrlCrawl('///url', [url_call.args[0], url])
        ] + tail_segments
        
        yield CrawlIntent(url=url, next_segments=_segments)


@register('///url', (Xpath, str))
def _handle_url_inf_and_xpath(curr_elem: html.HtmlElement, 
                              curr_segments: list[Url | Xpath], 
                              curr_depth: int, **kwargs) \
                                -> Iterable[DataIntent | ProcessIntent | InfiniteCrawlIntent]:
    """
    This is an operation that is generated internally by the parser. There is
    no explicit wxpath expression that generates this operation.
    """
    url_call = curr_segments[0]

    try:
        if curr_elem is None:
            raise ValueError("Missing element when op is 'url_inf_and_xpath'.")

        next_segments = curr_segments[1:]

        if not next_segments:
            yield DataIntent(value=curr_elem)
        else:
            yield ExtractIntent(elem=curr_elem, next_segments=next_segments)

        # For url_inf, also re-enqueue for further infinite expansion
        _segments = [UrlCrawl('///url', url_call.args[:-1])] + next_segments
        crawl_intent = InfiniteCrawlIntent(elem=curr_elem, next_segments=_segments)

        yield crawl_intent

    except Exception:
        log.exception("error fetching url inf and xpath", 
                      extra={"depth": curr_depth, "url": url_call.args[1]})

@register(Binary, (Xpath, Segments))
def _handle_binary(curr_elem: html.HtmlElement | str, 
                              curr_segments: list[Url | Xpath] | Binary, 
                              curr_depth: int, 
                              **kwargs) -> Iterable[DataIntent | ProcessIntent]:
    """
    Handles the execution of XPath functions that were initially suffixed with a 
    '!' (map) operator.
    """
    left = curr_segments.left
    _ = curr_segments.op
    right = curr_segments.right

    if len(right) == 0:
        # Binary operation on segments expects non-empty segments
        raise ValueError("Binary operation on segments expects non-empty segments")

    base_url = getattr(curr_elem, 'base_url', None)
    next_segments = right

    results = elementpath.select(
        curr_elem,
        left.value,
        parser=XPath3Parser,
        item='' if curr_elem is None else None
    )

    if isinstance(results, AnyAtomicType):
        results = [results]

    for result in results:
        if isinstance(result, str):
            value_or_elem = WxStr(result, base_url=base_url, depth=curr_depth) 
        else:
            value_or_elem = result

        yield ProcessIntent(elem=value_or_elem, next_segments=next_segments)
