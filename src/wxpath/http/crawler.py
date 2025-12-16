import asyncio, aiohttp, urllib.parse
from functools import partial
from collections import defaultdict
from typing import Iterable, Callable, Awaitable

from wxpath.util.logging import get_logger
from wxpath.http.stats import build_stats, build_trace_config


log = get_logger(__name__)

HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36"}

class Crawler:
    def __init__(
        self,
        concurrency: int = 16,
        # per_host: int = 4,
        timeout: int = 15,
        delay: float = 0,
        *,
        headers: dict[str, str] | None = None,
        proxies: dict[str, str] | None = None,
    ):
        self.concurrency = concurrency
        self._sem_global = asyncio.Semaphore(concurrency)
        # self._sem_host  = defaultdict(lambda: asyncio.Semaphore(per_host))
        self._timeout   = aiohttp.ClientTimeout(total=timeout)
        self._connector = aiohttp.TCPConnector(limit=self.concurrency*2, ttl_dns_cache=300)
        self._delay     = delay
        self._headers   = HEADERS | (headers or {}) # merge headers
        self._proxies   = proxies or {}
        self._session: aiohttp.ClientSession | None = None
        self._stats = build_stats()

    def build_session(self):
        trace_config = build_trace_config(self._stats)
        return aiohttp.ClientSession(
            headers=self._headers, 
            timeout=self.timeout, 
            connector=self._connector, 
            trace_configs=[trace_config]
        )


    async def __aenter__(self):
        # self._session = aiohttp.ClientSession(
        #     headers=self._headers,
        #     # timeout=self._timeout,
        # )
        self._session = self.build_session()
        return self

    async def __aexit__(self, exc_type, exc, tb):
        if self._session is not None:
            await self._session.close()
            self._session = None

    def _proxy_for(self, url: str) -> str | None:                 
        host = urllib.parse.urlsplit(url).hostname
        return self._proxies.get(host)

    async def _fetch(
        self,
        url: str,
        cb: Callable[[str, aiohttp.ClientResponse, bytes], Awaitable[None]],
        session: aiohttp.ClientSession,
    ):
        host = urllib.parse.urlsplit(url).hostname
        async with self._sem_global: #, self._sem_host[host]:
            if self._delay:
                await asyncio.sleep(self._delay)

            try:
                async with session.get(
                    url,
                    proxy=self._proxy_for(url),                
                ) as resp:
                    body = await resp.read()
                    await cb(url, resp, body)
            except Exception as exc:
                # TODO: adhere to ErrorPolicy?
                log.exception(f"[REQUEST ERROR] {url}")

    async def _run(
        self,
        urls: Iterable[str],
        cb: Callable[[str, aiohttp.ClientResponse, bytes], Awaitable[None]],
    ):
        if self._session is not None:
            # Reuse the persistent session created by __aenter__
            await asyncio.gather(*(self._fetch(u, cb, self._session) for u in urls))
        else:
            # Fallback: ephemeral session for one-off runs
            async with self.build_session() as s:
                await asyncio.gather(*(self._fetch(u, cb, s) for u in urls))

    async def run_async(
        self,
        urls: Iterable[str],
        cb: Callable[[str, aiohttp.ClientResponse, bytes], Awaitable[None]]
    ):
        if not asyncio.iscoroutinefunction(cb):
            async def _wrap(url, r, b): return cb(url, r, b)
            cb = _wrap
        await self._run(urls, cb)

    def run(
        self,
        urls: Iterable[str],
        cb: Callable[[str, aiohttp.ClientResponse, bytes], Awaitable[None]]
             | Callable[[str, aiohttp.ClientResponse, bytes], None],
    ):
        asyncio.run(self.run_async(urls, cb))
