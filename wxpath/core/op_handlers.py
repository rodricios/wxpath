"""
This module contains functions for handling each segment of a wxpath expression.
"""
import requests
from typing import Callable

from wxpath.hooks import get_hooks
from wxpath.core.errors import with_errors
from wxpath.core.task import Task
from wxpath.logging_utils import get_logger
from wxpath.core.helpers import (
    _ctx, 
    _load_page_as_element, 
    _get_absolute_links_from_elem_and_xpath
)
from wxpath.core.parser import (
    _parse_object_mapping, 
    _extract_arg_from_url_xpath_op, 
    _url_inf_filter_expr,
    parse_wxpath_expr
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

def _op(name):
    def reg(fn): 
        HANDLERS[name] = fn
        return fn
    return reg


def get_operator(name) -> Callable:
    if name not in HANDLERS:
        raise ValueError(f"Unknown operation: {name}")
    return HANDLERS[name]


@_op('url')
def _handle_url(curr_elem, curr_segments, curr_depth, queue, backlink, max_depth, seen_urls):
    """
    Handles the `^url()` segment of a wxpath expression
    """
    op, url = curr_segments[0]
    # NOTE: Should I allow curr_elem to be not None? 
    #   Pros: when adding backling attrib to new_elem, it's easy to add it from curr_elem.base_url. 
    #   Cons: curr_elem.base_url might not be set. Also, we keep an extra reference to curr_elem for the next level - could potentially cause a memory leak.
    if curr_elem is not None:
        raise ValueError("Cannot use 'url()' at the start of path_expr with an element provided.")
    if url.startswith('@'):
        raise ValueError("Cannot use '@' in url() segment at the start of path_expr.")
    if url in seen_urls:
        log.debug("url seen", extra={"depth": curr_depth, "op": op, "url": url})
        return

    try:
        new_elem = _load_page_as_element(url, backlink, curr_depth, seen_urls)
        
        if new_elem is None:
            return
        
        for hook in get_hooks():
            _elem = getattr(hook, 'post_parse', lambda _, elem: elem)\
                        (_ctx(url, backlink, curr_depth, curr_segments, seen_urls), new_elem)
            if _elem is None:
                return
            new_elem = _elem

        log.debug("fetched", extra={"depth": curr_depth, "op": op, "url": url})
        
        if curr_depth <= max_depth:
            log.debug("queueing", extra={"depth": curr_depth, "op": op, "url": url})
            queue.append(Task(new_elem, curr_segments[1:], curr_depth+1, url))
        else:
            # NOTE: Should we pass instead of yield here?
            yield new_elem
    except requests.exceptions.RequestException as e:
        log.exception("error fetching url", extra={"depth": curr_depth, "op": op, "url": url})


@_op('url_from_attr')
def _handle_url_from_attr__no_return(curr_elem, curr_segments, curr_depth, queue, backlink, max_depth, seen_urls):
    """
    Handles the `[/|//]url(@<attr>)` (e.g., `...//url(@href)`) segment of a wxpath expression
    """
    op, value = curr_segments[0]
    if curr_elem is None:
        raise ValueError("Element must be provided when op is 'url_from_attr'.")
    
    url_op_arg = _extract_arg_from_url_xpath_op(value)
    if not url_op_arg.startswith('@'):
        raise ValueError("Only '@*' is supported in url() segments not at the start of path_expr.")
    
    _path_exp = '.' + value.split('url')[0] + url_op_arg

    urls = _get_absolute_links_from_elem_and_xpath(curr_elem, _path_exp)

    for url in urls:
        if url in seen_urls:
            log.debug("url seen", extra={"depth": curr_depth, "op": op, "url": url})
            continue
        try:
            if curr_depth <= max_depth:
                # Don't bump the depth here, just queue up the URL to be processed at the next depth
                queue.append(Task(None, [('url', url)] + curr_segments[1:], curr_depth, curr_elem.base_url))
            else:
                log.debug("reached max depth", extra={"depth": curr_depth, "op": op, "url": url})
        except requests.exceptions.RequestException as e:
            log.exception("error fetching url", extra={"depth": curr_depth, "op": op, "url": url})
            continue


@_op('url_inf')
def _handle_url_inf__no_return(curr_elem, curr_segments, curr_depth, queue, backlink, max_depth, seen_urls):
    """
    Handles the ///url() segment of a wxpath expression. This operation is also 
    generated internally by the parser when a `///<xpath>/[/]url()` segment is
    encountered by the parser.
    This operation does not fetch URLs; instead, it XPaths the current element
    for URLs, then queues them for further processing (see 
    _handle_url_inf_and_xpath__no_return).
    """
    op, value = curr_segments[0]

    if curr_depth > max_depth:
        log.debug("reached max depth", extra={"depth": curr_depth, "op": op, "url": getattr(curr_elem, 'base_url', None)})
        return
    
    _path_exp = _url_inf_filter_expr(value)

    urls = _get_absolute_links_from_elem_and_xpath(curr_elem, _path_exp)
    
    log.debug("found urls", extra={"depth": curr_depth, "op": op, "url": getattr(curr_elem, 'base_url', None), "url_count": len(urls)})


    for url in urls:
        if url in seen_urls:
            log.debug("url seen", extra={"depth": curr_depth, "op": op, "url": url})
            continue

        _segments = [('url_inf_and_xpath', (url, value))] + curr_segments[1:]
        
        log.debug("queueing", extra={"depth": curr_depth, "op": op, "url": url})
        # Not incrementing since we do not actually fetch the URL here
        queue.append(Task(None, _segments, curr_depth, curr_elem.base_url))


@_op('url_inf_and_xpath')
def _handle_url_inf_and_xpath__no_return(curr_elem, curr_segments, curr_depth, queue, backlink, max_depth, seen_urls):
    """
    This is an operation that is generated internally by the parser. There is
    no explicit wxpath expression that generates this operation.
    """
    op, value = curr_segments[0]
    url, prev_op_value = value
    if curr_elem is not None:
        raise ValueError("Cannot use 'url()' at the start of path_expr with an element provided.")
    if url in seen_urls:
        log.debug("url seen", extra={"depth": curr_depth, "op": op, "url": url})
        return
    try:
        new_elem = _load_page_as_element(url, backlink, curr_depth, seen_urls)
        
        if new_elem is None:
            return
        
        for hook in get_hooks():
            _elem = getattr(hook, 'post_parse', lambda _, elem: elem)\
                        (_ctx(url, backlink, curr_depth, curr_segments, seen_urls), new_elem)
            if _elem is None:
                return
            new_elem = _elem

        log.debug("fetched", extra={"depth": curr_depth, "op": op, "url": url})
        
        if curr_depth <= max_depth:
            # Queue the new element for further xpath evaluation
            log.debug("queueing", extra={"depth": curr_depth, "op": op, "url": url})

            queue.append(Task(new_elem, curr_segments[1:], curr_depth+1, new_elem.base_url))
            # For url_inf, also re-enqueue for further infinite expansion
            _segments = [('url_inf', prev_op_value)] + curr_segments[1:]
            queue.append(Task(new_elem, _segments, curr_depth+1, new_elem.base_url))
        else:
            log.debug("reached max depth", extra={"depth": curr_depth, "op": op, "url": url})
            pass
    except Exception as e:
        log.exception("error fetching url", extra={"depth": curr_depth, "op": op, "url": url})


@_op('xpath')
def _handle_xpath(curr_elem, curr_segments, curr_depth, queue, backlink, max_depth, seen_urls):
    """
    Handles the [/|//]<xpath> segment of a wxpath expression. This is a plain XPath expression.
    Also handles wxpath-specific macro expansions like wx:backlink() or wx:depth().
    """
    _, value = curr_segments[0]
    if curr_elem is None:
        raise ValueError("Element must be provided when path_expr does not start with 'url()'.")
    base_url = getattr(curr_elem, 'base_url', None)
    assert backlink == base_url, "Backlink must be equal to base_url"

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
            yield WxStr(elem, base_url=base_url, depth=curr_depth) if isinstance(elem, str) else elem
        else:
            queue.append(Task(elem, curr_segments[1:], curr_depth, base_url))


@_op('object')
def _handle_object(curr_elem, curr_segments, curr_depth, queue, backlink,
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