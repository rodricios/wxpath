import asyncio
import aiohttp
from collections import deque
from typing import AsyncGenerator, Any, Iterable
from lxml.html import HtmlElement

from wxpath import patches
from wxpath.http.crawler import Crawler
from wxpath.core.models import CrawlTask, Intent, CrawlIntent, ProcessIntent, DataIntent, ExtractIntent, InfiniteCrawlIntent
from wxpath.core.parser import parse_wxpath_expr
from wxpath.core.ops import get_operator, OPS
from wxpath.core.helpers import parse_html, _ctx, _count_ops_with_url
from wxpath.hooks import get_hooks
from wxpath.util.logging import get_logger

log = get_logger(__name__)


class WXPathEngine:
    """
    Main class for executing wxpath expressions.

    The core pattern and directive for this engine is to build a queue of CrawlTasks, 
    which is crawled and processed in batches (of size `fetch_batch_size`). The traversal
    of the queue (and therefore the web tree) is done concurrently and in near-pefect 
    depth-based BFS order (URLs of depth N are fetched before URLs of depth N+1).

    Args:
        concurrency: number of concurrent fetches at the Crawler (request engine) level
        fetch_batch_size: number of URLs to send to the Crawler at once - controls the 
            streaming batch size
        dedupe_urls_per_page: whether to dedupe URLs on a per-page basis
    """
    def __init__(self, concurrency: int = 16, fetch_batch_size: int = 32, dedupe_urls_per_page: bool = True):
        self.concurrency = concurrency
        self.fetch_batch_size = fetch_batch_size
        self.seen_urls: set[str] = set()
        self.crawler = Crawler(concurrency=self.concurrency)
        self.dedupe_urls_per_page = dedupe_urls_per_page


    async def _fetch_many(self, crawler: Crawler, urls: Iterable[str]):
        out: dict[str, bytes] = {}

        async def _cb(u, resp, body):
            if getattr(resp, "status", 0) == 200 and body:
                out[u] = body

        if not urls:
            return out

        await crawler.run_async(urls, _cb)
        return out


    def post_fetch_hooks(self, body, task):
        for hook in get_hooks():
            body = getattr(hook, "post_fetch", lambda _, b: b)(
                _ctx(task.url, task.backlink, task.depth, [], self.seen_urls), body
            )
            if not body:
                log.debug(f"hook {hook.__name__} dropped {task.url}")
                break
        return body
    
    def post_parse_hooks(self, elem, task):
        for hook in get_hooks():
            elem = getattr(hook, "post_parse", lambda _, e: e)(
                _ctx(task.url, task.backlink, task.depth, task.segments, self.seen_urls),
                elem,
            )
            if elem is None:
                log.debug(f"hook {hook.__name__} dropped {task.url}")
                break
        return elem
    

    async def run(self, expression: str, max_depth: int) -> AsyncGenerator[Any, None]:
        segments = parse_wxpath_expr(expression)

        assert max_depth >= _count_ops_with_url(segments) - 1
        assert sum(1 for op, _ in segments if op == OPS.URL_INF) <= 1

        queue: deque[CrawlTask] = deque()

        if segments[0][0] == OPS.URL:
            url = segments[0][1]
            queue.append(
                CrawlTask(
                    elem=None,
                    url=url,
                    segments=segments[1:],
                    depth=0,
                    backlink=None,
                )
            )
            # self.seen_urls.add(url)
        else:
            raise ValueError("Hybrid engine currently requires expression to start with url()")
        
        async with self.crawler as crawler:
            while queue:
                # Initial task
                current_batch: list[CrawlTask] = []

                while queue and len(current_batch) < self.fetch_batch_size:
                    current_batch.append(queue.popleft())

                urls = {task.url for task in current_batch if task.url not in self.seen_urls}
                responses = await self._fetch_many(crawler, urls)

                for task in current_batch:
                    if task.url in responses:
                        body = responses[task.url]

                        body = self.post_fetch_hooks(body, task)
                        
                        if not body:
                            continue

                        elem = parse_html(body, base_url=task.url, backlink=task.backlink, depth=task.depth)

                        elem = self.post_parse_hooks(elem, task)

                        if elem is None:
                            continue

                        self.seen_urls.add(task.url)

                        if task.segments:
                            async for output in self._process_pipeline(
                                task=task,
                                elem=elem,
                                depth=task.depth,
                                max_depth=max_depth,
                                queue=queue,
                            ):
                                yield output
                        else:
                            yield elem

                    else:
                        log.warning(f"Failed to fetch {task.url}")

    async def _process_pipeline(
        self,
        task: CrawlTask,
        elem, 
        depth: int,
        max_depth: int,
        queue: deque[CrawlTask],
    ):
        mini_queue: deque[(HtmlElement, list[tuple[str, str]])] = deque([(elem, task.segments)])

        while mini_queue:
            elem, segments = mini_queue.popleft()
            
            op, _ = segments[0]
            operator = get_operator(op)

            intents = operator(elem, segments, depth, dedupe_urls_per_page=self.dedupe_urls_per_page)

            if not intents:
                return

            for intent in intents:
                if isinstance(intent, DataIntent):
                    yield intent.value

                elif isinstance(intent, CrawlIntent):
                    next_depth = task.depth + 1
                    if intent.url not in self.seen_urls and next_depth <= max_depth:
                        # self.seen_urls.add(intent.url)
                        queue.append(
                            CrawlTask(
                                elem=None,
                                url=intent.url,
                                segments=intent.next_segments,
                                depth=next_depth,
                                backlink=task.url,
                            )
                        )

                elif isinstance(intent, (ExtractIntent, ProcessIntent, InfiniteCrawlIntent)):
                    # immediately traverse the extraction
                    elem = intent.elem
                    next_segments = intent.next_segments
                    mini_queue.append((elem, next_segments))

def wxpath_async(path_expr: str, max_depth: int, engine: WXPathEngine = None) -> AsyncGenerator[Any, None]:
    if engine is None:
        engine = WXPathEngine(concurrency=32)
    return engine.run(path_expr, max_depth)


##### ASYNC IN SYNC #####
def wxpath_async_blocking_iter(path_expr, max_depth=1, engine: WXPathEngine = None):
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
    agen = wxpath_async(path_expr, max_depth=max_depth, engine=engine)

    try:
        while True:
            try:
                yield loop.run_until_complete(agen.__anext__())
            except StopAsyncIteration:
                break
    finally:
        loop.run_until_complete(loop.shutdown_asyncgens())
        loop.close()


def wxpath_async_blocking(path_expr, max_depth=1, engine: WXPathEngine = None):
    return list(wxpath_async_blocking_iter(path_expr, max_depth=max_depth, engine=engine))