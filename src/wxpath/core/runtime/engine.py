import asyncio
import contextlib
import inspect
from collections import deque
from typing import Any, AsyncGenerator, Iterator

from lxml.html import HtmlElement
from tqdm import tqdm

from wxpath import patches  # noqa: F401
from wxpath.core import parser
from wxpath.core.models import (
    CrawlIntent,
    CrawlTask,
    DataIntent,
    ExtractIntent,
    InfiniteCrawlIntent,
    ProcessIntent,
)
from wxpath.core.ops import get_operator
from wxpath.core.parser import Binary, Depth, Segment, Segments
from wxpath.core.runtime.helpers import parse_html
from wxpath.hooks.registry import FetchContext, get_hooks
from wxpath.http.client.crawler import Crawler
from wxpath.http.client.request import Request
from wxpath.util.logging import get_logger

log = get_logger(__name__)


class HookedEngineBase:
    """Common hook invocation helpers shared by engine variants."""

    async def post_fetch_hooks(self, body: bytes | str, task: CrawlTask) -> bytes | str | None:
        """Run registered `post_fetch` hooks over a fetched response body.

        Hooks may be synchronous or asynchronous and can transform or drop the
        response payload entirely.

        Args:
            body: Raw response body bytes from the crawler.
            task: The `CrawlTask` that produced the response.

        Returns:
            The transformed body, or `None` if any hook chooses to drop it.
        """
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
    
    async def post_parse_hooks(
        self, elem: HtmlElement | None, task: CrawlTask
    ) -> HtmlElement | None:
        """Run registered `post_parse` hooks on a parsed DOM element.

        Args:
            elem: Parsed `lxml` element to process.
            task: The originating `CrawlTask`.

        Returns:
            The transformed element, or `None` if a hook drops the branch.
        """
        for hook in get_hooks():
            hook_method = getattr(hook, "post_parse", lambda _, e: e)
            if inspect.iscoroutinefunction(hook_method):
                elem = await hook_method(
                    FetchContext(
                        url=task.url, 
                        backlink=task.backlink, 
                        depth=task.depth, 
                        segments=task.segments
                    ),
                    elem,
                )
            else:
                elem = hook_method(
                    FetchContext(
                        url=task.url, 
                        backlink=task.backlink, 
                        depth=task.depth, 
                        segments=task.segments
                    ),
                    elem,
                )
            if elem is None:
                log.debug(f"hook {type(hook).__name__} dropped {task.url}")
                break
        return elem
    
    async def post_extract_hooks(self, value: Any) -> Any | None:
        """Run registered `post_extract` hooks on extracted values.

        Args:
            value: The extracted datum to post-process.

        Returns:
            The transformed value, or `None` if a hook drops it.
        """
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


class WXPathEngine(HookedEngineBase):
    """Main class for executing wxpath expressions.

    The core pattern is to build a queue of CrawlTasks that are crawled and
    processed FIFO. Traversal of the queue (and therefore the web graph) is
    done concurrently in BFS-ish order.

    Args:
        crawler: Crawler instance to use for HTTP requests.
        concurrency: Number of concurrent fetches at the Crawler level.
        per_host: Number of concurrent fetches per host.
        respect_robots: Whether to respect robots.txt directives.
        allowed_response_codes: Set of allowed HTTP response codes. Defaults
            to ``{200}``. Responses may still be filtered and dropped.
        allow_redirects: Whether to follow HTTP redirects. Defaults to ``True``.
    """
    def __init__(
            self, 
            crawler: Crawler | None = None,
            concurrency: int = 16, 
            per_host: int = 8,
            respect_robots: bool = True,
            allowed_response_codes: set[int] = None,
            allow_redirects: bool = True,
        ):
        # NOTE: Will grow unbounded in large crawls. Consider a LRU cache, or bloom filter.
        self.seen_urls: set[str] = set()
        self.crawler = crawler or Crawler(
            concurrency=concurrency, 
            per_host=per_host,
            respect_robots=respect_robots
        )
        self.allowed_response_codes = allowed_response_codes or {200}
        self.allow_redirects = allow_redirects
        if allow_redirects:
            self.allowed_response_codes |= {301, 302, 303, 307, 308}

    def _get_max_depth(self, bin_or_segs: Binary | Segments, max_depth: int) -> int:
        """Get the maximum crawl depth for a given expression. Will find a Depth
        argument at the beginning of the expression and return its value. Otherwise, returns the
        max_depth value provided.
        TODO: There has to be a better way to do this.
        """
        if isinstance(bin_or_segs, Binary):
            if hasattr(bin_or_segs.left, 'func') == 'url': 
                depth_arg = [arg for arg in bin_or_segs.left.args if isinstance(arg, Depth)][0]
                return int(depth_arg.value)
            elif hasattr(bin_or_segs.right, 'func') == 'url':
                depth_arg = [arg for arg in bin_or_segs.right.args if isinstance(arg, Depth)][0]
                return int(depth_arg.value)
        elif isinstance(bin_or_segs, Segments):
            depth_arg = [arg for arg in bin_or_segs[0].args if isinstance(arg, Depth)]
            if depth_arg:
                return int(depth_arg[0].value)
        return max_depth

    async def run(
            self, 
            expression: str, 
            max_depth: int, 
            progress: bool = False,
            yield_errors: bool = False,
        ) -> AsyncGenerator[Any, None]:
        """Execute a wxpath expression concurrently and yield results.

        Builds and drives a BFS-like crawl pipeline that honors robots rules,
        throttling, and hook callbacks while walking the web graph.

        NOTES ON max_depth:
        If depth is provided in the expression, it will be used to limit the depth of the
        crawl. If depth is provided in the expression and max_depth is provided as an argument
        to `run`, the inline depth in the expression will take precedence.

        Currently, max_depth control flow logic is detected and executed in the
        engine. In the future, the operation handlers (ops.py) could be responsible for 
        detecting max_depth, and sending a terminal intent to the engine. It's also possible 
        that the depth terminals are relative to the current depth (i.e. `url(//xpath, depth=2)`
        implies crawling only the next 2 levels). This is not yet supported.

        Args:
            expression: WXPath expression string to evaluate.
            max_depth: Maximum crawl depth to follow for url hops.
            progress: Whether to display a progress bar.

        Yields:
            Extracted values produced by the expression (HTML elements or
            wxpath-specific value types).
        """
        bin_or_segs = parser.parse(expression)

        max_depth = self._get_max_depth(bin_or_segs, max_depth)

        queue: asyncio.Queue[CrawlTask] = asyncio.Queue()
        inflight: dict[str, CrawlTask] = {}
        pending_tasks = 0

        def is_terminal():
            # NOTE: consider adopting state machine pattern for determining 
            #       the current state of the engine.
            return queue.empty() and pending_tasks <= 0

        total_yielded = 0
        if progress:
            pbar = tqdm(total=0)
        else:
            pbar = None

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
                segments=bin_or_segs,
                depth=-1,
                backlink=None,
            )
            async for output in self._process_pipeline(
                task=seed_task,
                elem=None,
                depth=seed_task.depth,
                max_depth=max_depth,
                queue=queue,
                pbar=pbar,
            ):
                yield await self.post_extract_hooks(output)

            # While looping asynchronous generators, you MUST make sure 
            # to check terminal conditions before re-iteration.
            async for resp in crawler:
                if pbar is not None:
                    pbar.update(1)
                    pbar.refresh()

                task = inflight.pop(resp.request.url, None)
                pending_tasks -= 1

                if task is None:
                    log.warning(f"Got unexpected response from {resp.request.url}")

                    if yield_errors:
                        yield {
                            "__type__": "error",
                            "url": resp.request.url,
                            "reason": "unexpected_response",
                            "status": resp.body,
                            "body": resp.body
                        }
                        
                    if is_terminal():
                        break
                    continue

                if resp.error:
                    log.warning(f"Got error from {resp.request.url}: {resp.error}")

                    if yield_errors:
                        yield {
                            "__type__": "error",
                            "url": resp.request.url,
                            "reason": "network_error",
                            "exception": str(resp.error),
                            "status": resp.status,
                            "body": resp.body
                        }
                    if is_terminal():
                        break
                    continue

                # NOTE: Consider allowing redirects
                if resp.status not in self.allowed_response_codes or not resp.body:
                    log.warning(f"Got non-200 response from {resp.request.url}")

                    if yield_errors:
                        yield {
                            "__type__": "error",
                            "url": resp.request.url,
                            "reason": "bad_status",
                            "status": resp.status,
                            "body": resp.body
                        }

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
                    response=resp
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
                        pbar=pbar
                    ):  
                        total_yielded += 1
                        if pbar is not None:
                            pbar.set_postfix(yielded=total_yielded, depth=task.depth,)

                        yield await self.post_extract_hooks(output)
                else:
                    total_yielded += 1
                    if pbar is not None:
                        pbar.set_postfix(yielded=total_yielded, depth=task.depth,)

                    yield await self.post_extract_hooks(elem)

                # Termination condition
                if is_terminal():
                    break

            submit_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await submit_task

        if pbar is not None:
            pbar.close()

    async def _process_pipeline(
        self,
        task: CrawlTask,
        elem: Any, 
        depth: int,
        max_depth: int,
        queue: asyncio.Queue[CrawlTask],
        pbar: tqdm = None
    ) -> AsyncGenerator[Any, None]:
        """Process a queue of intents for a single crawl branch.

        Traverses wxpath segments depth-first within a page while coordinating
        newly discovered crawl intents back to the shared queue.

        Args:
            task: The originating crawl task for this branch.
            elem: Current DOM element (or extracted value) being processed.
            depth: Current traversal depth.
            max_depth: Maximum permitted crawl depth.
            queue: Shared crawl queue for enqueuing downstream URLs.

        Yields:
            object: Extracted values or processed elements as produced by operators.
        """
        mini_queue: deque[tuple[HtmlElement | Any, list[Binary | Segment] | Segments]] = deque(
            [(elem, task.segments)]
        )

        while mini_queue:
            elem, bin_or_segs = mini_queue.popleft()

            binary_or_segment = bin_or_segs if isinstance(bin_or_segs, Binary) else bin_or_segs[0]
            operator = get_operator(binary_or_segment)
            intents = operator(elem, bin_or_segs, depth)

            if not intents:
                return

            for intent in intents:
                if isinstance(intent, DataIntent):
                    yield intent.value

                elif isinstance(intent, CrawlIntent):
                    next_depth = task.depth + 1
                    # if intent.url not in self.seen_urls and next_depth <= max_depth:
                    if next_depth <= max_depth and intent.url not in self.seen_urls:
                        # self.seen_urls.add(intent.url)
                        log.debug(f"Depth: {next_depth}; Enqueuing {intent.url}")
                        
                        queue.put_nowait(
                            CrawlTask(
                                elem=None,
                                url=intent.url,
                                segments=intent.next_segments,
                                depth=next_depth,
                                backlink=task.url,
                            )
                        )
                        if pbar is not None:
                            pbar.total += 1
                            pbar.refresh()

                elif isinstance(intent, (ExtractIntent, ProcessIntent, InfiniteCrawlIntent)):
                    # immediately traverse the extraction
                    elem = intent.elem
                    next_segments = intent.next_segments
                    mini_queue.append((elem, next_segments))


def wxpath_async(path_expr: str,
                 max_depth: int,
                 progress: bool = False,
                 engine: WXPathEngine | None = None,
                 yield_errors: bool = False
                 ) -> AsyncGenerator[Any, None]:
    if engine is None:
        engine = WXPathEngine()
    return engine.run(path_expr, max_depth, progress=progress, yield_errors=yield_errors)


##### ASYNC IN SYNC #####
def wxpath_async_blocking_iter(
    path_expr: str,
    max_depth: int = 1,
    progress: bool = False,
    engine: WXPathEngine | None = None,
    yield_errors: bool = False
) -> Iterator[Any]:
    """Evaluate a wxpath expression using concurrent breadth-first traversal.

    Warning:
        Spins up its own event loop therefore this function must **not** be
        invoked from within an active asyncio event loop.

    Args:
        path_expr: A wxpath expression.
        max_depth: Maximum crawl depth. Must be at least the number of
            ``url*`` segments minus one.
        engine: Optional pre-configured WXPathEngine instance.

    Yields:
        object: Extracted objects (HtmlElement, WxStr, dict, or other values)
        produced by the expression evaluator.
    """
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    agen = wxpath_async(path_expr, max_depth=max_depth, progress=progress, 
                        engine=engine, yield_errors=yield_errors)

    try:
        while True:
            try:
                yield loop.run_until_complete(agen.__anext__())
            except StopAsyncIteration:
                break
    finally:
        loop.run_until_complete(loop.shutdown_asyncgens())
        loop.close()


def wxpath_async_blocking(
    path_expr: str,
    max_depth: int = 1,
    progress: bool = False,
    engine: WXPathEngine | None = None,
    yield_errors: bool = False
) -> list[Any]:
    return list(wxpath_async_blocking_iter(path_expr, 
                                           max_depth=max_depth, 
                                           progress=progress, 
                                           engine=engine,
                                           yield_errors=yield_errors,
                                           ))