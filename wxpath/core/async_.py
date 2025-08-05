from __future__ import annotations

import asyncio
import logging
from collections import deque
from typing import AsyncGenerator
from lxml import html

from wxpath import patches
from wxpath.core.models import Task
from wxpath.hooks import get_hooks, pipe_post_extract_async
from wxpath.crawler import Crawler

from wxpath.core.parser import parse_wxpath_expr
from wxpath.core.helpers import _ctx, _count_ops_with_url
from wxpath.core.op_handlers import (
    _handle_object,
    _handle_xpath,
    _haldle_url_inf__no_return,
    _handle_url_from_attr__no_return,
)

log = logging.getLogger(__name__)


async def _fetch_many_async(urls: list[str]) -> dict[str, bytes]:
    out: dict[str, bytes] = {}
    async def _cb(u: str, resp, body: bytes):
        if getattr(resp, "status", 0) == 200 and body:
            out[u] = body
    crawler = Crawler()
    await crawler.run_async(urls, _cb)
    return out


@pipe_post_extract_async
async def evaluate_wxpath_bfs_iter_async(
    elem,
    segments,
    *,
    max_depth: int = 1,
    seen_urls: set[str] | None = None,
) -> AsyncGenerator:
    """
    Evaluate a wxpath expression using concurrent breadth-first traversal.

    Args:
        elem: Starting element. Pass `None` if the expression begins with an
            initial `url(...)` segment.
        segments (list[tuple[str, str]]): Parsed wxpath expression.
        max_depth (int, optional): Maximum crawl depth. Must be at least the
            number of `url*` segments minus one. Defaults to `1`.
        seen_urls (set[str], optional): Set used to de-duplicate URLs. A new
            set is created when `None`.
    """
    assert max_depth >= _count_ops_with_url(segments) - 1, (
        "max_depth+1 must be >= number of url* segments "
        f"(max_depth={max_depth})"
    )
    assert len([op for op, _ in segments if op == "url_inf"]) <= 1, \
        "Only one ///url() segment allowed"

    if seen_urls is None:
        seen_urls = set()

    queue: deque[Task] = deque([Task(elem, segments, 0, None)])

    while queue:
        depth = queue[0].depth
        batch: list[Task] = []

        while queue and queue[0].depth == depth:
            batch.append(queue.popleft())

        urls: list[str] = []
        for _elem, segs, _d, _b in batch:
            if not segs:
                continue
            op, val = segs[0]
            if op == "url":
                urls.append(val)
            elif op == "url_inf_and_xpath":
                urls.append(val[0])

        bodies = await _fetch_many_async(urls)

        for curr_elem, curr_segments, curr_depth, backlink in batch:
            if not curr_segments:
                if curr_elem is not None:
                    yield curr_elem
                continue

            op, value = curr_segments[0]
            log.debug(
                f"{'  '*curr_depth}[CBFS] op={op} depth={curr_depth} "
                f"url={value if op=='url' else ''}"
            )

            if op in {"url", "url_inf_and_xpath"}:
                url, prev_inf_val = (value, None) if op == "url" else value
                if url in seen_urls:
                    continue
                body = bodies.get(url)
                if body is None:
                    log.error(f"{'  '*curr_depth}[CBFS] fetch failed: {url}")
                    continue

                for hook in get_hooks():
                    body = await hook.post_fetch(_ctx(url, backlink, curr_depth, [], seen_urls), body) \
                           if hasattr(hook, 'post_fetch') else body
                    if not body:
                        break
                else:
                    new_elem = html.fromstring(body, base_url=url)
                    new_elem.set("backlink", backlink)
                    new_elem.set("depth", str(curr_depth))
                    seen_urls.add(url)

                    for hook in get_hooks():
                        new_elem = await hook.post_parse(
                            _ctx(url, backlink, curr_depth, curr_segments, seen_urls), new_elem
                        ) if hasattr(hook, 'post_parse') else new_elem
                        if new_elem is None:
                            break
                    if new_elem is None:
                        continue

                    if curr_depth <= max_depth:
                        queue.append(Task(new_elem, curr_segments[1:], curr_depth + 1, new_elem.base_url))
                        if op == "url_inf_and_xpath":
                            queue.append(Task(new_elem, [("url_inf", prev_inf_val)] + curr_segments[1:], curr_depth + 1, new_elem.base_url))
                    else:
                        yield new_elem
                continue

            if op == "url_from_attr":
                _handle_url_from_attr__no_return(curr_elem, curr_segments, curr_depth, queue, backlink, max_depth, seen_urls)
            elif op == "url_inf":
                _haldle_url_inf__no_return(curr_elem, curr_segments, curr_depth, queue, backlink, max_depth, seen_urls)
            elif op == "xpath":
                for x in _handle_xpath(curr_elem, curr_segments, curr_depth, queue, backlink, max_depth, seen_urls):
                    yield x
            elif op == "object":
                for o in _handle_object(curr_elem, curr_segments, curr_depth, queue, backlink, max_depth, seen_urls):
                    yield o
            else:
                raise ValueError(f"Unknown operation: {op}")
            

def wxpath_async(path_expr, max_depth=1) -> AsyncGenerator:
    return evaluate_wxpath_bfs_iter_async(None, parse_wxpath_expr(path_expr), max_depth=max_depth)


##### ASYNC IN SYNC #####
def wxpath_async_blocking_iter(path_expr, max_depth=1):
    """
    Evaluate a wxpath expression using concurrent breadth-first traversal.
    
    Args:
        path_expr (str): A wxpath expression.
        max_depth (int, optional): Maximum crawl depth. Must be at least the
            number of `url*` segments minus one. Defaults to `1`.

    Yields:
        lxml.html.HtmlElement | wxpath.models.WxStr | dict | Any: The same objects
        produced by the sequential evaluator.

    Warning:
        Spins up its own event loop therefore this function must **not** be
        invoked from within an active asyncio event loop.
    """
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    agen = wxpath_async(path_expr, max_depth=max_depth)

    try:
        while True:
            try:
                yield loop.run_until_complete(agen.__anext__())
            except StopAsyncIteration:
                break
    finally:
        loop.run_until_complete(loop.shutdown_asyncgens())
        loop.close()