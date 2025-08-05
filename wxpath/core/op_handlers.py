"""
This module contains functions for handling each segment of a wxpath expression.
"""
import logging
import requests

from wxpath.core.models import Task, WxStr
from wxpath.hooks import get_hooks
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

log = logging.getLogger(__name__)


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
        log.debug(f"{curr_depth*'  '}[BFS][{op}] Skipping already seen URL: {url}")
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

        log.debug(f"{curr_depth*'  '}[BFS][{op}] Fetched URL: {url} curr_depth: {curr_depth} curr_segments[1:]: {curr_segments[1:]}")
        
        if curr_depth <= max_depth:
            log.debug(f"{curr_depth*'  '}[BFS][{op}] Queueing new element for further xpath evaluation curr_depth: {curr_depth} curr_segments[1:]: {curr_segments[1:]} url: {url}")
            queue.append(Task(new_elem, curr_segments[1:], curr_depth+1, url))
        else:
            # NOTE: Should we pass instead of yield here?
            yield new_elem
    except requests.exceptions.RequestException as e:
        log.error(f"{curr_depth*'  '}[BFS][{op}] Error fetching URL {url}: {e}")


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
            log.debug(f"{curr_depth*'  '}[BFS][{op}] Skipping already seen URL: {url}")
            continue
        try:
            if curr_depth <= max_depth:
                # Don't bump the depth here, just queue up the URL to be processed at the next depth
                queue.append(Task(None, [('url', url)] + curr_segments[1:], curr_depth, curr_elem.base_url))
            else:
                log.debug(f"{curr_depth*'  '}[BFS][{op}] Reached max depth for URL: {url}, not queuing further.")
        except requests.exceptions.RequestException as e:
            log.error(f"{curr_depth*'  '}[BFS][{op}] Error fetching URL {url}: {e}")
            continue


def _haldle_url_inf__no_return(curr_elem, curr_segments, curr_depth, queue, backlink, max_depth, seen_urls):
    """
    Handles the ///url() segment of a wxpath expression. This operation is also 
    generated internally by the parser when a `///<xpath>/[/]url()` segment is
    encountered by the parser.
    """
    op, value = curr_segments[0]

    _path_exp = _url_inf_filter_expr(value)

    urls = _get_absolute_links_from_elem_and_xpath(curr_elem, _path_exp)
    
    log.debug(f"{curr_depth*'  '}[BFS][{op}] Found {len(urls)} URLs from {getattr(curr_elem, 'base_url', None) if curr_elem is not None else None} at depth {curr_depth}")
    for url in urls:
        if url in seen_urls:
            log.debug(f"{curr_depth*'  '}[BFS][{op}] Skipping already seen URL: {url}")
            continue
        try:
            if curr_depth > max_depth:
                log.debug(f"{curr_depth*'  '}[BFS][{op}] Reached max depth for URL: {url}, not queuing further.")
                continue
            _segments = [('url_inf_and_xpath', (url, value))] + curr_segments[1:]
            log.debug(f"{curr_depth*'  '}[BFS][{op}] Queueing url_inf_and_xpath for URL: {url} with segments: {_segments}")
            # Not incrementing since we do not actually fetch the URL here
            queue.append(Task(None, _segments, curr_depth, curr_elem.base_url))

        except Exception as e:
            log.error(f"{curr_depth*'  '}[BFS][{op}] Error fetching URL {url}: {e}")
            continue


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
        log.debug(f"{curr_depth*'  '}[BFS][{op}] Skipping already seen URL: {url}")
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

        log.debug(f"{curr_depth*'  '}[BFS][{op}] Fetched URL: {url}")
        
        if curr_depth <= max_depth:
            # Queue the new element for further xpath evaluation
            log.debug(f"{curr_depth*'  '}[BFS][{op}] Queueing new element for further xpath evaluation curr_depth: {curr_depth} curr_segments[1:]: {curr_segments[1:]} url: {url}")
            queue.append(Task(new_elem, curr_segments[1:], curr_depth+1, new_elem.base_url))
            # For url_inf, also re-enqueue for further infinite expansion
            _segments = [('url_inf', prev_op_value)] + curr_segments[1:]
            log.debug(f"{curr_depth*'  '}[BFS][{op}] Queueing url_inf for URL: {url} with segments: {_segments}, new_elem: {new_elem}")
            queue.append(Task(new_elem, _segments, curr_depth+1, new_elem.base_url))
        else:
            log.debug(f"{curr_depth*'  '}[BFS][{op}] Reached max depth for URL: {url}, not queuing further.")
            pass
    except Exception as e:
        log.error(f"{curr_depth*'  '}[BFS][{op}] Error fetching URL {url}: {e}")


def _handle_xpath(curr_elem, curr_segments, curr_depth, queue, backlink, max_depth, seen_urls):
    """
    Handles the [/|//]<xpath> segment of a wxpath expression. This is a plain XPath expression.
    """
    _, value = curr_segments[0]
    if curr_elem is None:
        raise ValueError("Element must be provided when path_expr does not start with 'url()'.")
    base_url = getattr(curr_elem, 'base_url', None)
    elems = curr_elem.xpath3(value)
    
    for elem in elems:
        if len(curr_segments) == 1:
            yield WxStr(elem, base_url=base_url, depth=curr_depth) if isinstance(elem, str) else elem
        else:
            queue.append(Task(elem, curr_segments[1:], curr_depth, base_url))


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