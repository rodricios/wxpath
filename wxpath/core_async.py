import logging
from collections import deque
from typing import AsyncGenerator, Iterable
from lxml import html

from wxpath.models import Task
from wxpath.hooks import get_hooks, FetchContext
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


async def evaluate_wxpath_bfs_iter_concurrent_async(
    elem,
    segments,
    *,
    max_depth: int = 1,
    seen_urls: set[str] | None = None,
) -> AsyncGenerator:
    assert max_depth >= _count_ops_with_url(segments) - 1, (
        "max_depth+1 must be >= number of url* segments "
        f"(max_depth={max_depth})"
    )
    assert len([op for op, _ in segments if op == "url_inf"]) <= 1, \
        "Only one ///url() segment allowed"

    if seen_urls is None:
        seen_urls = set()

    queue: deque[Task] = deque([Task(elem, segments, 0, None)])
    crawler = Crawler()

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
            elif op == "url_inf_2":
                urls.append(val[0])

        out: dict[str, bytes] = {}

        async def _cb(u: str, resp, body: bytes):
            if getattr(resp, "status", 0) == 200 and body:
                out[u] = body

        await crawler.run_async(urls, _cb)

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

            if op in {"url", "url_inf_2"}:
                url, prev_inf_val = (value, None) if op == "url" else value
                if url in seen_urls:
                    continue
                body = out.get(url)
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
                        if op == "url_inf_2":
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