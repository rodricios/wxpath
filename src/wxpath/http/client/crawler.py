import abc

import aiohttp

try:
    from aiohttp_client_cache import CachedSession
    from aiohttp_client_cache import session as cached_session
except ImportError:
    CachedSession = None

import asyncio
import json
import time
import urllib.parse
from asyncio import Lock
from collections import defaultdict
from contextlib import nullcontext, suppress
from socket import gaierror
from typing import TYPE_CHECKING, Any, AsyncIterator, Callable, Mapping

from wxpath.http.client.cache import get_cache_backend
from wxpath.http.client.request import Request
from wxpath.http.client.response import Response
from wxpath.http.policy.retry import RetryPolicy
from wxpath.http.policy.robots import RobotsTxtPolicy
from wxpath.http.policy.throttler import AbstractThrottler, AutoThrottler
from wxpath.http.stats import CrawlerStats, build_trace_config
from wxpath.settings import CACHE_SETTINGS, CRAWLER_SETTINGS, AttrDict
from wxpath.util.logging import get_logger

log = get_logger(__name__)

if TYPE_CHECKING:
    from playwright.async_api import Playwright


def _get_playwright_imports() -> tuple[Callable[[], Any], Any]:
    """Load Playwright runtime dependencies only when needed.

    Returns:
        A tuple of ``(async_playwright, Stealth)``.

    Raises:
        RuntimeError: If required Playwright dependencies are not installed.
    """
    try:
        from playwright.async_api import async_playwright  # type: ignore[import-not-found]
    except ImportError as exc:
        raise RuntimeError(
            "Playwright support requires optional dependencies. "
            "Install with: pip install 'wxpath[playwright]'"
        ) from exc

    try:
        from playwright_stealth import Stealth  # type: ignore[import-not-found]
    except ImportError as exc:
        raise RuntimeError(
            "Playwright stealth mode requires playwright-stealth. "
            "Install with: pip install 'wxpath[playwright]'"
        ) from exc

    return async_playwright, Stealth

def get_async_session(
        headers: dict | None = None,
        timeout: aiohttp.ClientTimeout | None = None,
        connector: aiohttp.TCPConnector | None = None,
        trace_config: aiohttp.TraceConfig | None = None
) -> aiohttp.ClientSession:
    """
    Create and return a new aiohttp session. If aiohttp-client-cache is available
    and enabled, return a new CachedSession bound to the configured SQLite backend.
    The caller is responsible for closing the session.
    """

    if timeout is None:
        timeout = aiohttp.ClientTimeout(total=CRAWLER_SETTINGS.timeout)

    if CACHE_SETTINGS.enabled and CachedSession:
        log.info("using aiohttp-client-cache")
        return CachedSession(
            cache=get_cache_backend(),
            headers=headers,
            timeout=timeout,
            connector=connector,
            trace_configs=[trace_config] if trace_config is not None else None
        )

    return aiohttp.ClientSession(
        headers=headers, 
        timeout=timeout, 
        connector=connector, 
        trace_configs=[trace_config] if trace_config is not None else None
    )


class BaseCrawler(abc.ABC):
    """Base class with retry and throttling logic.
    TODO: Should likely rename.
    """
    def __init__(
            self, 
            *,
            concurrency: int = None,
            per_host: int = None,
            timeout: int = None,
            headers: dict | None = None,
            proxies: dict | None = None,
            verify_ssl: bool | None = None,
            throttler: AbstractThrottler | None = None,
            auto_throttle_target_concurrency: float = None,
            auto_throttle_start_delay: float = None,
            auto_throttle_max_delay: float = None,
            respect_robots: bool = True,
            retry_policy: RetryPolicy | None = None
        ):
        cfg = CRAWLER_SETTINGS
        self._closed = False

        #### CONCURRENCY CONFIG ####
        self.concurrency = concurrency if concurrency is not None else cfg.concurrency
        self.per_host = per_host if per_host is not None else cfg.per_host

        self._sem_global = asyncio.Semaphore(self.concurrency)
        self._sem_host = defaultdict(lambda: asyncio.Semaphore(self.per_host))
        #### END CONCURRENCY CONFIG ####
        
        self._verify_ssl = verify_ssl if verify_ssl is not None else getattr(
            cfg, "verify_ssl", True
        )

        timeout = timeout if timeout is not None else cfg.timeout
        self._timeout = aiohttp.ClientTimeout(total=timeout)

        self._headers = cfg.headers | (headers or {})

        #### THROTTLING CONFIG ####

        # auto-throttle defaults
        auto_throttle_target_concurrency = auto_throttle_target_concurrency \
            if auto_throttle_target_concurrency is not None \
            else cfg.auto_throttle_target_concurrency
        
        auto_throttle_start_delay = auto_throttle_start_delay \
            if auto_throttle_start_delay is not None \
            else cfg.auto_throttle_start_delay

        auto_throttle_max_delay = auto_throttle_max_delay \
            if auto_throttle_max_delay is not None \
            else cfg.auto_throttle_max_delay

        self.throttler = throttler or AutoThrottler(
            target_concurrency=auto_throttle_target_concurrency or self.concurrency/4.0,
            start_delay=auto_throttle_start_delay,
            max_delay=auto_throttle_max_delay,
        )
        #### END THROTTLING CONFIG ####

        #### INTERNAL COMMUNICATION CHANNELS ####
        self._pending: asyncio.Queue[Request] = asyncio.Queue()
        self._results: asyncio.Queue[Response] = asyncio.Queue()
        #### END INTERNAL COMMUNICATION CHANNELS ####

        self.retry_policy = retry_policy or RetryPolicy()

        self._stats = CrawlerStats()

        _proxies = proxies if proxies is not None else cfg.proxies
        self._proxies = _proxies if (isinstance(_proxies, defaultdict) or _proxies) else {}

        self.respect_robots = respect_robots if respect_robots is not None else cfg.respect_robots
        self._robots_policy: RobotsTxtPolicy | None = None

    @abc.abstractmethod
    async def __aenter__(self) -> "Crawler":
        raise NotImplementedError
    
    @abc.abstractmethod
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        raise NotImplementedError
    
    def submit(self, req: Request) -> None:
        """Queue a request for fetching or raise if crawler already closed."""
        if self._closed:
            raise RuntimeError("crawler is closed")
        self._pending.put_nowait(req)

    def __aiter__(self) -> AsyncIterator[Response]:
        return self._result_iter()

    async def _result_iter(self) -> AsyncIterator[Response]:
        """Async iterator yielding responses as workers produce them."""
        # while not self._closed:
        while not (self._closed and self._results.empty()):
            resp = await self._results.get()
            self._results.task_done()
            yield resp

    async def _worker(self) -> None:
        """Worker loop that fetches pending requests and enqueues results."""
        while True:
            req = await self._pending.get()
            try:
                # TODO: handle fetch/throttle-then-fetch/throttle-then-fetch-or-retry/etc. 
                #       policies here.
                resp = await self._fetch_or_throttle_or_retry(req)
                if resp is not None:
                    await self._results.put(resp)

            except asyncio.CancelledError:
                # Must propagate cancellation
                log.debug("cancelled error", extra={"url": req.url})
                raise

            except gaierror as exc:
                # Emit an error response so callers can account for task completion.
                # Swallowing DNS failures can deadlock consumers waiting on results.
                log.warning("DNS error", extra={"url": req.url})
                await self._results.put(Response(req, 0, b"", error=exc))

            except Exception as exc:
                log.error("exception", extra={"url": req.url}, exc_info=exc)
                # Last-resort safety: never drop a request silently
                await self._results.put(Response(req, 0, b"", error=exc))
            finally:
                self._pending.task_done()

    async def _fetch_one(self, req: Request) -> Response | None:
        """Fetch a single request without throttling or retrying.
        
        Implementation must provide status status, request_start, response_end for auto-throttling 
        and retry logic to work.
        """
        raise NotImplementedError
    
    async def _fetch_or_throttle_or_retry(self, req: Request) -> Response | None:
        """Fetch a single request, handling robots, throttling, and retries."""
        host = req.hostname

        if self._robots_policy:
            can_fetch = await self._robots_policy.can_fetch(
                req.url, self._headers.get("User-Agent")
            )
            if not can_fetch:
                log.debug("disallowed by robots.txt", extra={"url": req.url})
                return Response(req, 403, b"", error=RuntimeError("Disallowed by robots.txt"))

        # TODO: Move this filter to hooks
        if req.url.lower().endswith((".pdf", ".zip", ".exe")):
            req.max_retries = 0

        async with self._sem_global, self._sem_host[host]:
            t0 = asyncio.get_running_loop().time()
            await self.throttler.wait(host)
            dt = asyncio.get_running_loop().time() - t0

            self._stats.throttle_waits += 1
            self._stats.throttle_wait_time += dt
            self._stats.throttle_waits_by_host[host] += 1

            log.info("fetching", extra={"url": req.url})
            
            start = time.monotonic()
            try:
                resp = await self._fetch_one(req)
                
                self.throttler.record_latency(host, resp.latency)

                if self.retry_policy.should_retry(req, response=resp):
                    await self._retry(req)
                    return None

                return resp
                # return Response(req, resp.status, body, dict(resp.headers))
            except asyncio.CancelledError:
                # Normal during shutdown / timeout propagation
                log.debug("cancelled error", extra={"url": req.url})
                raise
            except Exception as exc:
                latency = time.monotonic() - start
                self.throttler.record_latency(host, latency)

                if self.retry_policy.should_retry(req, exception=exc):
                    await self._retry(req)
                    return None
                
                log.error("request failed", extra={"url": req.url}, exc_info=exc)
                return Response(req, 0, b"", error=exc)

    async def _retry(self, req: Request) -> None:
        """Reschedule a request according to the retry policy."""
        req.retries += 1
        delay = self.retry_policy.get_delay(req)

        log.warning(
            "retrying",
            extra={"url": req.url, "retry": req.retries, "delay": delay},
        )

        if delay:
            await asyncio.sleep(delay)

        self.submit(req)

    def _proxy_for(self, url: str) -> str | None:
        host = urllib.parse.urlsplit(url).hostname
        try:
            # bracket notation first, for defaultdicts
            value = self._proxies[host]
        except KeyError:
            value = self._proxies.get(host)
        
        if not value:
            log.debug("proxy", extra={"host": host, "value": value})
        return value


class PlaywrightCrawler(BaseCrawler):
    """Crawler implementation backed by a headless Playwright browser."""

    def __init__(self, stealth: bool = False, *args, **kwargs):
        """Initialize a Playwright-backed crawler.

        Args:
            stealth: Enable playwright-stealth evasions.
            *args: Positional arguments forwarded to ``BaseCrawler``.
            **kwargs: Keyword arguments forwarded to ``BaseCrawler``.
        """
        super().__init__(*args, **kwargs)

        self.stealth = stealth

        self._async_playwright: Callable[[], Any] | None = None
        self._stealth_cls: Any | None = None
        self._stealth_playwright = None
        self._playwright: Playwright | None = None
        self._browser = None
        self._cache_backend = None

        self._null_lock = nullcontext()

        # Reflecting ClientSession's internal cookie jar
        # self._cookie_jar = None

    async def __aenter__(self) -> "PlaywrightCrawler":
        """Start Playwright browser resources and worker tasks."""
        if self._async_playwright is None or self._stealth_cls is None:
            self._async_playwright, self._stealth_cls = _get_playwright_imports()

        # if self.stealth and self._stealth_playwright is None:
        #     self._stealth_playwright = await Stealth().use_async(async_playwright()).__aenter__()
        #     breakpoint()

        if self._playwright is None:
            if self.stealth:
                self._playwright = await self._stealth_cls().use_async(
                    self._async_playwright()
                ).__aenter__()
            else:
                self._playwright = await self._async_playwright().start()

        if self._browser is None:
            self._browser = await self._playwright.chromium.launch(headless=True)

        # Note: Set robots policy after session is created
        if self.respect_robots:
            self._robots_policy = RobotsTxtPolicy(self._session)

        if CACHE_SETTINGS.enabled and self._cache_backend is None:
            self._cache_backend = get_cache_backend()

        # if self._cookie_jar is None:
        #     # Reflecting ClientSession's internal cookie jar
        #     self._cookie_jar = CookieJar(loop=asyncio.get_running_loop())

        self._workers = [
            asyncio.create_task(self._worker(), name=f"crawler-worker-{i}")
            for i in range(self.concurrency)
        ]   
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Tear down workers, browser resources, and cache backend."""
        self._closed = True

        for worker in self._workers:
            worker.cancel()
        await asyncio.gather(*self._workers, return_exceptions=True)
        self._workers = []

        if self._cache_backend is not None:
            close_fn = getattr(self._cache_backend, "close", None)
            if callable(close_fn):
                await close_fn()

        if self._browser is not None:
            with suppress(Exception):
                await self._browser.close()
        if self._playwright is not None:
            with suppress(Exception):
                await self._playwright.stop()

        self._playwright = None
        self._browser = None
        self._cache_backend = None
        self._robots_policy = None

    def _build_raw_headers(self, headers: Mapping[str, str]) -> tuple[tuple[bytes, bytes], ...]:
        """Build aiohttp-compatible raw headers.

        Args:
            headers: Mapping of header names to header values.

        Returns:
            Header tuples encoded as UTF-8 bytes.
        """
        return tuple(
            (str(key).encode("utf-8"), str(value).encode("utf-8"))
            for key, value in headers.items()
        )

    def _build_cache_response_silhouette(self, response, body: str) -> AttrDict:
        """Build a ClientResponse-like object compatible with aiohttp-client-cache.

        Args:
            response: Playwright response-like object.
            body: HTML payload returned by Playwright.

        Returns:
            AttrDict with the minimal shape required by cache serialization.
        """
        response_headers = dict(response.headers)
        request_headers = self._headers
        raw_headers = self._build_raw_headers(response_headers)
        request_info = AttrDict(
            real_url=response.url,
            headers=request_headers,
        )
        return AttrDict(
            url=response.url,
            reason=response.status_text,
            method="GET",
            status=response.status,
            _body=body,
            raw_headers=raw_headers,
            headers=response_headers,
            cookies=[],
            version="playwright",  # version typically holds aiohttp-client-cache version
            _released=True,  # response already read
            links={},
            get_encoding=lambda: None,
            request_info=request_info,
            history=[],
        )

    async def _fetch_one(self, req: Request) -> Response | None:
        """Return cached response or fetch a single request"""

        if req.pagination is not None:
            return await self._fetch_paginated(req)

        actions = None
        if self._cache_backend is not None:
            key = self._cache_backend.create_key('GET', req.url, headers=self._headers)
            actions = self._cache_backend.create_cache_actions(
                key,
                req.url,
                expire_after=CACHE_SETTINGS.expire_after,
                refresh=False,
                headers=self._headers,
            )
            lock: Lock | nullcontext = (
                self._null_lock
                if actions.skip_read
                else cached_session._get_lock(id(self), key)
            )
            async with lock:
                response = await self._cache_backend.request(actions)
                if response:
                    log.debug(f'Using cached response for {req.url}')
                    return Response(
                        req,
                        response.status,
                        response._body,
                        headers=dict(response.headers),
                        request_start=0,
                        response_end=0,
                    )

        # page = await self._browser.new_page()
        context = await self._browser.new_context(
            extra_http_headers=self._headers,
            user_agent=self._headers.get("User-Agent"),
            viewport={"width": 1280, "height": 720},
        )

        page = await context.new_page()

        request_start = time.monotonic()
        response = await page.goto(req.url, wait_until="domcontentloaded")
        # Wait for page to be stable before reading content
        try:
            await page.wait_for_load_state("networkidle", timeout=5000)
        except Exception:
            # If networkidle times out, at least wait for load
            await page.wait_for_load_state("load", timeout=5000)
        
        # Retry content() if page is still navigating
        max_retries = 3
        for attempt in range(max_retries):
            try:
                body = await page.content()
                break
            except Exception as e:
                if "navigating" in str(e).lower() and attempt < max_retries - 1:
                    await asyncio.sleep(0.1 * (attempt + 1))
                    continue
                raise
        response_end = time.monotonic()

        # cookies = await context.cookies()
        await context.close()

        if actions is not None:
            actions.update_from_response(response)
            cached_response = self._build_cache_response_silhouette(response, body)
            if await self._cache_backend.is_cacheable(cached_response, actions):
                try:
                    await self._cache_backend.save_response(
                        cached_response,
                        actions.key,
                        actions.expires,
                    )
                    log.info("[CACHE WRITE]", extra={"req.url": req.url, "resp.url": response.url})
                except Exception as exc:
                    log.warning(
                        "playwright cache write failed",
                        extra={"req.url": req.url, "resp.url": response.url},
                        exc_info=exc,
                    )
        
        # TODO: Should we pass down headers like we do in Crawler()? 
        return Response(req, response.status, body, 
                        headers=dict(response.headers),
                        request_start=request_start, response_end=response_end)

    async def _fetch_paginated(self, req: Request) -> Response:
        """Click through a browser page sequence and emit pages as they arrive.

        Paginated requests bypass the single-URL cache: later pages may be
        produced by client-side state without distinct URLs. The final page is
        returned to the worker; earlier pages are placed on its result queue.

        Args:
            req: Request with pagination instructions.

        Returns:
            Final page response or a terminal response after an unchanged page.

        generated by AI - requires human review
        """
        from playwright.async_api import TimeoutError as PlaywrightTimeoutError

        pagination = req.pagination
        if pagination is None:
            raise ValueError("pagination instructions are required")

        context = await self._browser.new_context(
            extra_http_headers=self._headers,
            user_agent=self._headers.get("User-Agent"),
            viewport={"width": 1280, "height": 720},
        )
        start = time.monotonic()
        try:
            page = await context.new_page()
            navigation = await page.goto(req.url, wait_until="domcontentloaded")
            if navigation is None:
                raise RuntimeError(f"No navigation response for {req.url}")

            for page_number in range(pagination.max_pages):
                try:
                    await page.wait_for_load_state("networkidle", timeout=5000)
                except PlaywrightTimeoutError:
                    await page.wait_for_load_state("load", timeout=5000)

                body = await page.content()
                page_url = page.url
                result = Response(
                    req,
                    navigation.status,
                    body,
                    headers=dict(navigation.headers),
                    request_start=start,
                    response_end=time.monotonic(),
                    page_url=page_url,
                )
                if page_number + 1 == pagination.max_pages:
                    return result

                next_control = page.locator(f"xpath={pagination.click_xpath}").first
                if not await next_control.count() or not await next_control.is_visible():
                    return result
                if not await next_control.is_enabled():
                    return result

                result.complete = False
                await self._results.put(result)

                previous_dom = await page.evaluate("document.documentElement.outerHTML")
                await next_control.click(timeout=10000)
                try:
                    await page.wait_for_function(
                        "previous => document.documentElement.outerHTML !== previous",
                        arg=previous_dom,
                        timeout=10000,
                    )
                except PlaywrightTimeoutError:
                    return Response(
                        req,
                        result.status,
                        b"",
                        request_start=start,
                        response_end=time.monotonic(),
                        page_url=page_url,
                        terminal=True,
                    )

                if await page.content() == body and page.url == page_url:
                    return Response(
                        req,
                        result.status,
                        b"",
                        request_start=start,
                        response_end=time.monotonic(),
                        page_url=page_url,
                        terminal=True,
                    )

            raise AssertionError("pagination loop exceeded its page limit")
        finally:
            await context.close()

class Crawler(BaseCrawler):
    """
    Concurrent HTTP crawler that manages throttling, retries, and robots.
    TODO: Rename to AIOHTTPCrawler

    Example:
        from wxpath.http.client.crawler import Crawler, Request
        
        resps = []
        async def main(crawler, urls):
            async with crawler as crawler:
                for url in urls:
                    crawler.submit(Request(url, max_retries=0))
    
                async for resp in crawler:
                    resps.append(resp)
                    if len(resps) >= len(urls):
                        break
        
        crawler = Crawler()
        asyncio.run(main(crawler, ['https://example.com']))
    """

    def __init__(
        self,
        *,
        headers: dict | None = None,
        proxies: dict | None = None,
        verify_ssl: bool | None = None,
        retry_policy: RetryPolicy | None = None,
        throttler: AbstractThrottler | None = None,
        auto_throttle_target_concurrency: float = None,
        auto_throttle_start_delay: float = None,
        auto_throttle_max_delay: float = None,
        respect_robots: bool = True,
        **kwargs
    ):
        super().__init__(**kwargs)
        cfg = CRAWLER_SETTINGS

        self.retry_policy = retry_policy or RetryPolicy()

        # auto-throttle defaults
        auto_throttle_target_concurrency = auto_throttle_target_concurrency \
            if auto_throttle_target_concurrency is not None \
            else cfg.auto_throttle_target_concurrency
        
        auto_throttle_start_delay = auto_throttle_start_delay \
            if auto_throttle_start_delay is not None \
            else cfg.auto_throttle_start_delay

        auto_throttle_max_delay = auto_throttle_max_delay \
            if auto_throttle_max_delay is not None \
            else cfg.auto_throttle_max_delay

        self.throttler = throttler or AutoThrottler(
            target_concurrency=auto_throttle_target_concurrency or self.concurrency/4.0,
            start_delay=auto_throttle_start_delay,
            max_delay=auto_throttle_max_delay,
        )

        self._session: aiohttp.ClientSession | None = None
        self._workers: list[asyncio.Task] = []
        self._closed = False
        self._stats = CrawlerStats()

        self.respect_robots = respect_robots if respect_robots is not None else cfg.respect_robots
        self._robots_policy: RobotsTxtPolicy | None = None

        # WARN: If SQLiteBackend caching is enabled and min(concurrency, per_host) > 1,
        #       write-contention is likely to occur.
        if (CACHE_SETTINGS.enabled 
            and CACHE_SETTINGS.backend == "sqlite"
            and min(self.concurrency, self.per_host) > 1
            ):
            log.warning(
                "SQLiteBackend caching is enabled and min(concurrency, per_host) > 1. "
                "Write-contention is likely to occur. Consider using RedisBackend."
            )

    def build_session(self) -> aiohttp.ClientSession:
        """Construct an `aiohttp.ClientSession` with tracing and pooling."""
        trace_config = build_trace_config(self._stats)
        # Need to build the connector as late as possible as it requires the loop
        connector = aiohttp.TCPConnector(
            limit=self.concurrency * 2,
            ttl_dns_cache=300,
            ssl=self._verify_ssl,
        )
        return get_async_session(
            headers=self._headers,
            timeout=self._timeout,
            connector=connector,
            trace_config=trace_config
        )

    async def __aenter__(self) -> "Crawler":
        """Initialize HTTP session and start background workers."""
        if self._session is None:
            # self._session = aiohttp.ClientSession(timeout=self._timeout)
            self._session = self.build_session()

        # Note: Set robots policy after session is created
        if self.respect_robots:
            self._robots_policy = RobotsTxtPolicy(self._session)

        self._workers = [
            asyncio.create_task(self._worker(), name=f"crawler-worker-{i}")
            for i in range(self.concurrency)
        ]
        return self

    async def __aexit__(self, *_) -> None:
        """Tear down workers and close the HTTP session."""
        self._closed = True
        for w in self._workers:
            w.cancel()

        await asyncio.gather(*self._workers, return_exceptions=True)

        if self._session:
            await self._session.close()

    def _proxy_for(self, url: str) -> str | None:
        host = urllib.parse.urlsplit(url).hostname
        try:
            # bracket notation first, for defaultdicts
            value = self._proxies[host]
        except KeyError:
            value = self._proxies.get(host)
        
        if not value:
            log.debug("proxy", extra={"host": host, "value": value})
        return value
    
    async def _fetch_one(self, req: Request) -> Response | None:
        start = time.monotonic()
        async with self._session.get(
            req.url,
            headers=self._headers | req.headers,
            proxy=self._proxy_for(req.url),
            timeout=req.timeout or self._timeout,
        ) as resp:
            from_cache = getattr(resp, "from_cache", False)
            if from_cache:
                # NOTE: This is a bit of a hack, but it works. aiohttp-client-cache does not
                #  interface with TraceConfigs on cache hit, so we have to do it here.
                self._stats.requests_cache_hit += 1
                log.info("[CACHE HIT]", extra={"req.url": req.url, "resp.url": resp.url})
            else:
                log.info("[CACHE MISS]", extra={"req.url": req.url, "resp.url": resp.url})

            body = await resp.read()

            return Response(req, resp.status, body, 
                            headers=resp.headers,
                            request_start=start, 
                            response_end=time.monotonic())



class FlareSolverrCrawler(Crawler):
    def __init__(self, flaresolverr_url: str = "http://localhost:8191/v1", *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.flaresolverr_url = flaresolverr_url

    async def _fetch_one(self, req):
        """Override the fetch method to send requests via FlareSolverr API."""
        # Prepare the FlareSolverr payload
        payload = {
            "cmd": "request.get",
            "url": req.url,
            "maxTimeout": 60000, # 60 seconds
            # You can map wxpath headers here if needed, but be careful 
            # as FlareSolverr manages its own browser headers.
        }

        start = time.monotonic()

        # We POST to FlareSolverr instead of GETting the target directly
        async with self._session.post(
            self.flaresolverr_url, 
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=req.timeout or self._timeout
        ) as resp:
            data = await resp.json()
            
            if data.get("status") == "ok":
                solution = data.get("solution", {})
                
                # Construct a standard wxpath Response object
                # This tricks the engine into thinking it did a normal crawl
                return Response(
                    request=req,
                    status=solution.get("status", 200),
                    body=solution.get("response", "").encode('utf-8'),
                    headers=solution.get("headers", {}),
                    request_start=start,
                    response_end=time.monotonic(),
                    # You could also store cookies here if you wanted to maintain a session
                )
            else:
                # Handle FlareSolverr errors (timeouts, etc)
                error_msg = data.get("message", "Unknown FlareSolverr Error")
                return Response(req, 500, json.dumps({"flaresolverr_data": data}).encode('utf-8'),
                                error=RuntimeError(error_msg),
                                request_start=start, response_end=time.monotonic())
