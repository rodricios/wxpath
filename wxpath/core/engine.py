import re
import inspect

from collections import deque
from lxml import etree, html
from urllib.parse import urljoin

from wxpath.core import patches
from wxpath.core.models import WxStr, Task
from wxpath.core.http import fetch_html, parse_html, make_links_absolute


def wrap_strings(results, url):
    return [WxStr(s, base_url=url) if isinstance(s, str) else s for s in results]


def extract_arg_from_url_xpath_op(url_subsegment):
    match = re.search(r"url\((.+)\)", url_subsegment)
    if not match:
        raise ValueError(f"Invalid url() segment: {url_subsegment}")
    return match.group(1).strip("'\"")  # Remove surrounding quotes if any


def parse_wxpath_expr(path_expr):
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
    if len([op for op, val in parsed if op == 'url_inf']) > 1:
        raise ValueError("Only one ///url() is allowed")
    
    # Raises if multiple url() are present
    if len([op for op, val in parsed if op == 'url']) > 1:
        raise ValueError("Only one url() is allowed")
    
    # Raises when expr starts with //url(@<attr>)
    if parsed and parsed[0][0] == 'url_from_attr':
        raise ValueError("Path expr cannot start with [//]url(@<attr>)")
    
    return parsed
    

def apply_to_crawler(html_handler):
    signature = inspect.signature(evaluate_wxpath_bfs_iter)
    html_handlers = signature.parameters.get("html_handlers").default # type: list
    html_handlers.append(html_handler)
    return html_handler


def wxpath(elem, path_expr, items=None, depth=1, debug_indent=0):
    print(f"{debug_indent*'  '}wxpath called with path_expr: {path_expr}")
    
    segments = parse_wxpath_expr(path_expr)
    return list(evaluate_wxpath_bfs_iter(elem, segments, items, depth=depth, debug_indent=debug_indent))


def evaluate_wxpath_bfs_iter(elem, segments, max_depth=1, seen_urls=None, curr_depth=0, html_handlers=[], _graph_integration=None):
    """
    BFS version of evaluate_wxpath.
    Processes all nodes at the current depth before moving deeper.
    """

    assert len([op for op, val in segments if op == 'url_inf']) <= 1, "Only one ///url() is allowed"
    
    if seen_urls is None:
        seen_urls = set()
    queue = deque()
    
    # Initialize the queue: start with the initial element (or URL segment)
    # Get session_id from graph integration if available
    session_id = getattr(_graph_integration, '_current_session_id', None) if _graph_integration else None
    initial_task = Task(elem, segments, 0, session_id=session_id)
    queue.append(initial_task)

    iterations = 0
    while queue:

        iterations += 1
        if iterations % 100 == 0:
            print(f"[BFS] Iteration {iterations}: Queue size: {len(queue)}, Current depth: {curr_depth}, Seen URLs: {len(seen_urls)}")
        
        task = queue.popleft()
        curr_elem, curr_segments, curr_depth, backlink = task
        session_id = task.session_id
        parent_page_url = task.parent_page_url or getattr(curr_elem, 'base_url', None)
        
        if not curr_segments:
            if curr_elem is not None:
                yield curr_elem
            continue

        op, value = curr_segments[0]
        print(f"{curr_depth*'  '}[BFS] op: {op}, value: {value} depth={curr_depth} elem.base_url={getattr(curr_elem, 'base_url', None) if curr_elem else None}")
        
        if op == 'url':
            # NOTE: Should I allow curr_elem to be not None? 
            #   Pros: when adding backling attrib to new_elem, it's easy to add it from curr_elem.base_url. 
            #   Cons: curr_elem.base_url might not be set. Also, we keep an extra reference to curr_elem for the next level - could potentially cause a memory leak.
            if curr_elem is not None:
                raise ValueError("Cannot use 'url()' at the start of path_expr with an element provided.")
            if value.startswith('@'):
                raise ValueError("Cannot use '@' in url() segment at the start of path_expr.")
            if value in seen_urls:
                print(f"{curr_depth*'  '}[BFS][{op}] Skipping already seen URL: {value}")
                continue

            try:
                html_content = fetch_html(value)
                new_elem = html.fromstring(html_content, base_url=value)
                new_elem.set('backlink', backlink)
                if html_handlers:
                    for handler in html_handlers:
                        new_elem = handler(new_elem)
                seen_urls.add(value)
                print(f"{curr_depth*'  '}[BFS][{op}] Fetched URL: {value} curr_depth: {curr_depth} curr_segments[1:]: {curr_segments[1:]}")
                
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
                    print(f"{curr_depth*'  '}[BFS][{op}] Queueing new element for further xpath evaluation curr_depth: {curr_depth} curr_segments[1:]: {curr_segments[1:]} url: {value}")
                    next_task = Task(new_elem, curr_segments[1:], curr_depth+1, backlink=value, 
                                   parent_page_url=value, session_id=session_id)
                    queue.append(next_task)
                else:
                    yield new_elem
            except Exception as e:
                print(f"{curr_depth*'  '}[BFS][{op}] Error fetching URL {value}: {e}")
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
                    print(f"{curr_depth*'  '}[BFS][{op}] Skipping already seen URL: {url}")
                    continue
                try:
                    # Graph event: URL discovered
                    if _graph_integration and _graph_integration.is_enabled() and parent_page_url:
                        _graph_integration.pipeline.on_url_discovered(
                            source_url=parent_page_url,
                            target_url=url,
                            session_id=session_id
                        )
                    
                    if curr_depth <= max_depth:
                        # Don't bump the depth here, just queue up the URL to be processed at the next depth
                        next_task = Task(None, [('url', url)] + curr_segments[1:], curr_depth, 
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
                    print(f"{curr_depth*'  '}[BFS][{op}] Error fetching URL {url}: {e}")
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
            
            print(f"{curr_depth*'  '}[BFS][{op}] Found {len(urls)} URLs from {getattr(curr_elem, 'base_url', None) if curr_elem else None} at depth {curr_depth}")
            for url in urls:
                if url in seen_urls:
                    print(f"{curr_depth*'  '}[BFS][{op}] Skipping already seen URL: {url}")
                    continue
                try:
                    if curr_depth > max_depth:
                        print(f"{curr_depth*'  '}[BFS][{op}] Reached max depth for URL: {url}, not queuing further.")
                        # seen_urls.add(url)
                        # print(f"{curr_depth*'  '}[BFS][{op}] Yielding URL: {url}")
                        # yield html.fromstring(fetch_html(url), base_url=url)
                        continue
                    # Graph event: URL discovered  
                    if _graph_integration and _graph_integration.is_enabled() and parent_page_url:
                        _graph_integration.pipeline.on_url_discovered(
                            source_url=parent_page_url,
                            target_url=url,
                            session_id=session_id
                        )
                    
                    _segments = [('url_inf_2', (url, value))] + curr_segments[1:]
                    print(f"{curr_depth*'  '}[BFS][{op}] Queueing url_inf_2 for URL: {url} with segments: {_segments}")
                    # Not incrementing since we do not actually fetch the URL here
                    next_task = Task(None, _segments, curr_depth, backlink=curr_elem.base_url,
                                   parent_page_url=parent_page_url, session_id=session_id, 
                                   discovered_from_url=parent_page_url)
                    queue.append(next_task)

                except Exception as e:
                    print(f"{curr_depth*'  '}[BFS][{op}] Error fetching URL {url}: {e}")
                    continue

        elif op == 'url_inf_2':
            url, prev_op_value = value
            if curr_elem is not None:
                raise ValueError("Cannot use 'url()' at the start of path_expr with an element provided.")
            if url in seen_urls:
                print(f"{curr_depth*'  '}[BFS][{op}] Skipping already seen URL: {url}")
                continue
            try:
                html_content = fetch_html(url)
                new_elem = html.fromstring(html_content, base_url=url)
                new_elem.set('backlink', backlink)
                if html_handlers:
                    for handler in html_handlers:
                        new_elem = handler(new_elem)
                seen_urls.add(url)
                print(f"{curr_depth*'  '}[BFS][{op}] Fetched URL: {url}")
                
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
                    print(f"{curr_depth*'  '}[BFS][{op}] Queueing new element for further xpath evaluation curr_depth: {curr_depth} curr_segments[1:]: {curr_segments[1:]} url: {url}")
                    next_task1 = Task(new_elem, curr_segments[1:], curr_depth+1, backlink=new_elem.base_url,
                                    parent_page_url=url, session_id=session_id)
                    queue.append(next_task1)
                    # For url_inf, also re-enqueue for further infinite expansion
                    _segments = [('url_inf', prev_op_value)] + curr_segments[1:]
                    print(f"{curr_depth*'  '}[BFS][{op}] Queueing url_inf for URL: {url} with segments: {_segments}, new_elem: {new_elem}")
                    next_task2 = Task(new_elem, _segments, curr_depth+1, backlink=new_elem.base_url,
                                    parent_page_url=url, session_id=session_id)
                    queue.append(next_task2)
                else:
                    # print(f"{curr_depth*'  '}[BFS][{op}] Reached max depth for URL: {url}, not queuing further.")
                    # queue.append(Task(new_elem, curr_segments[1:], curr_depth+1, new_elem.base_url))
                    # yield new_elem
                    pass
            except Exception as e:
                print(f"{curr_depth*'  '}[BFS][{op}] Error fetching URL {url}: {e}")
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
                            print(f"{curr_depth*'  '}[BFS][{op}] Skipping already seen URL: {url}")
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
                                # TODO: Should I just queue this up as a `url` op?
                                seen_urls.add(url)
                                yield html.fromstring(fetch_html(url), base_url=url)
                        except Exception as e:
                            print(f"{curr_depth*'  '}[BFS][{op}] Error fetching URL {url}: {e}")
                            continue
                else:
                    raise ValueError(f"Unexpected segment pattern after XPath: {next_op}")
        else:
            raise ValueError(f"Unknown operation: {op}")

    return