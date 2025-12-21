import asyncio
import aiohttp
import time
import urllib.parse
from collections import defaultdict
from typing import AsyncIterator

from wxpath.http.client.request import Request
from wxpath.http.client.response import Response
from wxpath.http.policy.retry import RetryPolicy
from wxpath.http.policy.throttler import AbstractThrottler, AutoThrottler
from wxpath.util.logging import get_logger
from wxpath.http.stats import CrawlerStats, build_trace_config


log = get_logger(__name__)

HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36"}

class Crawler:
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
    ):
        self.concurrency = concurrency
        self._timeout = aiohttp.ClientTimeout(total=timeout)
        self._headers   = HEADERS | (headers or {}) # merge headers
        self._proxies = proxies or {}

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

    def build_session(self):
        trace_config = build_trace_config(self._stats)
        # Need to build the connector as late as possible as it requires the loop
        connector = aiohttp.TCPConnector(limit=self.concurrency*2, ttl_dns_cache=300)
        return aiohttp.ClientSession(
            headers=self._headers, 
            timeout=self._timeout, 
            connector=connector, 
            trace_configs=[trace_config]
        )

    async def __aenter__(self):
        if self._session is None:
            # self._session = aiohttp.ClientSession(timeout=self._timeout)
            self._session = self.build_session()

        self._workers = [
            asyncio.create_task(self._worker(), name=f"crawler-worker-{i}")
            for i in range(self.concurrency)
        ]
        return self

    async def __aexit__(self, *_):
        self._closed = True
        for w in self._workers:
            w.cancel()
        await asyncio.gather(*self._workers, return_exceptions=True)
        if self._session:
            await self._session.close()

    def submit(self, req: Request):
        if self._closed:
            raise RuntimeError("crawler is closed")
        self._pending.put_nowait(req)

    async def finish(self):
        """
        Wait for all pending requests to be processed and mark crawler done.
        """
        await self._pending.join()  # wait for queue
        self._closed = True

    def __aiter__(self) -> AsyncIterator[Response]:
        return self._result_iter()

    async def _result_iter(self):
        # while not self._closed:
        while not (self._closed and self._results.empty()):
            resp = await self._results.get()
            yield resp

    def _proxy_for(self, url: str):
        host = urllib.parse.urlsplit(url).hostname
        return self._proxies.get(host)

    async def _worker(self):
        while True:
            req = await self._pending.get()
            try:
                resp = await self._fetch_one(req)
                if resp is not None:
                    await self._results.put(resp)
            finally:
                self._pending.task_done()

    async def _fetch_one(self, req: Request) -> Response | None:
        host = req.hostname

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

            except Exception as exc:
                latency = time.monotonic() - start
                self.throttler.record_latency(host, latency)

                if self.retry_policy.should_retry(req, exception=exc):
                    await self._retry(req)
                    return None
                raise

    async def _retry(self, req: Request):
        req.retries += 1
        delay = self.retry_policy.get_delay(req)

        log.warning(
            "retrying",
            extra={"url": req.url, "retry": req.retries, "delay": delay},
        )

        if delay:
            await asyncio.sleep(delay)

        self.submit(req)