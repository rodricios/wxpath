# API Reference

> **Warning:** pre-1.0.0 - APIs and contracts may change.

## Top-Level API

The `wxpath` package exports these primary functions:

```python
from wxpath import (
    wxpath_async,
    wxpath_async_blocking,
    wxpath_async_blocking_iter,
    configure_logging
)
```

### wxpath_async

```python
async def wxpath_async(
    path_expr: str,
    max_depth: int,
    progress: bool = False,
    engine: WXPathEngine | None = None,
    yield_errors: bool = False
) -> AsyncGenerator[Any, None]
```

Async generator that evaluates a wxpath expression and yields results.

**Parameters:**

| Name | Type | Description |
|------|------|-------------|
| `path_expr` | str | wxpath expression to evaluate |
| `max_depth` | int | Maximum crawl depth for `url` hops |
| `progress` | bool | Display tqdm progress bar |
| `engine` | WXPathEngine | Pre-configured engine instance |
| `yield_errors` | bool | Yield error dicts instead of silently skipping |

**Yields:** Extracted values (HtmlElement, WxStr, dict, etc.)

### wxpath_async_blocking_iter

```python
def wxpath_async_blocking_iter(
    path_expr: str,
    max_depth: int = 1,
    progress: bool = False,
    engine: WXPathEngine | None = None,
    yield_errors: bool = False
) -> Iterator[Any]
```

Synchronous iterator wrapper around `wxpath_async`. Creates its own event loop.

> **Warning:** Must not be called from within an active asyncio event loop.

**Parameters:** Same as `wxpath_async`

**Yields:** Extracted values

### wxpath_async_blocking

```python
def wxpath_async_blocking(
    path_expr: str,
    max_depth: int = 1,
    progress: bool = False,
    engine: WXPathEngine | None = None,
    yield_errors: bool = False
) -> list[Any]
```

Synchronous function that returns all results as a list.

**Parameters:** Same as `wxpath_async`

**Returns:** List of all extracted values

### configure_logging

```python
def configure_logging(level: int = logging.INFO) -> None
```

Configure wxpath's logging system.

**Parameters:**

| Name | Type | Default | Description |
|------|------|---------|-------------|
| `level` | (int | str) | logging.INFO | Logging level |


## Module Index

### Core

- [Engine](core/engine.md) - Main execution engine (`WXPathEngine`)
- TODO: Parser - Expression parser and AST nodes
- TODO: Models - Data models (CrawlTask, intents)
- [Operations](core/ops.md) - Operation handlers and registry

### HTTP

- [Crawler](http/crawler.md) - HTTP client (`Crawler`, `BaseCrawler`)

- TODO: Cache - Cache backend factory
- TODO: Policy - Retry, robots, throttling policies
- TODO: Stats - Crawler statistics

### Hooks

- TODO: Registry - Hook registration and protocol
- TODO: Built-in Hooks - Predefined hooks

### Utilities

- TODO: Logging - Logging configuration
- TODO: Serialize - Type simplification

### Configuration

- [Settings](settings.md) - Global settings (`SETTINGS`, `CRAWLER_SETTINGS`, `CACHE_SETTINGS`)
