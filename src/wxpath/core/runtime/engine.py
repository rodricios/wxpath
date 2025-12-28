import asyncio
import inspect
import contextlib
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
    async def post_fetch_hooks(self, body, task):
        for hook in get_hooks():
            hook_method = getattr(hook, "post_fetch", lambda _, b: b)
            if inspect.iscoroutinefunction(hook_method):
                body = await hook_method(
                    FetchContext(task.url, task.backlink, task.depth, task.segments), 
                    body
                )
            else:
                body = hook_method(
                    FetchContext(task.url, task.backlink, task.depth, task.segments), 
                    body
                )
            if not body:
                log.debug(f"hook {type(hook).__name__} dropped {task.url}")
                break
        return body
    
    async def post_parse_hooks(self, elem, task):
        for hook in get_hooks():
            hook_method = getattr(hook, "post_parse", lambda _, e: e)
            if inspect.iscoroutinefunction(hook_method):
                elem = await hook_method(
                    FetchContext(url=task.url, backlink=task.backlink, depth=task.depth, segments=task.segments),
                    elem,
                )
            else:
                elem = hook_method(
                    FetchContext(url=task.url, backlink=task.backlink, depth=task.depth, segments=task.segments),
                    elem,
                )
            if elem is None:
                log.debug(f"hook {type(hook).__name__} dropped {task.url}")
                break
        return elem
    
    async def post_extract_hooks(self, value):
        for hook in get_hooks():
            hook_method = getattr(hook, "post_extract", lambda v: v)
            if inspect.iscoroutinefunction(hook_method):
                value = await hook_method(value)
            else:
                value = hook_method(value)
            if value is None:
                log.debug(f"hook {type(hook).__name__} dropped value")
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
        ):
        self.concurrency = concurrency
        self.per_host = per_host
        self.fetch_batch_size = fetch_batch_size
        self.seen_urls: set[str] = set()      # semantic traversal
        self.crawler = Crawler(concurrency=self.concurrency, per_host=self.per_host)

    async def run(self, expression: str, max_depth: int):
        segments = parse_wxpath_expr(expression)

        queue: asyncio.Queue[CrawlTask] = asyncio.Queue()
        inflight: dict[str, CrawlTask] = {}
        pending_tasks = 0

        def is_terminal():
            return queue.empty() and pending_tasks <= 0

        async with self.crawler as crawler:
            async def submitter():
                nonlocal pending_tasks
                while True:
                    task = await queue.get()

                    if task is None:
                        break

                    if task.url in self.seen_urls or task.url in inflight:
                        queue.task_done()
                        continue

                    # Mark URL as seen immediately
                    self.seen_urls.add(task.url)
                    inflight[task.url] = task

                    pending_tasks += 1
                    crawler.submit(Request(task.url, max_retries=0))
                    queue.task_done()

            submit_task = asyncio.create_task(submitter())

            # Seed the pipeline with a dummy task
            seed_task = CrawlTask(
                elem=None,
                url=None,
                segments=segments,
                depth=-1,
                backlink=None,
            )
            async for output in self._process_pipeline(
                task=seed_task,
                elem=None,
                depth=seed_task.depth,
                max_depth=max_depth,
                queue=queue,
            ):
                yield await self.post_extract_hooks(output)

            # While looping asynchronous generators, you MUST make sure 
            # to check terminal conditions before re-iteration.
            async for resp in crawler:
                task = inflight.pop(resp.request.url, None)
                pending_tasks -= 1

                if task is None:
                    log.warning(f"Got unexpected response from {resp.request.url}")
                    if is_terminal():
                        break
                    continue

                if resp.error:
                    log.warning(f"Got error from {resp.request.url}: {resp.error}")
                    if is_terminal():
                        break
                    continue

                # NOTE: Consider allowing redirects
                if resp.status != 200 or not resp.body:
                    log.warning(f"Got non-200 response from {resp.request.url}")
                    if is_terminal():
                        break
                    continue

                body = await self.post_fetch_hooks(resp.body, task)
                if not body:
                    if is_terminal():
                        break
                    continue

                elem = parse_html(
                    body,
                    base_url=task.url,
                    backlink=task.backlink,
                    depth=task.depth,
                )

                elem = await self.post_parse_hooks(elem, task)
                if elem is None:
                    if is_terminal():
                        break
                    continue

                if task.segments:
                    async for output in self._process_pipeline(
                        task=task,
                        elem=elem,
                        depth=task.depth,
                        max_depth=max_depth,
                        queue=queue,
                    ):

                        yield await self.post_extract_hooks(output)
                else:
                    yield await self.post_extract_hooks(elem)

                # Termination condition
                if is_terminal():
                    break

            submit_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await submit_task

    async def _process_pipeline(
        self,
        task: CrawlTask,
        elem, 
        depth: int,
        max_depth: int,
        queue: asyncio.Queue[CrawlTask],
    ):
        mini_queue: deque[(HtmlElement, list[tuple[str, str]])] = deque([(elem, task.segments)])

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