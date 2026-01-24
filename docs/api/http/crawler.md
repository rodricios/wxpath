# Crawler

> **Warning:** pre-1.0.0 - APIs and contracts may change.

HTTP crawler classes for concurrent fetching.

## Location

```python
from wxpath.http.client import Crawler
from wxpath.http.client.crawler import (
    BaseCrawler,
    Crawler,
    PlaywrightCrawler,
    FlareSolverrCrawler,
    get_async_session
)
```

## Crawler

Standard aiohttp-based HTTP crawler.

```python
class Crawler:
    def __init__(
        self,
        concurrency: int = None,
        per_host: int = None,
        timeout: int = None,
        *,
        headers: dict | None = None,
        proxies: dict | None = None,
        retry_policy: RetryPolicy | None = None,
        throttler: AbstractThrottler | None = None,
        auto_throttle_target_concurrency: float = None,
        auto_throttle_start_delay: float = None,
        auto_throttle_max_delay: float = None,
        respect_robots: bool = True,
    )
```

### Parameters

| Name | Type | Default | Description |
|------|------|---------|-------------|
| `concurrency` | int | None | Global concurrent requests |
| `per_host` | int | None | Per-host concurrent requests |
| `timeout` | int | None | Request timeout in seconds |
| `headers` | dict | None | Default HTTP headers |
| `proxies` | dict | None | Per-host proxy mapping |
| `throttler` | AbstractThrottler | None | Request throttler |
| `auto_throttle_target_concurrency` | float | None | Auto-throttle target |
| `auto_throttle_start_delay` | float | None | Initial throttle delay |
| `auto_throttle_max_delay` | float | None | Maximum throttle delay |
| `respect_robots` | bool | True | Honor robots.txt |
| `retry_policy` | RetryPolicy | None | Retry configuration |

### Context Manager

```python
from wxpath.http.client import Crawler, Request

async with Crawler() as crawler:
    crawler.submit(Request("https://example.com"))
    async for response in crawler:
        print(response.status)
        print(response.body)
```

### Methods

#### submit

```python
def submit(self, req: Request) -> None
```

Queue a request for fetching.

**Parameters:**
- `req` - Request to queue

**Raises:** `RuntimeError` if crawler is closed

#### build_session

```python
def build_session(self) -> aiohttp.ClientSession
```

Construct an aiohttp session with tracing and connection pooling.

### Example

```python
from wxpath.http.client import Crawler, Request

async def main():
    crawler = Crawler(
        concurrency=8,
        per_host=2,
        headers={'User-Agent': 'my-bot/1.0'},
        respect_robots=True
    )

    urls = [
        "https://example.com/page1",
        "https://example.com/page2",
        "https://example.com/page3"
    ]

    responses = []
    async with crawler:
        for url in urls:
            crawler.submit(Request(url))

        async for resp in crawler:
            responses.append(resp)
            if len(responses) >= len(urls):
                break

    return responses
```
