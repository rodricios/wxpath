# Engine

> **Warning:** pre-1.0.0 - APIs and contracts may change.

This model defines the execution engine, which coordinates crawling and extraction. 

Runtime flow:

1. Parses wxpath expressions, retrieving an AST.
2. Processes the AST by dispatching to operation handlers.
3. Gather *processing tasks* internally known as "intents" from operation handlers. Depending on the intent, the engine may:
    1. *Crawl*, (`CrawlIntent`) by communicating to the Crawler by enqueuing CrawlTasks.
    2. *Extract*, (`ExtractIntent`) by dispatching to operation handlers that extract data.
    3. *Yield*, (`DataIntent`) by yielding data to the caller.
    4. *Process*, (`ProcessIntent`) by dispatching to operation handlers, effectively bridging XPath and wxpath expressions.
    5. *InfiniteCrawl*, (`InfiniteCrawlIntent`) by enqueuing infinite crawl tasks, which communicates to the engine that it should produce crawl intents AND process intents or extract intents or data intents.


This engine evolved from an earlier, monolithic `wxpath` engine that had the crawler tightly coupled to the engine. While coupling between the crawler and engine still exists, it does so in a much more modular way, by dispatching crawl tasks to the crawler's queue.

## Location

```python
from wxpath.core.runtime import WXPathEngine
from wxpath.core.runtime.engine import HookedEngineBase
```

## WXPathEngine

Main class for executing wxpath expressions.

```python
class WXPathEngine(HookedEngineBase):
    def __init__(
        self,
        crawler: Crawler | None = None,
        concurrency: int = 16,
        per_host: int = 8,
        respect_robots: bool = True,
        allowed_response_codes: set[int] = None,
        allow_redirects: bool = True
    )
```

### Parameters

| Name | Type | Default | Description |
|------|------|---------|-------------|
| `crawler` | Crawler | None | Pre-configured crawler instance |
| `concurrency` | int | 16 | Global concurrent fetches |
| `per_host` | int | 8 | Per-host concurrent fetches |
| `respect_robots` | bool | True | Honor robots.txt directives |
| `allowed_response_codes` | set[int] | {200} | Accepted HTTP status codes |
| `allow_redirects` | bool | True | Follow HTTP redirects |

### Attributes

| Name | Type | Description |
|------|------|-------------|
| `seen_urls` | set[str] | URLs already processed (deduplication) |
| `crawler` | Crawler | HTTP crawler instance |
| `allowed_response_codes` | set[int] | Accepted status codes |
| `allow_redirects` | bool | Redirect following enabled |

### Methods

#### run

```python
async def run(
    self,
    expression: str,
    max_depth: int,
    progress: bool = False,
    yield_errors: bool = False
) -> AsyncGenerator[Any, None]
```

Execute a wxpath expression concurrently and yield results.

**Parameters:**

| Name | Type | Description |
|------|------|-------------|
| `expression` | str | wxpath expression to evaluate |
| `max_depth` | int | Maximum crawl depth |
| `progress` | bool | Show tqdm progress bar |
| `yield_errors` | bool | Yield error dicts for failed requests |

**Yields:** Extracted values (HtmlElement, WxStr, dict, etc.)

### Example

```python
import asyncio
from wxpath.core.runtime import WXPathEngine
from wxpath.http.client import Crawler

crawler = Crawler(
    concurrency=8,
    per_host=2,
    headers={'User-Agent': 'my-bot/1.0'}
)

engine = WXPathEngine(
    crawler=crawler,
    allowed_response_codes={200, 301, 302}
)

async def main():
    async for item in engine.run("url('https://example.com')//a/@href", max_depth=1):
        print(item)

asyncio.run(main())
```

## HookedEngineBase

Base class providing hook invocation methods.

```python
class HookedEngineBase:
    async def post_fetch_hooks(
        self, body: bytes | str, task: CrawlTask
    ) -> bytes | str | None

    async def post_parse_hooks(
        self, elem: HtmlElement | None, task: CrawlTask
    ) -> HtmlElement | None

    async def post_extract_hooks(
        self, value: Any
    ) -> Any | None
```

### Hook Methods

#### post_fetch_hooks

Run registered `post_fetch` hooks over a fetched response body.

**Parameters:**
- `body` - Raw response body bytes
- `task` - The CrawlTask that produced the response

**Returns:** Transformed body, or `None` if dropped

#### post_parse_hooks

Run registered `post_parse` hooks on a parsed DOM element.

**Parameters:**
- `elem` - Parsed lxml element
- `task` - The originating CrawlTask

**Returns:** Transformed element, or `None` if dropped

#### post_extract_hooks

Run registered `post_extract` hooks on extracted values.

**Parameters:**
- `value` - The extracted datum

**Returns:** Transformed value, or `None` if dropped

## Execution Flow

With the above Hooks system, wxpath's execution flow is as follows:

1. Parse expression into segments
2. Create seed task with initial URL(s)
3. Process tasks via BFS queue:
   - Fetch URL
   - Run post_fetch hooks
   - Parse HTML
   - Run post_parse hooks
   - Execute remaining segments
   - Emit intents (crawl, extract, data)
4. Yield extracted data through post_extract hooks
5. Continue until queue exhausted or max_depth reached
