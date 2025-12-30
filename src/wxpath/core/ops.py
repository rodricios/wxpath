"""
`ops` for "operations". This module contains side-effect-free functions (operators) 
for handling each segment of a wxpath expression.
"""
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
from wxpath.core.parser import OPS, Segment, UrlInfAndXpathValue, XpathValue
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


HANDLERS: dict[str, Callable] = {}

def _op(name: OPS):
    def reg(fn): 
        if name in HANDLERS:
            raise ValueError(f"Duplicate operation: {name}")
        HANDLERS[name] = fn
        return fn
    return reg


def get_operator(name: OPS) -> Callable[[html.HtmlElement, list[Segment], int], Iterable[Intent]]:
    if name not in HANDLERS:
        raise ValueError(f"Unknown operation: {name}")
    return HANDLERS[name]


@_op(OPS.URL_STR_LIT)
def _handle_url_str_lit(curr_elem: html.HtmlElement, 
                        curr_segments: list[Segment], 
                        curr_depth: int, **kwargs) -> Iterable[Intent]:
    op, value = curr_segments[0]

    log.debug("queueing", extra={"depth": curr_depth, "op": op, "url": value.target})

    next_segments = curr_segments[1:]

    if value.follow:
        _segments = [
            (OPS.URL_INF_AND_XPATH, UrlInfAndXpathValue('', value.target, value.follow))
        ] + next_segments
        
        yield CrawlIntent(url=value.target, next_segments=_segments)
    else:
        yield CrawlIntent(url=value.target, next_segments=next_segments)


@_op(OPS.URL_EVAL)
def _handle_url_eval(curr_elem: html.HtmlElement | str, 
                     curr_segments: list[Segment], 
                     curr_depth: int, 
                     **kwargs) -> Iterable[Intent]:
    op, value = curr_segments[0]

    _path_exp = value.expr

    if isinstance(curr_elem, str):
        # TODO: IMO, ideally, wxpath grammar should not be checked/validated/enforced 
        # in ops.py. It should instead be validated in the parser.
        if _path_exp not in {'.', 'self::node()'}:
            raise ValueError("Only '.' or 'self::node()' is supported in url() segments "
                             f"when prior xpath operation results in a string. Got: {_path_exp}")

        urls = [urljoin(getattr(curr_elem, 'base_url', None) or '', curr_elem)]
    else:
        # TODO: If prior xpath operation is XPATH_FN_MAP_FRAG, then this will likely fail.
        # It should be handled in the parser.
        urls = get_absolute_links_from_elem_and_xpath(curr_elem, _path_exp)
        urls = dict.fromkeys(urls)

    next_segments = curr_segments[1:]
    for url in urls:
        log.debug("queueing", extra={"depth": curr_depth, "op": op, "url": url})
        yield CrawlIntent(url=url, next_segments=next_segments)


@_op(OPS.URL_INF)
def _handle_url_inf(curr_elem: html.HtmlElement, 
                    curr_segments: list[Segment], 
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
    op, value = curr_segments[0]

    _path_exp = value.expr

    urls = get_absolute_links_from_elem_and_xpath(curr_elem, _path_exp)

    log.debug("found urls", 
              extra={"depth": curr_depth, "op": op, "url": getattr(curr_elem, 'base_url', None)})

    tail_segments = curr_segments[1:]
    for url in dict.fromkeys(urls):
        _segments = [
            (OPS.URL_INF_AND_XPATH, UrlInfAndXpathValue('', url, _path_exp))
        ] + tail_segments
        
        log.debug("queueing", extra={"depth": curr_depth, "op": op, "url": url})

        yield CrawlIntent(url=url, next_segments=_segments)


@_op(OPS.URL_INF_AND_XPATH)
def _handle_url_inf_and_xpath(curr_elem: html.HtmlElement, 
                              curr_segments: list[Segment], 
                              curr_depth: int, **kwargs) \
                                -> Iterable[DataIntent | ProcessIntent | InfiniteCrawlIntent]:
    """
    This is an operation that is generated internally by the parser. There is
    no explicit wxpath expression that generates this operation.
    """
    op, value = curr_segments[0]

    try:
        if curr_elem is None:
            raise ValueError("Missing element when op is 'url_inf_and_xpath'.")

        next_segments = curr_segments[1:]
        if not next_segments:
            yield DataIntent(value=curr_elem)
        else:
            yield ExtractIntent(elem=curr_elem, next_segments=next_segments)

        # For url_inf, also re-enqueue for further infinite expansion
        _segments = [(OPS.URL_INF, XpathValue('', value.expr))] + next_segments
        crawl_intent = InfiniteCrawlIntent(elem=curr_elem, next_segments=_segments)
        log.debug("queueing InfiniteCrawlIntent", 
                  extra={"depth": curr_depth, "op": op, 
                         "url": value.target, "crawl_intent": crawl_intent})
        yield crawl_intent

    except Exception:
        log.exception("error fetching url", 
                      extra={"depth": curr_depth, "op": op, "url": value.target})


@_op(OPS.XPATH)
def _handle_xpath(curr_elem: html.HtmlElement, 
                  curr_segments: list[Segment], 
                  curr_depth: int, 
                  **kwargs) -> Iterable[DataIntent | ProcessIntent]:
    """
    Handles the [/|//]<xpath> segment of a wxpath expression. This is a plain XPath expression.
    Also handles wxpath-specific macro expansions like wx:backlink() or wx:depth().
    """
    _, value = curr_segments[0]
    expr = value.expr
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


@_op(OPS.XPATH_FN_MAP_FRAG)
def _handle_xpath_fn_map_frag(curr_elem: html.HtmlElement | str, 
                              curr_segments: list[Segment], 
                              curr_depth: int, 
                              **kwargs) -> Iterable[DataIntent | ProcessIntent]:
    """
    Handles the execution of XPath functions that were initially suffixed with a 
    '!' (map) operator.
    """
    _, value = curr_segments[0]

    base_url = getattr(curr_elem, 'base_url', None)
    next_segments = curr_segments[1:]

    result = elementpath.select(
        curr_elem,
        value.expr,
        parser=XPath3Parser,
        item='' if curr_elem is None else None
    )

    if isinstance(result, AnyAtomicType):
        result = [result]

    for r in result:
        value_or_elem = WxStr(r, base_url=base_url, depth=curr_depth) if isinstance(r, str) else r
        if len(curr_segments) == 1:
            # XPATH_FN_MAP_FRAG is not a terminal operation
            raise ValueError("XPATH_FN_MAP_FRAG is not a terminal operation")
        else:
            yield ProcessIntent(elem=value_or_elem, next_segments=next_segments)
