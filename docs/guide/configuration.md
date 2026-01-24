# Configuration

> **Warning:** pre-1.0.0 - APIs and contracts may change.

wxpath provides hierarchical configuration through the `SETTINGS` object.

## Settings Structure

```python
from wxpath.settings import SETTINGS, CRAWLER_SETTINGS, CACHE_SETTINGS
```

### Crawler Settings

Access via `CRAWLER_SETTINGS` or `SETTINGS.http.client.crawler`:

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `concurrency` | int | 16 | Global concurrent requests |
| `per_host` | int | 8 | Per-host concurrent requests |
| `timeout` | int | 15 | Request timeout in seconds |
| `headers` | dict | `{...}` | Default HTTP headers |
| `proxies` | dict | `None` | Per-host proxy mapping |
| `respect_robots` | bool | `True` | Honor robots.txt |
| `auto_throttle_target_concurrency` | float | `None` | Target concurrent requests for throttler |
| `auto_throttle_start_delay` | float | 0.25 | Initial throttle delay |
| `auto_throttle_max_delay` | float | 10.0 | Maximum throttle delay |

### Cache Settings

Access via `CACHE_SETTINGS` or `SETTINGS.http.client.cache`:

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `enabled` | bool | `False` | Enable response caching |
| `expire_after` | timedelta | `timedelta(days=7)` | Cache TTL in seconds |
| `allowed_methods` | tuple | ("GET", "HEAD") | HTTP methods to cache |
| `allowed_codes` | tuple | (200, 203, 301, 302, 307, 308) | Status codes to cache |
| `ignored_params` | list | ["utm_*", "fbclid"] | Query params to ignore in cache key |
| `backend` | str | "sqlite" | Cache backend ("sqlite" or "redis") |
| `sqlite` | dict | `{...}` | SQLite backend settings |
| `redis` | dict | `{...}` | Redis backend settings |


For SQLite backend:

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `cache_name` | str | "cache.db" | SQLite cache name |

For Redis backend:

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `redis.address` | str | "redis://localhost:6379/0" | Redis connection URL |
| `cache_name` | str | "wxpath:" | Redis cache name |

## Configuration Examples

### Setting Headers

```python
from wxpath.settings import CRAWLER_SETTINGS

CRAWLER_SETTINGS.headers = {
    'User-Agent': 'my-crawler/1.0 (contact: you@example.com)',
    'Accept-Language': 'en-US,en;q=0.9'
}
```

### Enabling Caching

```python
from wxpath.settings import CACHE_SETTINGS

# SQLite backend (default)
CACHE_SETTINGS.enabled = True

# Redis backend
CACHE_SETTINGS.enabled = True
CACHE_SETTINGS.backend = "redis"
CACHE_SETTINGS.redis.address = "redis://localhost:6379/0"
```

### Custom Concurrency

```python
from wxpath.settings import CRAWLER_SETTINGS

CRAWLER_SETTINGS.concurrency = 32
CRAWLER_SETTINGS.per_host = 4
```

### Proxy Configuration

```python
from wxpath.settings import CRAWLER_SETTINGS
from collections import defaultdict

# Per-host proxies
CRAWLER_SETTINGS.proxies = {
    'example.com': 'http://proxy1:8080',
    'api.example.com': 'http://proxy2:8080'
}

# Default proxy for all hosts
CRAWLER_SETTINGS.proxies = defaultdict(lambda: 'http://default-proxy:8080')
```

## Engine Configuration

For fine-grained control, configure the engine and crawler directly:

```python
from wxpath import wxpath_async_blocking_iter
from wxpath.core.runtime import WXPathEngine
from wxpath.http.client import Crawler
from wxpath.http.policy.retry import RetryPolicy
from wxpath.http.policy.throttler import AutoThrottler
from wxpath.settings import CRAWLER_SETTINGS

CRAWLER_SETTINGS.headers = {'User-Agent': 'my-app/0.4.0 (contact: you@example.com)'}

# Custom retry policy
retry_policy = RetryPolicy(
    max_retries=3,
    retry_statuses={500, 502, 503, 504}
)

# Custom throttler
throttler = AutoThrottler(
    target_concurrency=2.0,
    start_delay=1.0,
    max_delay=30.0
)

# Create crawler
crawler = Crawler(
    concurrency=8,
    per_host=2,
    timeout=15,
    headers={'User-Agent': 'my-app/1.0'},
    retry_policy=retry_policy,
    throttler=throttler,
    respect_robots=True
)

# Create engine
engine = WXPathEngine(
    crawler=crawler,
    allowed_response_codes={200, 301, 302},
    allow_redirects=True
)

path_expr = """
url('https://quotes.toscrape.com/tag/humor/', follow=//li[@class='next']/a/@href)
  //div[@class='quote']
    /map{
      'author': (./span/small/text())[1],
      'text': (./span[@class='text']/text())[1]
      }
"""

# Use engine
for item in wxpath_async_blocking_iter(path_expr, max_depth=1, engine=engine):
    print(item)
```

## AttrDict

Settings use `AttrDict` for dot-notation access:

```python
from wxpath.settings import SETTINGS

# Both work
SETTINGS['http']['client']['crawler']['concurrency']
SETTINGS.http.client.crawler.concurrency
```
