# Getting Started

> **Warning:** pre-1.0.0 - APIs and contracts may change.

## Installation

### Basic Installation

```bash
pip install wxpath
```

Requires Python 3.10+.

### Optional Dependencies

For response caching:

```bash
# SQLite backend (good for single-worker crawls)
pip install wxpath[cache-sqlite]

# Redis backend (recommended for concurrent crawls)
pip install wxpath[cache-redis]
```

## Your First Crawl

### Simple Link Extraction

```python
import wxpath

# Extract all links from a page
expr = "url('https://quotes.toscrape.com')//a/@href"

for link in wxpath.wxpath_async_blocking_iter(expr):
    print(link)
```

### Using Async API

```python
import asyncio
from wxpath import wxpath_async

async def main():
    expr = "url('https://quotes.toscrape.com')//a/@href"
    async for item in wxpath_async(expr, max_depth=1):
        print(item)

asyncio.run(main())
```

## Understanding wxpath Expressions

A wxpath expression consists of segments that describe:

1. **What to fetch** - `url(...)` segments
2. **What to follow** - `///url(...)` for recursive crawling
3. **What to extract** - XPath expressions

### Example: Multi-level Crawl

```python
path_expr = """
url('https://quotes.toscrape.com')
  ///url(//a/@href)
    //span[@class='text']/text()
"""

for quote in wxpath.wxpath_async_blocking_iter(path_expr, max_depth=2):
    print(quote)
```

### Example: Structured Data Extraction

```python
from wxpath.settings import CRAWLER_SETTINGS

# Custom headers for politeness; necessary for some sites (e.g., Wikipedia)
CRAWLER_SETTINGS.headers = {'User-Agent': 'my-app/0.4.0 (contact: you@example.com)'}

path_expr = """
url('https://en.wikipedia.org/wiki/Python_(programming_language)')
  /map{
    'title': (//h1//text())[1] ! normalize-space(.),
    'mainText': //div[contains(@class, 'mw-parser-output')]/string-join(//p) ! normalize-space(.),
    'url': string(base-uri(.))
  }
"""

for item in wxpath.wxpath_async_blocking_iter(path_expr, max_depth=0):
    print(item)
```

## Configuration

### Custom Headers

Many websites require proper User-Agent headers:

```python
from wxpath.settings import CRAWLER_SETTINGS

CRAWLER_SETTINGS.headers = {
    'User-Agent': 'my-crawler/1.0 (contact: you@example.com)'
}
```

### Engine Configuration

```python
from wxpath import wxpath_async_blocking_iter
from wxpath.core.runtime import WXPathEngine
from wxpath.http.client import Crawler

crawler = Crawler(
    concurrency=8,
    per_host=2,
    timeout=10,
    respect_robots=True,
    headers={'User-Agent': 'my-app/0.1.0'}
)

engine = WXPathEngine(crawler=crawler)

items = list(wxpath_async_blocking_iter(
    "url('https://quotes.toscrape.com')//a/@href",
    max_depth=1,
    engine=engine
))
```

## Next Steps

- [Language Design](guide/language-design.md) - Deep dive into expression syntax
- [Configuration](guide/configuration.md) - All configuration options
- [Hooks](guide/hooks.md) - Extending wxpath with custom hooks
- [CLI](guide/cli.md) - Command-line interface usage
