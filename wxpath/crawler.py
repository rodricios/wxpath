import asyncio, aiohttp, time, urllib.parse
from collections import defaultdict
from typing import Iterable, Callable, Awaitable

class Crawler:
    def __init__(
        self,
        concurrency: int = 16,
        per_host: int = 4,
        timeout: int = 15,
        delay: float = 0,
        *,
        headers: dict[str, str] | None = None,
        proxies: dict[str, str] | None = None,
    ):
        self._sem_global = asyncio.Semaphore(concurrency)
        self._sem_host  = defaultdict(lambda: asyncio.Semaphore(per_host))
        self._timeout   = aiohttp.ClientTimeout(total=timeout)
        self._delay     = delay
        self._headers   = {"User-Agent": "mini-crawler"} | (headers or {})  # merge
        self._proxies   = proxies or {}

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
        async with self._sem_global, self._sem_host[host]:
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
                print(f"[ERR] {url} – {exc}")

    async def _run(
        self,
        urls: Iterable[str],
        cb: Callable[[str, aiohttp.ClientResponse, bytes], Awaitable[None]],
    ):
        async with aiohttp.ClientSession(
            headers=self._headers,
            timeout=self._timeout,
        ) as s:
            await asyncio.gather(*(self._fetch(u, cb, s) for u in urls))

    def run(
        self,
        urls: Iterable[str],
        cb: Callable[[str, aiohttp.ClientResponse, bytes], Awaitable[None]]
             | Callable[[str, aiohttp.ClientResponse, bytes], None],
    ):
        if not asyncio.iscoroutinefunction(cb):
            async def _wrap(url, r, b): return cb(url, r, b)
            cb = _wrap

        asyncio.run(self._run(urls, cb))