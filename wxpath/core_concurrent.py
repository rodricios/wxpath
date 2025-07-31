
"""
Concurrent breadth-first evaluator for wxpath expressions.

This module exposes `evaluate_wxpath_bfs_iter_concurrent`, a drop-in
replacement for `wxpath.core.evaluate_wxpath_bfs_iter` that batches all
URLs discovered at the same BFS depth and fetches them concurrently with
`wxpath.crawler.Crawler`.

Warning:
    `_fetch_many` invokes `Crawler.run`, which spins up its own
    event loop via `asyncio.run`.  Do **not** call
    `evaluate_wxpath_bfs_iter_concurrent` from within an already-running
    asyncio loop.
"""

import logging
from collections import deque
from typing import Mapping, Iterable
from lxml import html

from wxpath.models import Task
from wxpath.hooks import get_hooks
from wxpath.crawler import Crawler
from wxpath.core import (
    _ctx,
    _handle_object,
    _handle_xpath,
    _haldle_url_inf__no_return,
    _handle_url_from_attr__no_return,
    _count_ops_with_url,
)

log = logging.getLogger(__name__)

def _fetch_many(urls: Iterable[str]) -> Mapping[str, bytes]:
    """Fetch a batch of URLs concurrently.

    Args:
        urls (Iterable[str]): Unique absolute URLs to retrieve.

    Returns:
        Mapping[str, bytes]: A mapping of successfully fetched URLs to their
        response bodies. Only HTTP 200 responses are included.

    Notes:
        A fresh `wxpath.crawler.Crawler` instance is created so its
        semaphores are bound to the event loop spawned by
        `Crawler.run`.  Network failures or non-200 responses are
        silently skipped; missing keys in the returned mapping indicate
        fetch failures.
    """
    urls = list(dict.fromkeys(urls))     # stable-order dedup

    if not urls:
        return {}

    out: dict[str, bytes] = {}

    print(f"Fetching {len(urls)} URLs concurrently...\n")
    async def _cb(u: str, resp, body: bytes):
        if getattr(resp, "status", 0) == 200 and body:
            out[u] = body

    crawler = Crawler(concurrency=16, per_host=4, timeout=15)
    crawler.run(urls, _cb)       # blocking until all done
    return out


def evaluate_wxpath_bfs_iter_concurrent(
    elem,
    segments,
    *,
    max_depth: int = 1,
    seen_urls: set[str] | None = None,
):
    """Evaluate a wxpath expression using concurrent breadth-first traversal.

    The algorithm behaves like
    `wxpath.core.evaluate_wxpath_bfs_iter` but fetches all URLs
    discovered at the same BFS depth in parallel for improved throughput.

    Args:
        elem: Starting element. Pass `None` if the expression begins with an
            initial `url(...)` segment.
        segments (list[tuple[str, str]]): Parsed wxpath expression.
        max_depth (int, optional): Maximum crawl depth. Must be at least the
            number of `url*` segments minus one. Defaults to `1`.
        seen_urls (set[str], optional): Set used to de-duplicate URLs. A new
            set is created when `None`.

    Yields:
        lxml.html.HtmlElement | wxpath.models.WxStr | dict: The same objects
        produced by the sequential evaluator.

    Raises:
        AssertionError: If `max_depth` is too small or more than one
            `///url()` segment is present.

    Warning:
        Internally calls `asyncio.run` via `Crawler.run`;
        therefore this function must **not** be invoked from within an active
        asyncio event loop.
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
        # depth of the first task
        depth = queue[0].depth
        batch: list[Task] = []

        # pull the whole BFS layer into *batch*
        while queue and queue[0].depth == depth:
            batch.append(queue.popleft())

        # gather URLs that need fetching this layer
        urls: list[str] = []
        for _elem, segs, _d, _b in batch:
            if not segs:
                continue
            op, val = segs[0]
            if op == "url":
                urls.append(val)
            elif op == "url_inf_2":
                urls.append(val[0])

        bodies = _fetch_many(urls)    # {url: bytes}

        # process each task in the layer
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

            # URL-fetching ops handled directly (they depend on *bodies*)
            if op in {"url", "url_inf_2"}:
                url, prev_inf_val = (value, None) if op == "url" else value
                if url in seen_urls:
                    continue
                body = bodies.get(url)
                if body is None:
                    log.error(f"{'  '*curr_depth}[CBFS] fetch failed: {url}")
                    continue

                # run hook chain: post_fetch -> html.parse -> post_parse --
                for hook in get_hooks():
                    body = getattr(hook, "post_fetch",
                                   lambda _, c: c)(_ctx(url, backlink,
                                                        curr_depth, [],
                                                        seen_urls), body)
                    if not body:
                        break
                else:  # executed only if loop *not* broken
                    new_elem = html.fromstring(body, base_url=url)
                    new_elem.set("backlink", backlink)
                    new_elem.set("depth", str(curr_depth))
                    seen_urls.add(url)

                    for hook in get_hooks():
                        new_elem = getattr(hook, "post_parse",
                                           lambda _, e: e)(
                            _ctx(url, backlink, curr_depth,
                                 curr_segments, seen_urls), new_elem)
                        if new_elem is None:
                            break
                    if new_elem is None:
                        continue

                    # enqueue next layer
                    if curr_depth <= max_depth:
                        queue.append(
                            Task(new_elem, curr_segments[1:],
                                 curr_depth + 1, new_elem.base_url)
                        )
                        if op == "url_inf_2":
                            queue.append(
                                Task(new_elem,
                                     [("url_inf", prev_inf_val)]
                                     + curr_segments[1:],
                                     curr_depth + 1, new_elem.base_url)
                            )
                    else:
                        yield new_elem
                continue  # next task

            # Delegate everything else to the original helper functions
            if op == "url_from_attr":
                _handle_url_from_attr__no_return(
                    curr_elem, curr_segments, curr_depth, queue,
                    backlink, max_depth, seen_urls,
                )
            elif op == "url_inf":
                _haldle_url_inf__no_return(
                    curr_elem, curr_segments, curr_depth, queue,
                    backlink, max_depth, seen_urls,
                )
            elif op == "xpath":
                yield from _handle_xpath(
                    curr_elem, curr_segments, curr_depth, queue,
                    backlink, max_depth, seen_urls,
                )
            elif op == "object":
                yield from _handle_object(
                    curr_elem, curr_segments, curr_depth, queue,
                    backlink, max_depth, seen_urls,
                )
            else:
                raise ValueError(f"Unknown operation: {op}")