import logging
from collections import deque

from wxpath import patches
from wxpath.core.models import Task
from wxpath.hooks import pipe_post_extract
from wxpath.core.helpers import _count_ops_with_url
from wxpath.core.parser import parse_wxpath_expr
from wxpath.core.op_handlers import (
    _handle_url,
    _handle_object,
    _handle_xpath,
    _haldle_url_inf__no_return,
    _handle_url_inf_and_xpath__no_return,
    _handle_url_from_attr__no_return
)

log = logging.getLogger(__name__)


@pipe_post_extract
def evaluate_wxpath_bfs_iter(elem, segments, max_depth=1, seen_urls=None, curr_depth=0):
    """
    BFS version of evaluate_wxpath.
    Processes all nodes at the current depth before moving deeper.
    """
    assert max_depth >= (_count_ops_with_url(segments) - 1) , (
        "max_depth+1 must be equal to or greater than the number of url* segments. "
        f"max_depth: {max_depth}, number of url* segments: {_count_ops_with_url(segments)}")
    assert len([op for op, _ in segments if op == 'url_inf']) <= 1, "Only one ///url() is allowed"
    
    if seen_urls is None:
        seen_urls = set()
    queue = deque()
    
    # Initialize the queue: start with the initial element (or URL segment)
    queue.append(Task(elem, segments, 0))

    iterations = 0
    while queue:
        iterations += 1
        if iterations % 100 == 0:
            log.debug(f"[BFS] Iteration {iterations}: Queue size: {len(queue)}, Current depth: {curr_depth}, Seen URLs: {len(seen_urls)}")
        
        curr_elem, curr_segments, curr_depth, backlink = queue.popleft()
        
        if not curr_segments:
            if curr_elem is not None:
                yield curr_elem
            continue

        op, value = curr_segments[0]
        log.debug(f"{curr_depth*'  '}[BFS] op: {op}, value: {value} depth={curr_depth} elem.base_url={getattr(curr_elem, 'base_url', None) if curr_elem is not None else None}")
        
        if op == 'url':
            yield from _handle_url(curr_elem, curr_segments, curr_depth, queue, backlink, max_depth, seen_urls)
        elif op == 'url_from_attr':
            _handle_url_from_attr__no_return(curr_elem, curr_segments, curr_depth, queue, backlink, max_depth, seen_urls)
        elif op == 'url_inf':
            _haldle_url_inf__no_return(curr_elem, curr_segments, curr_depth, queue, backlink, max_depth, seen_urls)
        elif op == 'url_inf_and_xpath':
            _handle_url_inf_and_xpath__no_return(curr_elem, curr_segments, curr_depth, queue, backlink, max_depth, seen_urls)
        elif op == 'xpath':
            yield from _handle_xpath(curr_elem, curr_segments, curr_depth, queue, backlink, max_depth, seen_urls)
        elif op == 'object':
            yield from _handle_object(curr_elem, curr_segments, curr_depth, queue,
                                      backlink, max_depth, seen_urls)
        else:
            raise ValueError(f"Unknown operation: {op}")

    return


def wxpath_iter(path_expr, max_depth=1):
    return filter(None, evaluate_wxpath_bfs_iter(None, parse_wxpath_expr(path_expr), max_depth=max_depth))


def wxpath(path_expr, max_depth=1):
    return list(wxpath_iter(path_expr, max_depth=max_depth))
