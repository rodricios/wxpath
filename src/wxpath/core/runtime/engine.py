import asyncio
from collections import deque
from typing import AsyncGenerator, Any, Iterable
from lxml.html import HtmlElement

from wxpath import patches
from wxpath.http.client.crawler import Crawler
from wxpath.http.client.request import Request
from wxpath.core.models import CrawlTask, CrawlIntent, ProcessIntent, DataIntent, ExtractIntent, InfiniteCrawlIntent
from wxpath.core.parser import parse_wxpath_expr
from wxpath.core.ops import get_operator, OPS
from wxpath.core.runtime.helpers import parse_html
from wxpath.hooks.registry import get_hooks, FetchContext
from wxpath.util.logging import get_logger

log = get_logger(__name__)


class Engine:
    def post_fetch_hooks(self, body, task):
        for hook in get_hooks():
            body = getattr(hook, "post_fetch", lambda _, b: b)(
                FetchContext(task.url, task.backlink, task.depth, task.segments), 
                body
            )
            if not body:
                log.debug(f"hook {hook.__name__} dropped {task.url}")
                break
        return body
    
    def post_parse_hooks(self, elem, task):
        for hook in get_hooks():
            elem = getattr(hook, "post_parse", lambda _, e: e)(
                FetchContext(url=task.url, backlink=task.backlink, depth=task.depth, segments=task.segments),
                elem,
            )
            if elem is None:
                log.debug(f"hook {hook.__name__} dropped {task.url}")
                break
        return elem
    

    def post_extract_hooks(self, value):
        for hook in get_hooks():
            value = getattr(hook, "post_extract", lambda _, v: v)(value)
            if value is None:
                log.debug(f"hook {hook.__name__} dropped value")
                break
        return value


class WXPathEngine(Engine):
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
    def __init__(
            self, 
            concurrency: int = 16, 
            per_host: int = 8,
            fetch_batch_size: int = 32, 
            # dedupe_urls_per_page: bool = True
        ):
        self.concurrency = concurrency
        self.per_host = per_host
        self.fetch_batch_size = fetch_batch_size
        self.seen_urls: set[str] = set()      # semantic traversal
        # self.fetched_urls: set[str] = set()   # actual HTTP fetches
        self.crawler = Crawler(concurrency=self.concurrency, per_host=self.per_host)
        # self.dedupe_urls_per_page = dedupe_urls_per_page

    async def _fetch_many(self, crawler: Crawler, urls: Iterable[str]) -> dict[str, str]:
        responses: dict[str, str] = {}

        requests: list[Request] = [Request(url=u) for u in urls]

        async for resp in crawler.fetch(requests):
            breakpoint()
            if resp.status == 200 and resp.body:
                responses[resp.request.url] = resp.body

        return responses

    async def run(self, expression: str, max_depth: int):
        segments = parse_wxpath_expr(expression)

        if segments[0][0] != OPS.URL:
            raise ValueError("Expression must start with url()")

        root_url = segments[0][1]
        queue: asyncio.Queue[CrawlTask] = asyncio.Queue()
        inflight: dict[str, CrawlTask] = {}

        # Seed the queue with the root task
        await queue.put(
            CrawlTask(
                elem=None,
                url=root_url,
                segments=segments[1:],
                depth=0,
                backlink=None,
            )
        )

        async def producer(crawler: Crawler):
            while True:
                try:
                    task = await asyncio.wait_for(queue.get(), timeout=0.1)
                except asyncio.TimeoutError:
                    if not inflight and queue.empty():
                        break
                    continue

                if task.url in inflight or task.url in self.seen_urls:
                    queue.task_done()
                    continue

                crawler.submit(Request(task.url))
                inflight[task.url] = task
                queue.task_done()

        async def consumer(crawler: Crawler):
            while True:
                if not inflight and queue.empty():
                    break

                try:
                    resp = await asyncio.wait_for(crawler.__aiter__().__anext__(), timeout=0.5)
                except asyncio.TimeoutError:
                    continue

                task = inflight.pop(resp.request.url, None)
                if not task:
                    log.warning(f"Got unexpected response from {resp.request.url}")
                    continue

                if resp.status != 200 or not resp.body:
                    continue

                body = self.post_fetch_hooks(resp.body, task)
                if not body:
                    continue

                elem = parse_html(body, base_url=task.url, backlink=task.backlink, depth=task.depth)
                elem = self.post_parse_hooks(elem, task)
                if elem is None:
                    continue

                # Enqueue new tasks discovered from this element
                if task.segments:
                    async for output in self._process_pipeline(
                        task=task,
                        elem=elem,
                        depth=task.depth,
                        max_depth=max_depth,
                        queue=queue,
                    ):
                        yield self.post_extract_hooks(output)
                else:
                    yield self.post_extract_hooks(elem)

                self.seen_urls.add(task.url)

        async with self.crawler as crawler:
            prod_task = asyncio.create_task(producer(crawler))
            async for item in consumer(crawler):
                yield item
            await prod_task

    async def _process_pipeline(
        self,
        task: CrawlTask,
        elem, 
        depth: int,
        max_depth: int,
        queue: asyncio.Queue[CrawlTask],
    ):
        mini_queue: deque[(HtmlElement, list[tuple[str, str]])] = deque([(elem, task.segments)])

        # breakpoint()
        while mini_queue:
            elem, segments = mini_queue.popleft()
            
            op, _ = segments[0]
            operator = get_operator(op)

            intents = operator(elem, segments, depth)

            if not intents:
                return

            for intent in intents:
                if isinstance(intent, DataIntent):
                    yield intent.value

                elif isinstance(intent, CrawlIntent):
                    next_depth = task.depth + 1
                    # if intent.url not in self.seen_urls and next_depth <= max_depth:
                    if next_depth <= max_depth:
                        # self.seen_urls.add(intent.url)
                        queue.put_nowait(
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