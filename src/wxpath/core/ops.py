"""
`ops` for "operations". This module contains side-effect-free functions (operators) 
for handling each segment of a wxpath expression.
"""
import requests
from typing import Callable, Iterable
from lxml import html

from wxpath.core.models import (
    Intent,
    CrawlIntent, 
    DataIntent, 
    ProcessIntent, 
    ExtractIntent, 
    InfiniteCrawlIntent
)
from wxpath.util.logging import get_logger
from wxpath.core.dom import get_absolute_links_from_elem_and_xpath
from wxpath.core.parser import (
    _parse_object_mapping, 
    _extract_arg_from_url_xpath_op, 
    _url_inf_filter_expr,
    parse_wxpath_expr,
    OPS,
    Segment
)

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
        HANDLERS[name] = fn
        return fn
    return reg


def get_operator(name: OPS) -> Callable[[html.HtmlElement, list[Segment], int], Iterable[Intent]]:
    if name not in HANDLERS:
        raise ValueError(f"Unknown operation: {name}")
    return HANDLERS[name]


@_op(OPS.URL_FROM_ATTR)
def _handle_url_from_attr__no_return(curr_elem: html.HtmlElement, curr_segments: list[Segment], curr_depth: int, **kwargs) -> Iterable[CrawlIntent]:
    """
    Handles the `[/|//]url(@<attr>)` (e.g., `...//url(@href)`) segment of a wxpath expression
    """
    op, value = curr_segments[0]
    if curr_elem is None:
        raise ValueError("Element must be provided when op is 'url_from_attr'.")
    
    url_op_arg = _extract_arg_from_url_xpath_op(value)
    log.debug("extracted arg from url xpath op", extra={"depth": curr_depth, "op": op, "url_op_arg": url_op_arg})
    if not url_op_arg.startswith('@'):
        raise ValueError("Only '@*' is supported in url() segments not at the start of path_expr.")
    
    _path_exp = '.' + value.split('url')[0] + url_op_arg

    log.debug("path expression", extra={"depth": curr_depth, "op": op, "path_exp": _path_exp})

    urls = get_absolute_links_from_elem_and_xpath(curr_elem, _path_exp)

    urls = list(dict.fromkeys(urls))

    log.debug("absolute links", extra={"depth": curr_depth, "op": op, "url_count": len(urls)})

    for url in urls:
        try:
            log.debug("queueing CrawlIntent", extra={"depth": curr_depth, "op": op, "url": url})
            yield CrawlIntent(url=url, next_segments=curr_segments[1:])
        except requests.exceptions.RequestException as e:
            log.exception("error fetching url", extra={"depth": curr_depth, "op": op, "url": url})
            continue


@_op(OPS.URL_INF)
def _handle_url_inf__no_return(curr_elem: html.HtmlElement, curr_segments: list[Segment], curr_depth: int, **kwargs) -> Iterable[CrawlIntent]:
    """
    Handles the ///url() segment of a wxpath expression. This operation is also 
    generated internally by the parser when a `///<xpath>/[/]url()` segment is
    encountered by the parser.
    This operation does not fetch URLs; instead, it XPaths the current element
    for URLs, then queues them for further processing (see 
    _handle_url_inf_and_xpath__no_return).
    """
    op, value = curr_segments[0]

    _path_exp = _url_inf_filter_expr(value)

    urls = get_absolute_links_from_elem_and_xpath(curr_elem, _path_exp)
    
    urls = list(dict.fromkeys(urls))

    log.debug("found urls", extra={"depth": curr_depth, "op": op, "url": getattr(curr_elem, 'base_url', None), "url_count": len(urls)})

    for url in urls:

        _segments = [(OPS.URL_INF_AND_XPATH, (url, value))] + curr_segments[1:]
        
        log.debug("queueing", extra={"depth": curr_depth, "op": op, "url": url})
        # Not incrementing since we do not actually fetch the URL here
        yield CrawlIntent(url=url, next_segments=_segments)


@_op(OPS.URL_INF_AND_XPATH)
def _handle_url_inf_and_xpath__no_return(curr_elem: html.HtmlElement, curr_segments: list[Segment], curr_depth: int, **kwargs) -> Iterable[DataIntent | ProcessIntent | InfiniteCrawlIntent]:
    """
    This is an operation that is generated internally by the parser. There is
    no explicit wxpath expression that generates this operation.
    """
    op, value = curr_segments[0]
    url, prev_op_value = value

    log.debug("handling url inf and xpath", extra={"curr_segments": curr_segments, "depth": curr_depth, "op": op, "url": url, "prev_op_value": prev_op_value, "curr_elem": curr_elem, "curr_elem.base_url": getattr(curr_elem, 'base_url', None)})

    try:
        if curr_elem is None:
            raise ValueError("Missing element when op is 'url_inf_and_xpath'.")

        next_segments = curr_segments[1:]
        if not next_segments:
            yield DataIntent(value=curr_elem)
        else:
            yield ExtractIntent(elem=curr_elem, next_segments=next_segments)

        # For url_inf, also re-enqueue for further infinite expansion
        _segments = [(OPS.URL_INF, prev_op_value)] + curr_segments[1:]
        crawl_intent = InfiniteCrawlIntent(elem=curr_elem, next_segments=_segments)
        log.debug("queueing InfiniteCrawlIntent", extra={"depth": curr_depth, "op": op, "url": url, "crawl_intent": crawl_intent})
        yield crawl_intent

    except Exception as e:
        log.exception("error fetching url", extra={"depth": curr_depth, "op": op, "url": url})


@_op(OPS.XPATH)
def _handle_xpath(curr_elem: html.HtmlElement, curr_segments: list[Segment], curr_depth: int, **kwargs) -> Iterable[DataIntent | ProcessIntent]:
    """
    Handles the [/|//]<xpath> segment of a wxpath expression. This is a plain XPath expression.
    Also handles wxpath-specific macro expansions like wx:backlink() or wx:depth().
    """
    _, value = curr_segments[0]
    if curr_elem is None:
        raise ValueError("Element must be provided when path_expr does not start with 'url()'.")
    base_url = getattr(curr_elem, 'base_url', None)
    log.debug("base url", extra={"depth": curr_depth, "op": 'xpath', "base_url": base_url})
    # assert backlink == base_url, "Backlink must be equal to base_url"

    _backlink_str = f"string('{curr_elem.get('backlink')}')"
    # We use the root tree's depth and not curr_depth because curr_depth accounts for a +1 
    # increment after each url*() hop
    _depth_str = f"number({curr_elem.getroottree().getroot().get('depth')})"
    value = value.replace('wx:backlink()', _backlink_str)
    value = value.replace('wx:backlink(.)', _backlink_str)
    value = value.replace('wx:depth()', _depth_str)
    value = value.replace('wx:depth(.)', _depth_str)

    elems = curr_elem.xpath3(value)
    
    for elem in elems:
        if len(curr_segments) == 1:
            yield DataIntent(value=WxStr(elem, base_url=base_url, depth=curr_depth) if isinstance(elem, str) else elem)
        else:
            yield ProcessIntent(elem=elem, next_segments=curr_segments[1:])


# @_op(OPS.OBJECT)
def _handle_object(curr_elem, curr_segments, curr_depth, backlink,
                   max_depth, seen_urls):
    """
    Builds a JSON-like dict from an object segment.

    Each value expression is evaluated using the full wxpath DSL so it can
    contain anything from a plain XPath to another `url()` hop.
    """
    assert False, "Code is deprecated. Functionality fulfilled by XPath 3.1 map objects."
    _, value = curr_segments[0]

    if curr_elem is None:
        raise ValueError("Object segment requires an element context before it.")

    obj_map = _parse_object_mapping(value)
    result = {}

    for key, expr in obj_map.items():
        # Detect optional [n] scalar-selection suffix.
        idx = None
        m = re.match(r'^(.*)\[(\d+)\]\s*$', expr)
        if m:
            expr_inner = m.group(1).strip()
            idx = int(m.group(2))
        else:
            expr_inner = expr

        # Parse the sub-expression and decide whether it needs a root element.
        sub_segments = parse_wxpath_expr(expr_inner)
        root_elem = None if sub_segments[0][0] != 'xpath' else curr_elem

        sub_results = list(
            evaluate_wxpath_bfs_iter(
                root_elem,
                sub_segments,
                max_depth=max_depth,
            )
        )

        # Apply index hint if present
        if idx is not None:
            sub_results = sub_results[idx:idx+1] if len(sub_results) > idx else []

        if not sub_results:
            result[key] = None
        elif len(sub_results) == 1:
            result[key] = sub_results[0]
        else:
            result[key] = sub_results

    # Yield the constructed object; no further traversal after an object segment.
    yield result