# HTTP Module

> **Warning:** pre-1.0.0 - APIs and contracts may change.

The `wxpath.http` module provides the HTTP client infrastructure.

## Submodules

| Module | Description |
|--------|-------------|
| [crawler](crawler.md) | HTTP crawlers (`Crawler`, `BaseCrawler`, `PlaywrightCrawler`) |
| [TODO: stats](stats.md) | Crawler statistics |
| [TODO: policy/](policy/) | Retry, robots, throttling policies |

## Quick Import

```python
from wxpath.http.client import Crawler, Request, Response
from wxpath.http.client.cache import get_cache_backend
from wxpath.http.stats import CrawlerStats
```

## Architecture

```
                    ┌─────────────────┐
                    │   WXPathEngine  │<────────────────────┐
                    └────────┬────────┘                     │
                             │                              │  
                             ▼                              │
                    ┌─────────────────┐                     │      
                    │     Crawler     │                     │      
                    │  (BaseCrawler)  │                     │
                    └────────┬────────┘                     │
                             │                              │      
        ┌────────────────────┼────────────────────┐         │
        │                    │                    │         │
        ▼                    ▼                    ▼         │
 ┌─────────────┐     ┌─────────────┐     ┌─────────────┐    │
 │  Throttler  │     │ RobotsTxt   │     │ RetryPolicy │    │
 │             │     │   Policy    │     │             │    │
 └─────────────┘     └─────────────┘     └─────────────┘    │
        │                    │                    │         │
        └────────────────────┼────────────────────┘         │
                             │                              │
                             ▼                              │
                    ┌─────────────────┐                     │  
                    │ aiohttp Session │                     │
                    │   (+ cache)     │ ────> Response >────┘
                    └─────────────────┘
```

## Crawler Types

### Crawler (aiohttp)

Standard HTTP crawler using aiohttp. Best for most use cases.

```python
from wxpath.http.client import Crawler

crawler = Crawler(
    concurrency=16,
    per_host=4,
    respect_robots=True
)
```

MORE TO COME!

## Request/Response Flow

1. Engine submits `Request` to Crawler
2. Crawler checks robots.txt policy (if enabled)
3. Throttler delays request if needed (if enabled)
4. Request sent via aiohttp session
5. Response cached (if enabled)
6. `Response` returned to engine

## Concurrency Control

Two-level semaphore system:
- **Global semaphore**: Limits total concurrent requests
- **Per-host semaphores**: Limits concurrent requests per domain

```python
Crawler(
    concurrency=16,    # Global limit
    per_host=4         # Per-host limit
)
```
