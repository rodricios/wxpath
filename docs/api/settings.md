# Settings

> **Warning:** pre-1.0.0 - APIs and contracts may change.

Global configuration for wxpath.

## Location

```python
from wxpath.settings import SETTINGS, CRAWLER_SETTINGS, CACHE_SETTINGS, AttrDict
```

## SETTINGS

Root settings object containing all configuration. The SETTINGS dict hierarchy follows the hierarchy of wxpath submodules.

```python
SETTINGS = AttrDict({
    "http": {
        "client": {
            "cache": { ... },
            "crawler": { ... }
        }
    }
})
```

## CRAWLER_SETTINGS

Shortcut to `SETTINGS.http.client.crawler`.

```python
from wxpath.settings import CRAWLER_SETTINGS

CRAWLER_SETTINGS.concurrency = 16
CRAWLER_SETTINGS.headers = {"User-Agent": "my-bot/1.0"}
```

### Fields

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

## CACHE_SETTINGS

Shortcut to `SETTINGS.http.client.cache`.

```python
from wxpath.settings import CACHE_SETTINGS

CACHE_SETTINGS.enabled = True
CACHE_SETTINGS.backend = "redis"
```

### Fields

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

### SQLite Settings

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `cache_name` | str | "cache.db" | SQLite cache name |


### Redis Settings

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `redis.address` | str | "redis://localhost:6379/0" | Redis connection URL |
| `cache_name` | str | "wxpath:" | Redis cache name |

## AttrDict

Dictionary subclass enabling dot-notation access.

```python
class AttrDict(dict):
    def __getattr__(self, name): ...
    def __setattr__(self, name, value): ...
```

### Usage

```python
from wxpath.settings import AttrDict

config = AttrDict({
    "database": {
        "host": "localhost",
        "port": 5432
    }
})

# Both work
config["database"]["host"]
config.database.host

# Setting values
config.database.port = 5433
```

## Configuration Examples

### Basic Setup

```python
from wxpath.settings import CRAWLER_SETTINGS, CACHE_SETTINGS

# Crawler config
CRAWLER_SETTINGS.concurrency = 8
CRAWLER_SETTINGS.per_host = 2
CRAWLER_SETTINGS.headers = {
    "User-Agent": "my-crawler/1.0 (contact: me@example.com)"
}

# Enable caching
CACHE_SETTINGS.enabled = True
```

### Full Configuration

```python
from wxpath.settings import SETTINGS

# Access nested settings
SETTINGS.http.client.crawler.concurrency = 16
SETTINGS.http.client.crawler.timeout = 60

SETTINGS.http.client.cache.enabled = True
SETTINGS.http.client.cache.backend = "redis"
SETTINGS.http.client.cache.redis.address = "redis://cache.local:6379/0"
```

### Proxy Configuration

```python
from wxpath.settings import CRAWLER_SETTINGS
from collections import defaultdict

# Per-host proxies
CRAWLER_SETTINGS.proxies = {
    "example.com": "http://proxy1:8080",
    "api.example.com": "http://proxy2:8080"
}

# Default proxy for all hosts
CRAWLER_SETTINGS.proxies = defaultdict(lambda: "http://default:8080")
```

## Settings Precedence

1. Constructor arguments (highest priority)
2. Settings object modifications
3. Default values (lowest priority)

```python
from wxpath.http.client import Crawler
from wxpath.settings import CRAWLER_SETTINGS

CRAWLER_SETTINGS.concurrency = 8  # Setting

# Constructor overrides settings
crawler = Crawler(concurrency=4)  # Uses 4, not 8
```
