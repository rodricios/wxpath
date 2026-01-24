# Examples

> **Warning:** pre-1.0.0 - APIs and contracts may change.

Practical examples demonstrating wxpath usage patterns.

## Basic Link Extraction

Extract all links from a page:

```python
import wxpath

expr = "url('https://example.com')//a/@href"

for link in wxpath.wxpath_async_blocking_iter(expr):
    print(link)
```

## Structured Data Extraction

Extract structured data using XPath 3.1 maps:

```python
import wxpath

expr = """
url('https://quotes.toscrape.com')
  //div[@class='quote']/map{
    'text': .//span[@class='text']/text(),
    'author': .//small[@class='author']/text(),
    'tags': .//a[@class='tag']/text()
  }
"""

for quote in wxpath.wxpath_async_blocking_iter(expr, max_depth=0):
    print(quote)
```

## Paginated Crawl

Follow pagination links:

```python
import wxpath

expr = """
url('https://quotes.toscrape.com')
  ///url(//li[@class='next']/a/@href)
    //div[@class='quote']//span[@class='text']/text()
"""

for quote in wxpath.wxpath_async_blocking_iter(expr, max_depth=10):
    print(quote)
```

## Wikipedia Knowledge Graph

Build a knowledge graph from Wikipedia:

```python
import wxpath
from wxpath.settings import CRAWLER_SETTINGS

CRAWLER_SETTINGS.headers = {
    'User-Agent': 'my-app/1.0 (contact: you@example.com)'
}

expr = """
url('https://en.wikipedia.org/wiki/Python_(programming_language)')
  ///url(
    //div[@id='mw-content-text']//a/@href[
      starts-with(., '/wiki/') and not(contains(., ':'))
    ]
  )
  /map{
    'title': (//h1/text())[1],
    'url': string(base-uri(.)),
    'summary': string((//div[contains(@class, 'mw-parser-output')]/p[1])[1]),
    'links': //div[@id='mw-content-text']//a/@href[starts-with(., '/wiki/')]
  }
"""

for item in wxpath.wxpath_async_blocking_iter(expr, max_depth=1):
    print(f"{item['title']}: {item['url']}")
```

## Custom Headers and Engine

Configure crawling behavior:

```python
from wxpath import wxpath_async_blocking_iter
from wxpath.core.runtime import WXPathEngine
from wxpath.http.client import Crawler

crawler = Crawler(
    concurrency=4,
    per_host=2,
    timeout=15,
    headers={
        'User-Agent': 'research-bot/1.0 (academic research)',
        'Accept-Language': 'en-US,en;q=0.9'
    },
    respect_robots=True
)

engine = WXPathEngine(crawler=crawler)

expr = "url('https://example.com')///url(//a/@href)//title/text()"

for title in wxpath_async_blocking_iter(expr, max_depth=2, engine=engine):
    print(title)
```

## Async Usage

Use with asyncio:

```python
import asyncio
from wxpath import wxpath_async

async def main():
    expr = "url('https://example.com')//a/@href"

    links = []
    async for link in wxpath_async(expr, max_depth=1):
        links.append(link)
        if len(links) >= 100:
            break

    return links

links = asyncio.run(main())
```

## Progress Bar

Display crawl progress:

```python
import wxpath

expr = """
url('https://quotes.toscrape.com')
  ///url(//li[@class='next']/a/@href)
    //div[@class='quote']/map{
      'text': .//span[@class='text']/text(),
      'author': .//small[@class='author']/text()
    }
"""

for quote in wxpath.wxpath_async_blocking_iter(expr, max_depth=5, progress=True):
    pass  # Progress bar shows crawl status
```

## Using Hooks

### Filter by Language

```python
from wxpath import hooks, wxpath_async_blocking_iter

@hooks.register
class OnlyEnglish:
    def post_parse(self, ctx, elem):
        lang = elem.xpath('string(/html/@lang)').lower()[:2]
        return elem if lang in ("en", "") else None

for item in wxpath_async_blocking_iter(expr, max_depth=1):
    print(item)  # Only English pages
```

### Log All URLs

```python
from wxpath import hooks

@hooks.register
class URLLogger:
    def post_fetch(self, ctx, html_bytes):
        print(f"Fetched: {ctx.url} (depth={ctx.depth})")
        return html_bytes
```

### Save Results to JSONL

```python
from wxpath import hooks, wxpath_async_blocking_iter

hooks.register(hooks.JSONLWriter("/output/results.jsonl"))

for item in wxpath_async_blocking_iter(expr, max_depth=1):
    pass  # Results automatically written to file
```

## Caching for Development

Enable caching to speed up development iteration:

```python
from wxpath.settings import CACHE_SETTINGS
from wxpath import wxpath_async_blocking_iter

CACHE_SETTINGS.enabled = True

# First run: fetches from network
results1 = list(wxpath_async_blocking_iter(expr, max_depth=1))

# Modify expression and run again - uses cached responses
expr2 = "url('https://example.com')//h1/text()"
results2 = list(wxpath_async_blocking_iter(expr2, max_depth=1))
```

## Error Handling

Handle errors in crawl results:

```python
from wxpath import wxpath_async_blocking_iter

for item in wxpath_async_blocking_iter(expr, max_depth=2, yield_errors=True):
    if isinstance(item, dict) and item.get('__type__') == 'error':
        print(f"Error: {item['url']} - {item['reason']}")
        continue

    process(item)
```

## CLI Examples

Basic extraction:

```bash
wxpath "url('https://example.com')//a/@href"
```

Deep crawl with filters:

```bash
wxpath --depth 2 \
    --header "User-Agent: my-bot/1.0" \
    "url('https://example.com')///url(//a/@href[contains(., '/docs/')])//h1/text()"
```

Save to file:

```bash
wxpath "url('https://example.com')//a/@href" > links.jsonl
```

With caching:

```bash
wxpath --cache --depth 3 "url('https://example.com')///url(//a/@href)//title/text()"
```
