import re
import requests
import inspect

from collections import deque
from lxml import etree, html
from urllib.parse import urljoin

from wxpath import patches
from wxpath.models import WxStr, Task


def fetch_html(url):
    response = requests.get(url, timeout=10)
    response.raise_for_status()
    return response.content


def parse_html(content):
    return etree.HTML(content)


def make_links_absolute(links, base_url):
    """
    Convert relative links to absolute links based on the base URL.

    Args:
        links (list): List of link strings.
        base_url (str): The base URL to resolve relative links against.

    Returns:
        List of absolute URLs.
    """
    if base_url is None:
        raise ValueError("base_url must not be None when making links absolute.")
    return [urljoin(base_url, link) for link in links if link]


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
        elif s.startswith('///'):
            parsed.append(('inf_xpath', "//" + s[3:]))
        else:
            parsed.append(('xpath', s))
    
    # Collapes inf_xpath segment and the succeeding url_from_attr segment into a single url_inf segment
    for i in range(len(parsed) - 1):
        if parsed[i][0] == 'inf_xpath' and parsed[i + 1][0] == 'url_from_attr':
            inf_xpath_value = parsed[i][1]
            url_from_attr_value = extract_arg_from_url_xpath_op(parsed[i + 1][1])
            url_from_attr_traveral_fragment = parsed[i + 1][1].split('url')[0]
            parsed[i] = (
                'url_inf', 
                f'///url({inf_xpath_value}{url_from_attr_traveral_fragment}{url_from_attr_value})'
            )
            parsed.pop(i + 1)
    
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


def url_inf_filter_expr(url_op_and_arg):
    url_op_arg = extract_arg_from_url_xpath_op(url_op_and_arg)
    if url_op_arg.startswith('@'):
        return ".//" + url_op_arg
    else:
        return url_op_arg


def count_ops_with_url(segments):
    return len([op for op, _ in segments if op.startswith('url')])


def evaluate_wxpath_bfs_iter(elem, segments, max_depth=1, seen_urls=None, curr_depth=0, html_handlers=[]):
    """
    BFS version of evaluate_wxpath.
    Processes all nodes at the current depth before moving deeper.
    """
    assert max_depth >= (count_ops_with_url(segments) - 1) , "max_depth+1 must be equal to or greater than the number of url* segments. " +\
        f"max_depth: {max_depth}, number of url* segments: {count_ops_with_url(segments)}"
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
            print(f"[BFS] Iteration {iterations}: Queue size: {len(queue)}, Current depth: {curr_depth}, Seen URLs: {len(seen_urls)}")
        
        curr_elem, curr_segments, curr_depth, backlink = queue.popleft()
        
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
                new_elem.set('depth', str(curr_depth))
                if html_handlers:
                    for handler in html_handlers:
                        new_elem = handler(new_elem)
                seen_urls.add(value)
                print(f"{curr_depth*'  '}[BFS][{op}] Fetched URL: {value} curr_depth: {curr_depth} curr_segments[1:]: {curr_segments[1:]}")
                
                if curr_depth <= max_depth:
                    print(f"{curr_depth*'  '}[BFS][{op}] Queueing new element for further xpath evaluation curr_depth: {curr_depth} curr_segments[1:]: {curr_segments[1:]} url: {value}")
                    queue.append(Task(new_elem, curr_segments[1:], curr_depth+1, value))
                else:
                    yield new_elem
            except requests.exceptions.RequestException as e:
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
                    if curr_depth <= max_depth:
                        # Don't bump the depth here, just queue up the URL to be processed at the next depth
                        queue.append(Task(None, [('url', url)] + curr_segments[1:], curr_depth, curr_elem.base_url))
                    # else:
                    #     # TODO: Should I just queue this up as a `url` op?
                    #     seen_urls.add(url)
                    #     elem = html.fromstring(fetch_html(url), base_url=url)
                    #     elem.set('backlink', curr_elem.base_url)
                    #     yield elem
                    # seen_urls.add(url)
                except requests.exceptions.RequestException as e:
                    print(f"{curr_depth*'  '}[BFS][{op}] Error fetching URL {url}: {e}")
                    continue

        elif op == 'url_inf':
            _path_exp = url_inf_filter_expr(value)
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
                    _segments = [('url_inf_2', (url, value))] + curr_segments[1:]
                    print(f"{curr_depth*'  '}[BFS][{op}] Queueing url_inf_2 for URL: {url} with segments: {_segments}")
                    # Not incrementing since we do not actually fetch the URL here
                    queue.append(Task(None, _segments, curr_depth, curr_elem.base_url))

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
                new_elem.set('depth', str(curr_depth))
                if html_handlers:
                    for handler in html_handlers:
                        new_elem = handler(new_elem)
                seen_urls.add(url)
                print(f"{curr_depth*'  '}[BFS][{op}] Fetched URL: {url}")
                
                # If no more segments, it means user wants to fetch the html elements
                # if not curr_segments[1:]:
                #     print(f"{curr_depth*'  '}[BFS][{op}] Yielding URL: {url}")
                #     # OR queue.append(Task(new_elem, curr_segments[1:], curr_depth+1, new_elem.base_url))
                #     yield new_elem
                
                if curr_depth <= max_depth:
                    # Queue the new element for further xpath evaluation
                    print(f"{curr_depth*'  '}[BFS][{op}] Queueing new element for further xpath evaluation curr_depth: {curr_depth} curr_segments[1:]: {curr_segments[1:]} url: {url}")
                    queue.append(Task(new_elem, curr_segments[1:], curr_depth+1, new_elem.base_url))
                    # For url_inf, also re-enqueue for further infinite expansion
                    _segments = [('url_inf', prev_op_value)] + curr_segments[1:]
                    print(f"{curr_depth*'  '}[BFS][{op}] Queueing url_inf for URL: {url} with segments: {_segments}, new_elem: {new_elem}")
                    queue.append(Task(new_elem, _segments, curr_depth+1, new_elem.base_url))
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
                    yield WxStr(elem, base_url=base_url, depth=curr_depth) if isinstance(elem, str) else elem
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
                            if curr_depth < max_depth:
                                queue.append(Task(None, [('url', url)] + curr_segments[2:], curr_depth+1, backlink=base_url))
                            else:
                                # TODO: Should I just queue this up as a `url` op?
                                seen_urls.add(url)
                                new_elem = html.fromstring(fetch_html(url), base_url=url)
                                new_elem.set('backlink', backlink)
                                new_elem.set('depth', str(curr_depth))
                                yield new_elem
                        except Exception as e:
                            print(f"{curr_depth*'  '}[BFS][{op}] Error fetching URL {url}: {e}")
                            continue
                else:
                    raise ValueError(f"Unexpected segment pattern after XPath: {next_op}")
        else:
            raise ValueError(f"Unknown operation: {op}")

    return


def wxpath_iter(path_expr, max_depth=1):
    return evaluate_wxpath_bfs_iter(None, parse_wxpath_expr(path_expr), max_depth=max_depth)


def wxpath(path_expr, max_depth=1):
    return list(wxpath_iter(path_expr, max_depth=max_depth))
