"""
Async version of wxpath core functionality with parallelized HTTP requests.

This module provides async implementations of core wxpath functions,
enabling concurrent HTTP requests while preserving BFS queue semantics.
"""

import asyncio
import aiohttp
import logging
import re
from collections import deque, defaultdict
from typing import Optional, List, Dict, Iterable, Any
from urllib.parse import urljoin, urlsplit

from lxml import html
from .models import WxElement, WxStr, Task
from .hooks import get_hooks, FetchContext
from .crawler import Crawler
from .core import (
    parse_html, _make_links_absolute, wrap_strings, _extract_arg_from_url_xpath_op,
    _split_top_level, _parse_object_mapping, parse_wxpath_expr, 
    _url_inf_filter_expr, _count_ops_with_url, _get_absolute_links_from_elem_and_xpath,
    _ctx
)

log = logging.getLogger(__name__)


async def async_fetch_html(url: str) -> bytes:
    """
    Async version of fetch_html for single URL.
    """
    async with aiohttp.ClientSession() as session:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as response:
            response.raise_for_status()
            return await response.read()


async def async_fetch_html_batch(urls: List[str], crawler: Optional[Crawler] = None) -> Dict[str, Optional[bytes]]:
    """
    Fetch multiple URLs concurrently with robust error handling.
    
    Args:
        urls: List of URLs to fetch
        crawler: Optional Crawler instance for rate limiting and configuration
        
    Returns:
        Dict mapping URL -> content (or None if failed)
        
    Individual URL failures return None instead of raising exceptions,
    ensuring that a single failure doesn't halt the entire batch.
    """
    if not urls:
        return {}
        
    if crawler is None:
        crawler = Crawler(concurrency=16, per_host=4, timeout=15)
    
    results = {}
    
    async def fetch_single(url: str, session: aiohttp.ClientSession):
        """Fetch a single URL with error handling."""
        host = urlsplit(url).hostname
        
        try:
            # Use crawler's semaphore system for rate limiting
            async with crawler._sem_global, crawler._sem_host[host]:
                if crawler._delay:
                    await asyncio.sleep(crawler._delay)
                
                async with session.get(
                    url,
                    proxy=crawler._proxy_for(url),
                    timeout=crawler._timeout
                ) as response:
                    content = await response.read()
                    results[url] = content
                    log.debug(f"Successfully fetched {url} ({len(content)} bytes)")
                    
        except asyncio.TimeoutError:
            log.error(f"Timeout fetching {url}")
            results[url] = None
        except aiohttp.ClientError as e:
            log.error(f"Client error fetching {url}: {e}")
            results[url] = None
        except Exception as e:
            log.error(f"Unexpected error fetching {url}: {e}")
            results[url] = None
    
    # Create session with crawler's configuration
    async with aiohttp.ClientSession(
        headers=crawler._headers,
        timeout=crawler._timeout
    ) as session:
        # Create tasks for all URLs
        tasks = [fetch_single(url, session) for url in urls]
        
        # Execute all tasks concurrently, collecting exceptions
        await asyncio.gather(*tasks, return_exceptions=True)
    
    log.info(f"Batch fetch completed: {len([v for v in results.values() if v is not None])}/{len(urls)} successful")
    return results


async def async_load_page_as_element(
    url: str,
    backlink: Optional[str],
    depth: int,
    seen_urls: set[str],
    curr_depth: int = -1,
    op: str = "",
    crawler: Optional[Crawler] = None
) -> Optional[html.HtmlElement]:
    """
    Async version of _load_page_as_element.
    
    Fetches the URL asynchronously, parses it into an lxml Element,
    sets backlink/depth, and runs any HTML post-processing hooks.
    """
    try:
        content = await async_fetch_html(url) if crawler is None else \
                 (await async_fetch_html_batch([url], crawler))[url]
        
        if content is None:
            return None
        
        # Apply post_fetch hooks
        for hook in get_hooks():
            _content = getattr(hook, 'post_fetch', lambda _, content: content)(
                _ctx(url, backlink, depth, [], seen_urls), content
            )
            if not _content:
                return None
            content = _content
        
        elem = html.fromstring(content, base_url=url)
        elem.set("backlink", backlink)
        elem.set("depth", str(depth))
        seen_urls.add(url)
        
        log.debug(f"{curr_depth*'  '}[ASYNC-BFS][{op}] Fetched URL: {url}")
        return elem
        
    except Exception as e:
        log.error(f"Error loading page {url}: {e}")
        return None


async def async_handle_url(curr_elem, curr_segments, curr_depth, queue, backlink, max_depth, seen_urls, crawler=None):
    """
    Async version of _handle_url.
    Handles the `^url()` segment of a wxpath expression.
    """
    op, url = curr_segments[0]
    
    if curr_elem is not None:
        raise ValueError("Cannot use 'url()' at the start of path_expr with an element provided.")
    if url.startswith('@'):
        raise ValueError("Cannot use '@' in url() segment at the start of path_expr.")
    if url in seen_urls:
        log.debug(f"{curr_depth*'  '}[ASYNC-BFS][{op}] Skipping already seen URL: {url}")
        return

    try:
        new_elem = await async_load_page_as_element(url, backlink, curr_depth, seen_urls, curr_depth, op, crawler)
        
        if new_elem is None:
            return
        
        # Apply post_parse hooks
        for hook in get_hooks():
            _elem = getattr(hook, 'post_parse', lambda _, elem: elem)(
                _ctx(url, backlink, curr_depth, curr_segments, seen_urls), new_elem
            )
            if _elem is None:
                return
            new_elem = _elem

        log.debug(f"{curr_depth*'  '}[ASYNC-BFS][{op}] Fetched URL: {url} curr_depth: {curr_depth} curr_segments[1:]: {curr_segments[1:]}")
        
        if curr_depth <= max_depth:
            log.debug(f"{curr_depth*'  '}[ASYNC-BFS][{op}] Queueing new element for further xpath evaluation curr_depth: {curr_depth} curr_segments[1:]: {curr_segments[1:]} url: {url}")
            queue.append(Task(new_elem, curr_segments[1:], curr_depth+1, url))
        else:
            yield new_elem
            
    except Exception as e:
        log.error(f"{curr_depth*'  '}[ASYNC-BFS][{op}] Error fetching URL {url}: {e}")


def async_handle_url_from_attr__no_return(curr_elem, curr_segments, curr_depth, queue, backlink, max_depth, seen_urls):
    """
    Async version of _handle_url_from_attr__no_return.
    Handles the `[/|//]url(@<attr>)` segment of a wxpath expression.
    
    Note: This function collects URLs but doesn't fetch them immediately.
    The actual fetching will be done in batch by the main BFS loop.
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
            log.debug(f"{curr_depth*'  '}[ASYNC-BFS][{op}] Skipping already seen URL: {url}")
            continue
        try:
            if curr_depth <= max_depth:
                # Queue URL for batch processing
                queue.append(Task(None, [('url', url)] + curr_segments[1:], curr_depth, curr_elem.base_url))
            else:
                log.debug(f"{curr_depth*'  '}[ASYNC-BFS][{op}] Reached max depth for URL: {url}, not queuing further.")
        except Exception as e:
            log.error(f"{curr_depth*'  '}[ASYNC-BFS][{op}] Error processing URL {url}: {e}")
            continue


def async_handle_url_inf__no_return(curr_elem, curr_segments, curr_depth, queue, backlink, max_depth, seen_urls):
    """
    Async version of _haldle_url_inf__no_return.
    Handles the ///url() segment of a wxpath expression.
    """
    op, value = curr_segments[0]
    _path_exp = _url_inf_filter_expr(value)
    urls = _get_absolute_links_from_elem_and_xpath(curr_elem, _path_exp)
    
    log.debug(f"{curr_depth*'  '}[ASYNC-BFS][{op}] Found {len(urls)} URLs from {getattr(curr_elem, 'base_url', None) if curr_elem is not None else None} at depth {curr_depth}")
    
    for url in urls:
        if url in seen_urls:
            log.debug(f"{curr_depth*'  '}[ASYNC-BFS][{op}] Skipping already seen URL: {url}")
            continue
        try:
            if curr_depth > max_depth:
                log.debug(f"{curr_depth*'  '}[ASYNC-BFS][{op}] Reached max depth for URL: {url}, not queuing further.")
                continue
            _segments = [('url_inf_2', (url, value))] + curr_segments[1:]
            log.debug(f"{curr_depth*'  '}[ASYNC-BFS][{op}] Queueing url_inf_2 for URL: {url} with segments: {_segments}")
            queue.append(Task(None, _segments, curr_depth, curr_elem.base_url))
        except Exception as e:
            log.error(f"{curr_depth*'  '}[ASYNC-BFS][{op}] Error processing URL {url}: {e}")
            continue


async def async_handle_url_inf_2__no_return(curr_elem, curr_segments, curr_depth, queue, backlink, max_depth, seen_urls, crawler=None):
    """
    Async version of _handle_url_inf_2__no_return.
    This is an operation that is generated internally by the parser.
    """
    op, value = curr_segments[0]
    url, prev_op_value = value
    
    if curr_elem is not None:
        raise ValueError("Cannot use 'url()' at the start of path_expr with an element provided.")
    if url in seen_urls:
        log.debug(f"{curr_depth*'  '}[ASYNC-BFS][{op}] Skipping already seen URL: {url}")
        return

    try:
        new_elem = await async_load_page_as_element(url, backlink, curr_depth, seen_urls, curr_depth, op, crawler)
        
        if new_elem is None:
            return
        
        # Apply post_parse hooks
        for hook in get_hooks():
            _elem = getattr(hook, 'post_parse', lambda _, elem: elem)(
                _ctx(url, backlink, curr_depth, curr_segments, seen_urls), new_elem
            )
            if _elem is None:
                return
            new_elem = _elem

        log.debug(f"{curr_depth*'  '}[ASYNC-BFS][{op}] Fetched URL: {url}")
        
        if curr_depth <= max_depth:
            # Queue the new element for further xpath evaluation
            log.debug(f"{curr_depth*'  '}[ASYNC-BFS][{op}] Queueing new element for further xpath evaluation curr_depth: {curr_depth} curr_segments[1:]: {curr_segments[1:]} url: {url}")
            queue.append(Task(new_elem, curr_segments[1:], curr_depth+1, new_elem.base_url))
            
            # For url_inf, also re-enqueue for further infinite expansion
            _segments = [('url_inf', prev_op_value)] + curr_segments[1:]
            log.debug(f"{curr_depth*'  '}[ASYNC-BFS][{op}] Queueing url_inf for URL: {url} with segments: {_segments}, new_elem: {new_elem}")
            queue.append(Task(new_elem, _segments, curr_depth+1, new_elem.base_url))
        else:
            log.debug(f"{curr_depth*'  '}[ASYNC-BFS][{op}] Reached max depth for URL: {url}, not queuing further.")
            
    except Exception as e:
        log.error(f"{curr_depth*'  '}[ASYNC-BFS][{op}] Error fetching URL {url}: {e}")


def async_handle_xpath(curr_elem, curr_segments, curr_depth, queue, backlink, max_depth, seen_urls):
    """
    Async version of _handle_xpath.
    Handles the [/|//]<xpath> segment of a wxpath expression.
    This is a plain XPath expression that doesn't require async processing.
    """
    _, value = curr_segments[0]
    if curr_elem is None:
        raise ValueError("Element must be provided when path_expr does not start with 'url()'.")
    
    base_url = getattr(curr_elem, 'base_url', None)
    elems = curr_elem.xpath(value)
    
    for elem in elems:
        if len(curr_segments) == 1:
            yield WxStr(elem, base_url=base_url, depth=curr_depth) if isinstance(elem, str) else elem
        else:
            queue.append(Task(elem, curr_segments[1:], curr_depth, base_url))


async def async_handle_object(curr_elem, curr_segments, curr_depth, queue, backlink, max_depth, seen_urls, crawler=None):
    """
    Async version of _handle_object.
    Builds a JSON-like dict from an object segment.
    """
    _, value = curr_segments[0]

    if curr_elem is None:
        raise ValueError("Object segment requires an element context before it.")

    obj_map = _parse_object_mapping(value)
    result = {}

    for key, expr in obj_map.items():
        # Detect optional [n] scalar-selection suffix
        idx = None
        m = re.match(r'^(.*)\\[(\\d+)\\]\\s*$', expr)
        if m:
            expr_inner = m.group(1).strip()
            idx = int(m.group(2))
        else:
            expr_inner = expr

        # Parse the sub-expression and decide whether it needs a root element
        sub_segments = parse_wxpath_expr(expr_inner)
        root_elem = None if sub_segments[0][0] != 'xpath' else curr_elem

        sub_results = []
        async for item in async_evaluate_wxpath_bfs_iter(
            root_elem,
            sub_segments,
            max_depth=max_depth,
            crawler=crawler
        ):
            sub_results.append(item)

        # Apply index hint if present
        if idx is not None:
            sub_results = sub_results[idx:idx+1] if len(sub_results) > idx else []

        if not sub_results:
            result[key] = None
        elif len(sub_results) == 1:
            result[key] = sub_results[0]
        else:
            result[key] = sub_results

    # Yield the constructed object; no further traversal after an object segment
    yield result


async def async_evaluate_wxpath_bfs_iter(elem, segments, max_depth=1, seen_urls=None, curr_depth=0, crawler=None):
    """
    Async BFS version of evaluate_wxpath with depth-based batch processing.
    
    This function processes all nodes at the current depth before moving deeper,
    and batches URL fetches for parallel processing while maintaining BFS semantics.
    
    Args:
        elem: Initial element or None for URL-based expressions
        segments: Parsed wxpath expression segments
        max_depth: Maximum traversal depth
        seen_urls: Set of already visited URLs
        curr_depth: Current traversal depth
        crawler: Optional Crawler instance for HTTP configuration
        
    Yields:
        Results from wxpath evaluation
    """
    assert max_depth >= (_count_ops_with_url(segments) - 1), \
        f"max_depth+1 must be equal to or greater than the number of url* segments. " + \
        f"max_depth: {max_depth}, number of url* segments: {_count_ops_with_url(segments)}"
    assert len([op for op, _ in segments if op == 'url_inf']) <= 1, "Only one ///url() is allowed"
    
    if seen_urls is None:
        seen_urls = set()
    
    if crawler is None:
        crawler = Crawler(concurrency=16, per_host=4, timeout=15)
    
    queue = deque()
    queue.append(Task(elem, segments, 0))

    iterations = 0
    
    while queue:
        iterations += 1
        if iterations % 100 == 0:
            log.debug(f"[ASYNC-BFS] Iteration {iterations}: Queue size: {len(queue)}, Current depth: {curr_depth}, Seen URLs: {len(seen_urls)}")
        
        # Collect tasks that need URL fetching at the current depth
        url_fetch_tasks = []
        immediate_tasks = []
        
        # Process current queue and separate URL vs non-URL tasks
        temp_queue = deque()
        while queue:
            task = queue.popleft()
            curr_elem, curr_segments, task_depth, backlink = task
            
            if not curr_segments:
                if curr_elem is not None:
                    yield curr_elem
                continue

            op, value = curr_segments[0]
            
            # Separate URL operations that need batch processing
            if op in ['url', 'url_inf_2'] and task_depth == curr_depth:
                url_fetch_tasks.append(task)
            else:
                immediate_tasks.append(task)
        
        # Process immediate tasks (non-URL operations)
        for task in immediate_tasks:
            curr_elem, curr_segments, task_depth, backlink = task
            op, value = curr_segments[0]
            
            log.debug(f"{task_depth*'  '}[ASYNC-BFS] op: {op}, value: {value} depth={task_depth} elem.base_url={getattr(curr_elem, 'base_url', None) if curr_elem is not None else None}")
            
            if op == 'url_from_attr':
                async_handle_url_from_attr__no_return(curr_elem, curr_segments, task_depth, queue, backlink, max_depth, seen_urls)
            elif op == 'url_inf':
                async_handle_url_inf__no_return(curr_elem, curr_segments, task_depth, queue, backlink, max_depth, seen_urls)
            elif op == 'xpath':
                for result in async_handle_xpath(curr_elem, curr_segments, task_depth, queue, backlink, max_depth, seen_urls):
                    yield result
            elif op == 'object':
                async for result in async_handle_object(curr_elem, curr_segments, task_depth, queue, backlink, max_depth, seen_urls, crawler):
                    yield result
            else:
                # Queue for next iteration if not a URL operation
                queue.append(task)
        
        # Batch process URL fetch tasks
        if url_fetch_tasks:
            # Extract URLs for batch fetching
            urls_to_fetch = []
            url_task_map = {}
            
            for task in url_fetch_tasks:
                curr_elem, curr_segments, task_depth, backlink = task
                op, value = curr_segments[0]
                
                if op == 'url':
                    url = value
                elif op == 'url_inf_2':
                    url, prev_op_value = value
                else:
                    continue
                    
                if url not in seen_urls:
                    urls_to_fetch.append(url)
                    url_task_map[url] = task
            
            # Batch fetch all URLs
            if urls_to_fetch:
                log.info(f"[ASYNC-BFS] Batch fetching {len(urls_to_fetch)} URLs at depth {curr_depth}")
                url_contents = await async_fetch_html_batch(urls_to_fetch, crawler)
                
                # Process fetched results
                for url, content in url_contents.items():
                    if content is None:
                        log.debug(f"[ASYNC-BFS] Skipping failed URL: {url}")
                        continue
                        
                    task = url_task_map[url]
                    curr_elem, curr_segments, task_depth, backlink = task
                    op, value = curr_segments[0]
                    
                    try:
                        # Apply post_fetch hooks
                        for hook in get_hooks():
                            _content = getattr(hook, 'post_fetch', lambda _, content: content)(
                                _ctx(url, backlink, task_depth, [], seen_urls), content
                            )
                            if not _content:
                                content = None
                                break
                            content = _content
                        
                        if content is None:
                            continue
                        
                        # Parse HTML to element
                        elem = html.fromstring(content, base_url=url)
                        elem.set("backlink", backlink)
                        elem.set("depth", str(task_depth))
                        seen_urls.add(url)
                        
                        # Apply post_parse hooks
                        for hook in get_hooks():
                            _elem = getattr(hook, 'post_parse', lambda _, elem: elem)(
                                _ctx(url, backlink, task_depth, curr_segments, seen_urls), elem
                            )
                            if _elem is None:
                                elem = None
                                break
                            elem = _elem
                        
                        if elem is None:
                            continue
                        
                        log.debug(f"{task_depth*'  '}[ASYNC-BFS][{op}] Successfully processed URL: {url}")
                        
                        # Handle different URL operations
                        if op == 'url':
                            if task_depth <= max_depth:
                                queue.append(Task(elem, curr_segments[1:], task_depth+1, url))
                            else:
                                yield elem
                                
                        elif op == 'url_inf_2':
                            url_val, prev_op_value = value
                            if task_depth <= max_depth:
                                # Queue for further xpath evaluation
                                queue.append(Task(elem, curr_segments[1:], task_depth+1, elem.base_url))
                                # Re-enqueue for infinite expansion
                                _segments = [('url_inf', prev_op_value)] + curr_segments[1:]
                                queue.append(Task(elem, _segments, task_depth+1, elem.base_url))
                            
                    except Exception as e:
                        log.error(f"[ASYNC-BFS] Error processing URL {url}: {e}")
                        continue

    return


# Sync wrapper for backward compatibility
def evaluate_wxpath_bfs_iter_async_wrapper(elem, segments, max_depth=1, seen_urls=None, curr_depth=0, crawler=None):
    """
    Synchronous wrapper for async_evaluate_wxpath_bfs_iter.
    Allows using the async implementation from synchronous code.
    """
    async def _run():
        results = []
        async for result in async_evaluate_wxpath_bfs_iter(elem, segments, max_depth, seen_urls, curr_depth, crawler):
            results.append(result)
        return results
    
    return asyncio.run(_run())


# Main async entry point
async def async_wxpath(elem_or_url, expr, max_depth=1, crawler=None):
    """
    Async version of the main wxpath function.
    
    Args:
        elem_or_url: Starting element or URL
        expr: wxpath expression string
        max_depth: Maximum traversal depth
        crawler: Optional Crawler instance
        
    Returns:
        Async generator yielding wxpath results
    """
    segments = parse_wxpath_expr(expr)
    
    # Determine starting element
    if isinstance(elem_or_url, str):
        # It's a URL
        elem = None
        segments = [('url', elem_or_url)] + segments
    else:
        # It's an element
        elem = elem_or_url
    
    async for result in async_evaluate_wxpath_bfs_iter(elem, segments, max_depth=max_depth, crawler=crawler):
        yield result