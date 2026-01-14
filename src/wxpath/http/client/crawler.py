import asyncio
import time
import urllib.parse
from collections import defaultdict
from socket import gaierror
from typing import AsyncIterator

import aiohttp

from wxpath.http.client.request import Request
from wxpath.http.client.response import Response
from wxpath.http.policy.retry import RetryPolicy
from wxpath.http.policy.robots import RobotsTxtPolicy
from wxpath.http.policy.throttler import AbstractThrottler, AutoThrottler
from wxpath.http.stats import CrawlerStats, build_trace_config
from wxpath.util.logging import get_logger

log = get_logger(__name__)

HEADERS = {"User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)" 
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/142.0.0.0 Safari/537.36")}


class Crawler:
    """Concurrent HTTP crawler that manages throttling, retries, and robots."""

    def __init__(
        self,
        concurrency: int = 16,
        per_host: int = 8,
        timeout: int = 15,
        *,
        headers: dict | None = None,
        proxies: dict | None = None,
        retry_policy: RetryPolicy | None = None,
        throttler: AbstractThrottler | None = None,
        auto_throttle_target_concurrency: float = None,
        auto_throttle_start_delay: float = 0.25,
        auto_throttle_max_delay: float = 10.0,
        respect_robots: bool = True,
    ):
        self.concurrency = concurrency
        self._timeout = aiohttp.ClientTimeout(total=timeout)
        self._headers   = HEADERS | (headers or {}) # merge headers
        self._proxies = proxies if (isinstance(proxies, defaultdict) or proxies) else {}
        self.respect_robots = respect_robots

        self.retry_policy = retry_policy or RetryPolicy()
        self.throttler = throttler or AutoThrottler(
            target_concurrency=auto_throttle_target_concurrency or concurrency/4.0,
            start_delay=auto_throttle_start_delay,
            max_delay=auto_throttle_max_delay,
        )
        self._sem_global = asyncio.Semaphore(concurrency)
        self._sem_host = defaultdict(lambda: asyncio.Semaphore(per_host))

        self._pending: asyncio.Queue[Request] = asyncio.Queue()
        self._results: asyncio.Queue[Response] = asyncio.Queue()

        self._session: aiohttp.ClientSession | None = None
        self._workers: list[asyncio.Task] = []
        self._closed = False
        self._stats = CrawlerStats()
        self._robots_policy: RobotsTxtPolicy | None = None

    def build_session(self) -> aiohttp.ClientSession:
        """Construct an `aiohttp.ClientSession` with tracing and pooling."""
        trace_config = build_trace_config(self._stats)
        # Need to build the connector as late as possible as it requires the loop
        connector = aiohttp.TCPConnector(limit=self.concurrency*2, ttl_dns_cache=300)
        return aiohttp.ClientSession(
            headers=self._headers, 
            timeout=self._timeout, 
            connector=connector, 
            trace_configs=[trace_config]
        )

    async def __aenter__(self) -> "Crawler":
        """Initialize HTTP session and start background workers."""
        if self._session is None:
            # self._session = aiohttp.ClientSession(timeout=self._timeout)
            self._session = self.build_session()

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

    async def _worker(self) -> None:
        """Worker loop that fetches pending requests and enqueues results."""
        while True:
            req = await self._pending.get()
            try:
                resp = await self._fetch_one(req)
                if resp is not None:
                    await self._results.put(resp)

            except asyncio.CancelledError:
                # Must propagate cancellation
                log.debug("cancelled error", extra={"url": req.url})
                raise

            except gaierror:
                # Ignore DNS errors
                log.warning("DNS error", extra={"url": req.url})
                pass

            except Exception as exc:
                log.warning("exception", extra={"url": req.url})
                # Last-resort safety: never drop a request silently
                await self._results.put(Response(req, 0, b"", error=exc))
            finally:
                self._pending.task_done()

    async def _fetch_one(self, req: Request) -> Response | None:
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

            start = time.monotonic()
            try:
                async with self._session.get(
                    req.url,
                    headers=self._headers | req.headers,
                    proxy=self._proxy_for(req.url),
                    timeout=req.timeout or self._timeout,
                ) as resp:
                    body = await resp.read()

                    latency = time.monotonic() - start
                    self.throttler.record_latency(host, latency)

                    if self.retry_policy.should_retry(req, response=resp):
                        await self._retry(req)
                        return None

                    return Response(req, resp.status, body, dict(resp.headers))
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