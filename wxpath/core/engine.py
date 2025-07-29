import re
import inspect
import logging
from typing import List, Tuple, Union, Optional, Iterator, Any, Callable, Set

from collections import deque
from lxml import etree, html
from urllib.parse import urljoin

from wxpath.core import patches
from wxpath.core.models import WxStr, Task
from wxpath.core.http import fetch_html, parse_html, make_links_absolute

# Configure logging for wxpath engine
logger = logging.getLogger(__name__)

# Memory management constants
MAX_QUEUE_SIZE = 10000
MAX_SEEN_URLS = 50000
MAX_ITERATIONS = 100000

# XPath validation constants
MAX_XPATH_LENGTH = 5000
MAX_XPATH_COMPLEXITY = 100  # Max number of operators/functions
DISALLOWED_XPATH_FUNCTIONS = [
    'document', 'doc', 'system-property', 'unparsed-entity-uri',
    'generate-id', 'function-available', 'element-available'
]


def validate_xpath_expression(xpath_expr: str) -> None:
    """Validate XPath expression for security and complexity.
    
    Args:
        xpath_expr: The XPath expression to validate
        
    Raises:
        ValueError: If the expression is invalid, too complex, or contains disallowed functions
    """
    if not xpath_expr or not isinstance(xpath_expr, str):
        raise ValueError("XPath expression must be a non-empty string")
    
    if len(xpath_expr) > MAX_XPATH_LENGTH:
        raise ValueError(f"XPath expression too long: {len(xpath_expr)} > {MAX_XPATH_LENGTH}")
    
    # Check for disallowed functions
    xpath_lower = xpath_expr.lower()
    for func in DISALLOWED_XPATH_FUNCTIONS:
        if f"{func}(" in xpath_lower:
            raise ValueError(f"Disallowed XPath function: {func}")
    
    # Count complexity indicators (rough estimate)
    complexity_indicators = [
        '/', '//', '[', ']', '(', ')', '@', ':', '|', '+', '-', '*', 
        'and', 'or', 'not', 'contains', 'starts-with', 'text()', 'node()'
    ]
    
    complexity_count = sum(xpath_expr.count(indicator) for indicator in complexity_indicators)
    
    if complexity_count > MAX_XPATH_COMPLEXITY:
        raise ValueError(f"XPath expression too complex: {complexity_count} > {MAX_XPATH_COMPLEXITY}")
    
    # Check for potential infinite loops or very deep nesting
    if xpath_expr.count('//') > 10:
        raise ValueError("Too many '//' operators - potential performance issue")
    
    # Basic syntax validation - check for balanced brackets and parentheses
    brackets = xpath_expr.count('[') - xpath_expr.count(']')
    parens = xpath_expr.count('(') - xpath_expr.count(')')
    
    if brackets != 0:
        raise ValueError("Unbalanced square brackets in XPath expression")
    if parens != 0:
        raise ValueError("Unbalanced parentheses in XPath expression")


def wrap_strings(results: List[Union[str, Any]], url: str) -> List[Union[WxStr, Any]]:
    """Wrap string results with WxStr to maintain base URL context."""
    return [WxStr(s, base_url=url) if isinstance(s, str) else s for s in results]


def extract_arg_from_url_xpath_op(url_subsegment: str) -> str:
    """Extract the argument from a url() XPath operation.
    
    Args:
        url_subsegment: The url() segment to extract from
        
    Returns:
        The extracted URL or attribute argument
        
    Raises:
        ValueError: If the segment is not a valid url() operation
    """
    match = re.search(r"url\((.+)\)", url_subsegment)
    if not match:
        raise ValueError(f"Invalid url() segment: {url_subsegment}")
    return match.group(1).strip("'\"")  # Remove surrounding quotes if any


def parse_wxpath_expr(path_expr: str) -> List[Tuple[str, str]]:
    """Parse a wxpath expression into operation segments.
    
    Args:
        path_expr: The wxpath expression to parse
        
    Returns:
        List of tuples containing (operation_type, value) pairs
        
    Raises:
        ValueError: For invalid or unsupported expressions
    """
    segments = []
    i = 0
    n = len(path_expr)
    while i < n:
        # Detect ///url(, //url(, /url(, or url(
        match = re.match(r'/{0,3}url\(', path_expr[i:])
        if match:
            seg_start = i
            i += match.end()  # Move past the matched "url("
            paren_depth = 1
            while i < n and paren_depth > 0:
                if path_expr[i] == '(':
                    paren_depth += 1
                elif path_expr[i] == ')':
                    paren_depth -= 1
                i += 1
            segments.append(path_expr[seg_start:i])
        else:
            # Grab until the next /url(
            next_url = re.search(r'/{0,3}url\(', path_expr[i:])
            next_pos = next_url.start() + i if next_url else n
            if i != next_pos:
                segments.append(path_expr[i:next_pos])
            i = next_pos

    parsed = []
    for s in segments:
        s = s.strip()
        if not s:
            continue
        if s.startswith('url("') or s.startswith("url('"):
            parsed.append(('url', extract_arg_from_url_xpath_op(s)))
        elif s.startswith('/url(@') or s.startswith('//url(@'):
            parsed.append(('url_from_attr', s))
        elif s.startswith('///url('):
            parsed.append(('url_inf', s))
        elif s.startswith('/url("') or s.startswith('//url("'):  # RAISE ERRORS FROM INVALID SEGMENTS
            raise ValueError(f"url() segment cannot have fixed-length argument and preceding navigation slashes (/|//): {s}")
        elif s.startswith("/url('") or s.startswith("//url('"):  # RAISE ERRORS FROM INVALID SEGMENTS
            raise ValueError(f"url() segment cannot have fixed-length argument and preceding navigation slashes (/|//): {s}")
        elif s.startswith('/url(') or s.startswith("//url("):    # RAISE ERRORS FROM INVALID SEGMENTS
            # Reaching this presumes an unsupported value
            raise ValueError(f"Unsupported url() segment: {s}")
        else:
            parsed.append(('xpath', s))
    
    #### RAISE ERRORS FROM INVALID SEGMENTS ####
    
    # Raises if multiple ///url() are present
    if len([op for op, _ in parsed if op == 'url_inf']) > 1:
        raise ValueError("Only one ///url() is allowed")
    
    # Raises if multiple url() are present
    if len([op for op, _ in parsed if op == 'url']) > 1:
        raise ValueError("Only one url() is allowed")
    
    # Raises when expr starts with //url(@<attr>)
    if parsed and parsed[0][0] == 'url_from_attr':
        raise ValueError("Path expr cannot start with [//]url(@<attr>)")
    
    return parsed
    

def apply_to_crawler(html_handler: Callable[[html.HtmlElement], html.HtmlElement]) -> Callable[[html.HtmlElement], html.HtmlElement]:
    """Register an HTML handler to be applied to all fetched pages.
    
    Args:
        html_handler: Function that takes and returns an HTML element
        
    Returns:
        The same handler function (for decorator pattern)
    """
    signature = inspect.signature(evaluate_wxpath_bfs_iter)
    html_handlers: List[Callable] = signature.parameters.get("html_handlers").default
    html_handlers.append(html_handler)
    return html_handler


def wxpath(elem: Optional[html.HtmlElement], 
           path_expr: str, 
           items: Optional[List[Any]] = None, 
           depth: int = 1, 
           debug_indent: int = 0) -> List[Union[html.HtmlElement, WxStr, str]]:
    """Execute wxpath expression on element with specified depth.
    
    Args:
        elem: HTML element to start from (None for URL-based expressions)
        path_expr: XPath expression with wxpath extensions
        items: Optional list of items (deprecated)
        depth: Maximum crawling depth (default: 1)
        debug_indent: Debug indentation level (deprecated)
        
    Returns:
        List of matching elements or text content
        
    Raises:
        ValueError: For invalid expressions or unsupported operations
    """
    logger.debug("wxpath called with path_expr: %s", path_expr)
    
    # Validate the path expression for security and complexity
    validate_xpath_expression(path_expr)
    
    segments = parse_wxpath_expr(path_expr)
    return list(evaluate_wxpath_bfs_iter(elem, segments, items=items, max_depth=depth, debug_indent=debug_indent))


def evaluate_wxpath_bfs_iter(
    elem: Optional[html.HtmlElement], 
    segments: List[Tuple[str, str]], 
    items: Optional[List[Any]] = None,
    max_depth: int = 1, 
    seen_urls: Optional[Set[str]] = None, 
    curr_depth: int = 0, 
    html_handlers: Optional[List[Callable]] = None, 
    _graph_integration: Optional[Any] = None,
    debug_indent: int = 0,
    max_queue_size: int = MAX_QUEUE_SIZE,
    max_seen_urls: int = MAX_SEEN_URLS,
    max_iterations: int = MAX_ITERATIONS
) -> Iterator[Union[html.HtmlElement, WxStr, str]]:
    """
    BFS version of evaluate_wxpath.
    Processes all nodes at the current depth before moving deeper.
    
    Args:
        elem: Starting HTML element (None for URL-based expressions)
        segments: Parsed wxpath expression segments
        items: Optional list of items (deprecated)
        max_depth: Maximum crawling depth
        seen_urls: Set of already visited URLs
        curr_depth: Current depth in crawling
        html_handlers: Optional list of HTML processing functions
        _graph_integration: Optional graph integration object
        debug_indent: Debug indentation level (deprecated)
        max_queue_size: Maximum number of tasks in queue (memory management)
        max_seen_urls: Maximum number of URLs to remember (memory management)
        max_iterations: Maximum total iterations to prevent infinite loops
        
    Yields:
        HTML elements, WxStr objects, or strings from the crawl
        
    Raises:
        MemoryError: When memory limits are exceeded
        RuntimeError: When iteration limits are exceeded
    """

    assert len([op for op, _ in segments if op == 'url_inf']) <= 1, "Only one ///url() is allowed"
    
    if seen_urls is None:
        seen_urls = set()
    if html_handlers is None:
        html_handlers = []
    queue = deque()
    
    # Initialize the queue: start with the initial element (or URL segment)
    # Get session_id from graph integration if available
    session_id = getattr(_graph_integration, '_current_session_id', None) if _graph_integration else None
    initial_task = Task(elem, segments, 0, session_id=session_id)
    queue.append(initial_task)

    iterations = 0
    try:
        while queue:
            # Memory and iteration limits
            if iterations >= max_iterations:
                logger.error("Maximum iterations exceeded: %d", max_iterations)
                raise RuntimeError(f"Maximum iteration limit ({max_iterations}) exceeded")
                
            if len(queue) > max_queue_size:
                logger.error("Queue size exceeded: %d > %d", len(queue), max_queue_size)
                raise MemoryError(f"Queue size limit ({max_queue_size}) exceeded")
                
            if len(seen_urls) > max_seen_urls:
                logger.warning("Seen URLs limit exceeded: %d > %d. Clearing oldest entries.", 
                             len(seen_urls), max_seen_urls)
                # Keep only the most recent URLs by converting to list, slicing, and back to set
                seen_urls_list = list(seen_urls)
                seen_urls = set(seen_urls_list[-max_seen_urls//2:])  # Keep half

            iterations += 1
            if iterations % 100 == 0:
                logger.info("BFS Iteration %d: Queue size: %d, Current depth: %d, Seen URLs: %d", 
                           iterations, len(queue), curr_depth, len(seen_urls))
            
            task = queue.popleft()
            curr_elem, curr_segments, curr_depth, backlink = task
            session_id = task.session_id
            parent_page_url = task.parent_page_url or getattr(curr_elem, 'base_url', None)
            
            if not curr_segments:
                if curr_elem is not None:
                    yield curr_elem
                continue

            op, value = curr_segments[0]
            elem_base_url = getattr(curr_elem, 'base_url', None) if curr_elem else None
            logger.debug("BFS op: %s, value: %s, depth: %d, elem.base_url: %s", 
                        op, value, curr_depth, elem_base_url)
            
            if op == 'url':
                # NOTE: Should I allow curr_elem to be not None? 
                #   Pros: when adding backling attrib to new_elem, it's easy to add it from curr_elem.base_url. 
                #   Cons: curr_elem.base_url might not be set. Also, we keep an extra reference to curr_elem for the next level - could potentially cause a memory leak.
                if curr_elem is not None:
                    raise ValueError("Cannot use 'url()' at the start of path_expr with an element provided.")
                if value.startswith('@'):
                    raise ValueError("Cannot use '@' in url() segment at the start of path_expr.")
                if value in seen_urls:
                    logger.debug("BFS[%s] Skipping already seen URL: %s", op, value)
                    continue

                try:
                    html_content = fetch_html(value)
                    new_elem = html.fromstring(html_content, base_url=value)
                    new_elem.set('backlink', backlink)
                    if html_handlers:
                        for handler in html_handlers:
                            new_elem = handler(new_elem)
                    seen_urls.add(value)
                    logger.debug("BFS[%s] Fetched URL: %s at depth: %d, remaining segments: %s", 
                               op, value, curr_depth, curr_segments[1:])
                    
                    # Graph event: page fetched
                    if _graph_integration and _graph_integration.is_enabled():
                        _graph_integration.pipeline.on_page_fetched(
                            url=value,
                            elem=new_elem,
                            depth=curr_depth,
                            parent_url=parent_page_url,
                            session_id=session_id
                        )
                    
                    if curr_depth <= max_depth:
                        logger.debug("BFS[%s] Queueing element for xpath evaluation at depth: %d, url: %s", 
                                   op, curr_depth, value)
                        next_task = Task(new_elem, curr_segments[1:], curr_depth+1, backlink=value, 
                                       parent_page_url=value, session_id=session_id)
                        queue.append(next_task)
                    else:
                        yield new_elem
                except Exception as e:
                    logger.warning("BFS[%s] Error fetching URL %s: %s", op, value, e)
                    continue

            elif op == 'url_from_attr':
                if curr_elem is None:
                    raise ValueError("Element must be provided when op is 'url_from_attr'.")
                url_op_arg = extract_arg_from_url_xpath_op(value)
                if not url_op_arg.startswith('@'):
                    raise ValueError("Only '@*' is supported in url() segments not at the start of path_expr.")
                _path_exp = value.split('url')[0] + url_op_arg
                elems = curr_elem.xpath(_path_exp)
                base_url = getattr(curr_elem, 'base_url', None)
                urls = make_links_absolute(elems, base_url)

                for url in urls:
                    if url in seen_urls:
                        logger.debug("BFS[%s] Skipping already seen URL: %s", op, url)
                        continue
                    try:
                        # Graph event: URL discovered
                        if _graph_integration and _graph_integration.is_enabled() and parent_page_url:
                            _graph_integration.pipeline.on_url_discovered(
                                source_url=parent_page_url,
                                target_url=url,
                                session_id=session_id
                            )
                        
                        if curr_depth < max_depth:
                            # Queue up the URL to be processed at the next depth
                            next_task = Task(None, [('url', url)] + curr_segments[1:], curr_depth + 1, 
                                           backlink=curr_elem.base_url, parent_page_url=parent_page_url,
                                           session_id=session_id, discovered_from_url=parent_page_url)
                            queue.append(next_task)
                        # else:
                        #     # TODO: Should I just queue this up as a `url` op?
                        #     seen_urls.add(url)
                        #     elem = html.fromstring(fetch_html(url), base_url=url)
                        #     elem.set('backlink', curr_elem.base_url)
                        #     yield elem
                        # seen_urls.add(url)
                    except Exception as e:
                        logger.warning("BFS[%s] Error processing URL %s: %s", op, url, e)
                        continue

            elif op == 'url_inf':
                # Infinite crawl
                url_op_arg = extract_arg_from_url_xpath_op(value)
                if not url_op_arg.startswith('@'):
                    raise ValueError("Only '@*' is supported in url() segments for infinite crawl.")
                _path_exp = ".//" + url_op_arg
                elems = curr_elem.xpath(_path_exp)
                base_url = getattr(curr_elem, 'base_url', None)
                urls = make_links_absolute(elems, base_url)
                
                source_url = getattr(curr_elem, 'base_url', None) if curr_elem else None
                logger.debug("BFS[%s] Found %d URLs from %s at depth %d", op, len(urls), source_url, curr_depth)
                for url in urls:
                    if url in seen_urls:
                        logger.debug("BFS[%s] Skipping already seen URL: %s", op, url)
                        continue
                    try:
                        if curr_depth >= max_depth:
                            logger.debug("BFS[%s] Reached max depth for URL: %s, not queuing further", op, url)
                            continue
                        # Graph event: URL discovered  
                        if _graph_integration and _graph_integration.is_enabled() and parent_page_url:
                            _graph_integration.pipeline.on_url_discovered(
                                source_url=parent_page_url,
                                target_url=url,
                                session_id=session_id
                            )
                        
                        _segments = [('url_inf_2', (url, value))] + curr_segments[1:]
                        logger.debug("BFS[%s] Queueing url_inf_2 for URL: %s with segments: %s", op, url, _segments)
                        # Not incrementing since we do not actually fetch the URL here
                        next_task = Task(None, _segments, curr_depth, backlink=curr_elem.base_url,
                                       parent_page_url=parent_page_url, session_id=session_id, 
                                       discovered_from_url=parent_page_url)
                        queue.append(next_task)

                    except Exception as e:
                        logger.warning("BFS[%s] Error processing URL %s: %s", op, url, e)
                        continue

            elif op == 'url_inf_2':
                url, prev_op_value = value
                if curr_elem is not None:
                    raise ValueError("Cannot use 'url()' at the start of path_expr with an element provided.")
                if url in seen_urls:
                    logger.debug("BFS[%s] Skipping already seen URL: %s", op, url)
                    continue
                try:
                    html_content = fetch_html(url)
                    new_elem = html.fromstring(html_content, base_url=url)
                    new_elem.set('backlink', backlink)
                    if html_handlers:
                        for handler in html_handlers:
                            new_elem = handler(new_elem)
                    seen_urls.add(url)
                    logger.debug("BFS[%s] Fetched URL: %s", op, url)
                    
                    # Graph event: page fetched
                    if _graph_integration and _graph_integration.is_enabled():
                        _graph_integration.pipeline.on_page_fetched(
                            url=url,
                            elem=new_elem,
                            depth=curr_depth,
                            parent_url=parent_page_url,
                            session_id=session_id
                        )
                    
                    # If no more segments, it means user wants to fetch the html elements
                    # if not curr_segments[1:]:
                    #     print(f"{curr_depth*'  '}[BFS][{op}] Yielding URL: {url}")
                    #     # OR queue.append(Task(new_elem, curr_segments[1:], curr_depth+1, new_elem.base_url))
                    #     yield new_elem
                    
                    if curr_depth <= max_depth:
                        # Queue the new element for further xpath evaluation
                        logger.debug("BFS[%s] Queueing element for xpath evaluation at depth: %d, url: %s", 
                                   op, curr_depth, url)
                        next_task1 = Task(new_elem, curr_segments[1:], curr_depth+1, backlink=new_elem.base_url,
                                        parent_page_url=url, session_id=session_id)
                        queue.append(next_task1)
                        # For url_inf, also re-enqueue for further infinite expansion
                        _segments = [('url_inf', prev_op_value)] + curr_segments[1:]
                        logger.debug("BFS[%s] Queueing url_inf for URL: %s with segments: %s", 
                                   op, url, _segments)
                        next_task2 = Task(new_elem, _segments, curr_depth+1, backlink=new_elem.base_url,
                                        parent_page_url=url, session_id=session_id)
                        queue.append(next_task2)
                    else:
                        # print(f"{curr_depth*'  '}[BFS][{op}] Reached max depth for URL: {url}, not queuing further.")
                        # queue.append(Task(new_elem, curr_segments[1:], curr_depth+1, new_elem.base_url))
                        # yield new_elem
                        pass
                except Exception as e:
                    logger.warning("BFS[%s] Error fetching URL %s: %s", op, url, e)
                    continue

            elif op == 'xpath':
                if curr_elem is None:
                    raise ValueError("Element must be provided when path_expr does not start with 'url()'.")
                base_url = getattr(curr_elem, 'base_url', None)
                if len(curr_segments) == 1:
                    elems = curr_elem.xpath(value)
                    for elem in elems:
                        # Graph event: element extracted (for final results)
                        if (_graph_integration and _graph_integration.is_enabled() and 
                            parent_page_url and hasattr(elem, 'tag')):
                            _graph_integration.pipeline.on_element_extracted(
                                page_url=parent_page_url,
                                element=elem,
                                xpath=value,
                                session_id=session_id
                            )
                        
                        yield WxStr(elem, base_url=base_url) if isinstance(elem, str) else elem
                else:
                    next_op, next_val = curr_segments[1]
                    # NOTE: we look ahead because it's more efficient to retrieve all childs URLs at once, as opposed to queue up.
                    # Consider modifying this logic to queue up URLs at a top level operation handler.
                    if next_op == 'url_from_attr':
                        url_or_attr = extract_arg_from_url_xpath_op(next_val)
                        if not url_or_attr.startswith('@'):
                            raise ValueError("Only '@*' is supported in url() segments not at the start of path_expr.")
                        _path_exp = value.strip() + next_val.split('url')[0] + url_or_attr
                        elems = curr_elem.xpath(_path_exp)
                        urls = make_links_absolute(elems, base_url)
                        for url in urls:
                            if url in seen_urls:
                                logger.debug("BFS[%s] Skipping already seen URL: %s", op, url)
                                continue
                            try:
                                # Graph event: URL discovered
                                if _graph_integration and _graph_integration.is_enabled() and parent_page_url:
                                    _graph_integration.pipeline.on_url_discovered(
                                        source_url=parent_page_url,
                                        target_url=url,
                                        xpath=_path_exp,
                                        session_id=session_id
                                    )
                                
                                if curr_depth < max_depth:
                                    next_task = Task(None, [('url', url)] + curr_segments[2:], curr_depth+1, 
                                                   backlink=base_url, parent_page_url=parent_page_url,
                                                   session_id=session_id, discovered_from_url=parent_page_url)
                                    queue.append(next_task)
                                else:
                                    # At max depth, fetch and yield the URL directly
                                    try:
                                        seen_urls.add(url)
                                        html_content = fetch_html(url)
                                        yield html.fromstring(html_content, base_url=url)
                                    except Exception as e:
                                        logger.warning("BFS[%s] Error fetching URL at max depth %s: %s", op, url, e)
                            except Exception as e:
                                logger.warning("BFS[%s] Error processing URL %s: %s", op, url, e)
                                continue
                    else:
                        raise ValueError(f"Unexpected segment pattern after XPath: {next_op}")
            else:
                raise ValueError(f"Unknown operation: {op}")
    
    finally:
        # Cleanup: Clear any remaining references to help with garbage collection
        if 'queue' in locals():
            queue.clear()
        if 'seen_urls' in locals():
            seen_urls.clear()
        logger.debug("BFS iterator cleanup completed")

    return