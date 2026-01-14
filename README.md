# **wxpath** - declarative web crawling with XPath 

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/release/python-3100/)

**wxpath** is a declarative web crawler where traversal is expressed directly in XPath. Instead of writing imperative crawl loops, wxpath lets you describe what to follow and what to extract in a single expression. **wxpath** executes that expression concurrently, breadth-first-*ish*, and streams results as they are discovered.

By introducing the `url(...)` operator and the `///` syntax, wxpath's engine is able to perform deep (or paginated) web crawling and extraction.

NOTE: This project is in early development. Core concepts are stable, but the API and features may change. Please report issues - in particular, deadlocked crawls or unexpected behavior - and any features you'd like to see (no guarantee they'll be implemented).


## Contents

- [Example](#example)
- [Language Design](DESIGN.md)
- [`url(...)` and `///url(...)` Explained](#url-and-url-explained)
- [General flow](#general-flow)
- [Asynchronous Crawling](#asynchronous-crawling)
- [Polite Crawling](#polite-crawling)
- [Output types](#output-types)
- [XPath 3.1](#xpath-31-by-default)
- [CLI](#cli)
- [Hooks (Experimental)](#hooks-experimental)
- [Install](#install)
- [More Examples](EXAMPLES.md)
- [Comparisons](#comparisons)
- [Advanced: Engine & Crawler Configuration](#advanced-engine--crawler-configuration)
- [Project Philosophy](#project-philosophy)
- [Warnings](#warnings)
- [Commercial support / consulting](#commercial-support--consulting)
- [License](#license)


## Example

```python
import wxpath

# Crawl, extract fields, build a knowledge graph
path_expr = """
url('https://en.wikipedia.org/wiki/Expression_language')
 ///url(//main//a/@href[starts-with(., '/wiki/') and not(contains(., ':'))])
 /map{
    'title': (//span[contains(@class, "mw-page-title-main")]/text())[1] ! string(.),
    'url': string(base-uri(.)),
    'short_description': //div[contains(@class, 'shortdescription')]/text() ! string(.),
    'forward_links': //div[@id="mw-content-text"]//a/@href ! string(.)
 }
"""

for item in wxpath.wxpath_async_blocking_iter(path_expr, max_depth=1):
    print(item)
```

Output:

```python
map{'title': 'Computer language', 'url': 'https://en.wikipedia.org/wiki/Computer_language', 'short_description': 'Formal language for communicating with a computer', 'forward_links': ['/wiki/Formal_language', '/wiki/Communication', ...]}
map{'title': 'Advanced Boolean Expression Language', 'url': 'https://en.wikipedia.org/wiki/Advanced_Boolean_Expression_Language', 'short_description': 'Hardware description language and software', 'forward_links': ['/wiki/File:ABEL_HDL_example_SN74162.png', '/wiki/Hardware_description_language', ...]}
map{'title': 'Machine-readable medium and data', 'url': 'https://en.wikipedia.org/wiki/Machine_readable', 'short_description': 'Medium capable of storing data in a format readable by a machine', 'forward_links': ['/wiki/File:EAN-13-ISBN-13.svg', '/wiki/ISBN', ...]}
...
```

**Note:** Some sites (including Wikipedia) may block requests without proper headers.  
See [Advanced: Engine & Crawler Configuration](#advanced-engine--crawler-configuration) to set a custom `User-Agent`.


The above expression does the following:

1. Starts at the specified URL, `https://en.wikipedia.org/wiki/Expression_language`.
2. Filters for links in the `<main>` section that start with `/wiki/` and do not contain a colon (`:`).
3. For each link found, 
    * it follows the link and extracts the title, URL, and short description of the page.
    * it repeats step 2 until the maximum depth is reached.
4. Streams the extracted data as it is discovered.


## `url(...)` and `///url(...)` Explained

- `url(...)` is a custom operator that fetches the content of the user-specified or internally generated URL and returns it as an `lxml.html.HtmlElement` for further XPath processing.
- `///url(...)` indicates a deep crawl. It tells the runtime engine to continue following links up to the specified `max_depth`. Unlike repeated `url()` hops, it allows a single expression to describe deeper graph exploration. WARNING: Use with caution and constraints (via `max_depth` or XPath predicates) to avoid traversal explosion.


## Language Design

See [DESIGN.md](DESIGN.md) for details of the language design. You will see the core concepts and design the language from the ground up.


## General flow

**wxpath** evaluates an expression as a list of traversal and extraction steps (internally referred to as `Segment`s).

`url(...)` creates crawl tasks either statically (via a fixed URL) or dynamically (via a URL derived from the XPath expression). **URLs are deduplicated globally, on a best-effort basis - not per-depth**.

XPath segments operate on fetched documents (fetched via the immediately preceding `url(...)` operations).

`///url(...)` indicates deep crawling - it proceeds breadth-first-*ish* up to `max_depth`.

Results are yielded as soon as they are ready.


## Asynchronous Crawling

**wxpath** is `asyncio/aiohttp`-first, providing an asynchronous API for crawling and extracting data.

```python
import asyncio
from wxpath import wxpath_async

items = []

async def main():
    path_expr = "url('https://en.wikipedia.org/wiki/Expression_language')///url(//@href[starts-with(., '/wiki/')])//a/@href"
    async for item in wxpath_async(path_expr, max_depth=1):
        items.append(item)

asyncio.run(main())
```

### Blocking, Concurrent Requests

**wxpath** also provides an asyncio-in-sync API, allowing you to crawl multiple pages concurrently while maintaining the simplicity of synchronous code. This is particularly useful for crawls in strictly synchronous execution environments (i.e., not inside an `asyncio` event loop) where performance is a concern.

```python
from wxpath import wxpath_async_blocking_iter

path_expr = "url('https://en.wikipedia.org/wiki/Expression_language')///url(//@href[starts-with(., '/wiki/')])//a/@href"
items = list(wxpath_async_blocking_iter(path_expr, max_depth=1))
```

## Polite Crawling

**wxpath** respects [robots.txt](https://en.wikipedia.org/wiki/Robots_exclusion_standard) by default via the `WXPathEngine(..., robotstxt=True)` constructor.


## Output types

The wxpath Python API yields structured objects.

Depending on the expression, results may include:

- `lxml.*` and `lxml.html.*` objects
- `elementpath.datatypes.*` objects (for XPath 3.1 features)
- `WxStr` (string values with provenance)
- dictionaries / maps
- lists or other XPath-native values

The CLI flattens these objects into plain JSON for display.
The Python API preserves structure by default.


## XPath 3.1 By Default

**wxpath** uses the `elementpath` library to provide XPath 3.1 support, enabling advanced XPath features like **maps**, **arrays**, and more. This allows you to write more powerful XPath queries.

```python
path_expr = """
    url('https://en.wikipedia.org/wiki/Expression_language')
    ///url(//div[@id='mw-content-text']//a/@href)
    /map{ 
        'title':(//span[contains(@class, "mw-page-title-main")]/text())[1], 
        'short_description':(//div[contains(@class, "shortdescription")]/text())[1],
        'url'://link[@rel='canonical']/@href[1]
    }
"""
# [...
# {'title': 'Computer language',
# 'short_description': 'Formal language for communicating with a computer',
# 'url': 'https://en.wikipedia.org/wiki/Computer_language'},
# {'title': 'Machine-readable medium and data',
# 'short_description': 'Medium capable of storing data in a format readable by a machine',
# 'url': 'https://en.wikipedia.org/wiki/Machine-readable_medium_and_data'},
# {'title': 'Domain knowledge',
# 'short_description': 'Specialist knowledge within a specific field',
# 'url': 'https://en.wikipedia.org/wiki/Domain_knowledge'},
# ...]
```


## CLI

**wxpath** provides a command-line interface (CLI) to quickly experiment and execute wxpath expressions directly from the terminal. 

The following example demonstrates how to crawl Wikipedia starting from the "Expression language" page, extract links to other wiki pages, and retrieve specific fields from each linked page.

NOTE: Due to the everchanging nature of web content, the output may vary over time.
```bash
> wxpath --depth 1 \
    --header "User-Agent: my-app/0.1 (contact: you@example.com)" \
    "url('https://en.wikipedia.org/wiki/Expression_language') \
    ///url(//div[@id='mw-content-text']//a/@href[starts-with(., '/wiki/') \
        and not(matches(@href, '^(?:/wiki/)?(?:Wikipedia|File|Template|Special|Template_talk|Help):'))]) \
    /map{ \
        'title':(//span[contains(@class, 'mw-page-title-main')]/text())[1], \
        'short_description':(//div[contains(@class, 'shortdescription')]/text())[1], \
        'url':string(base-uri(.)), \
        'backlink':wx:backlink(.), \
        'depth':wx:depth(.) \
        }"

{"title": "Computer language", "short_description": "Formal language for communicating with a computer", "url": "https://en.wikipedia.org/wiki/Computer_language", "backlink": "https://en.wikipedia.org/wiki/Expression_language", "depth": 1.0}
{"title": "Machine-readable medium and data", "short_description": "Medium capable of storing data in a format readable by a machine", "url": "https://en.wikipedia.org/wiki/Machine_readable", "backlink": "https://en.wikipedia.org/wiki/Expression_language", "depth": 1.0}
{"title": "Domain knowledge", "short_description": "Specialist knowledge within a specific field", "url": "https://en.wikipedia.org/wiki/Domain_knowledge", "backlink": "https://en.wikipedia.org/wiki/Expression_language", "depth": 1.0}
{"title": "Advanced Boolean Expression Language", "short_description": "Hardware description language and software", "url": "https://en.wikipedia.org/wiki/Advanced_Boolean_Expression_Language", "backlink": "https://en.wikipedia.org/wiki/Expression_language", "depth": 1.0}
{"title": "Data Analysis Expressions", "short_description": "Formula and data query language", "url": "https://en.wikipedia.org/wiki/Data_Analysis_Expressions", "backlink": "https://en.wikipedia.org/wiki/Expression_language", "depth": 1.0}
{"title": "Jakarta Expression Language", "short_description": "Computer programming language", "url": "https://en.wikipedia.org/wiki/Jakarta_Expression_Language", "backlink": "https://en.wikipedia.org/wiki/Expression_language", "depth": 1.0}
{"title": "Rights Expression Language", "short_description": [], "url": "https://en.wikipedia.org/wiki/Rights_Expression_Language", "backlink": "https://en.wikipedia.org/wiki/Expression_language", "depth": 1.0}
{"title": "Computer science", "short_description": "Study of computation", "url": "https://en.wikipedia.org/wiki/Computer_science", "backlink": "https://en.wikipedia.org/wiki/Expression_language", "depth": 1.0}
```

Command line options:

```bash
--depth                <depth>       Max crawl depth
--verbose              [true|false]  Provides superficial CLI information
--debug                [true|false]  Provides verbose runtime output and information
--concurrency          <concurrency> Number of concurrent fetches
--concurrency-per-host <concurrency> Number of concurrent fetches per host
--header               "Key:Value"   Add a custom header (e.g., 'Key:Value'). Can be used multiple times.
--respect-robots       [true|false] (Default: True) Respects robots.txt
```


## Hooks (Experimental)

**wxpath** supports a pluggable hook system that allows you to modify the crawling and extraction behavior. You can register hooks to preprocess URLs, post-process HTML, filter extracted values, and more. Hooks will be executed in the order they are registered. Hooks may impact performance.

```python

from wxpath import hooks

@hooks.register
class OnlyEnglish:
    def post_parse(self, ctx, elem):
        lang = elem.xpath('string(/html/@lang)').lower()[:2]
        return elem if lang in ("en", "") else None
```

### Async usage

NOTE: Hooks may be synchronous or asynchronous, but all hooks in a project should follow the same style.
Mixing sync and async hooks is not supported and may lead to unexpected behavior.

```python

from wxpath import hooks

@hooks.register
class OnlyEnglish:
    async def post_parse(self, ctx, elem):
        lang = elem.xpath('string(/html/@lang)').lower()[:2]
        return elem if lang in ("en", "") else None

```

### Predefined Hooks

`JSONLWriter` (aliased `NDJSONWriter`) is a built-in hook that writes extracted data to a newline-delimited JSON file. This is useful for storing results in a structured format that can be easily processed later.

```python
from wxpath import hooks
hooks.register(hooks.JSONLWriter)
```


## Install

Requires Python 3.10+.

```
pip install wxpath
```


## More Examples

See [EXAMPLES.md](EXAMPLES.md) for more usage examples.


## Comparisons

See [COMPARISONS.md](COMPARISONS.md) for comparisons with other web-scraping tools.


## Advanced: Engine & Crawler Configuration

You can alter the engine and crawler's behavior like so: 

```python
from wxpath import wxpath_async_blocking_iter
from wxpath.core.runtime import WXPathEngine
from wxpath.http.client.crawler import Crawler

crawler = Crawler(
    concurrency=8,
    per_host=2,
    timeout=10,
    respect_robots=False,
    headers={
        "User-Agent": "my-app/0.1.0 (contact: you@example.com)", # Sites like Wikipedia will appreciate this
    },
)

# If `crawler` is not specified, a default Crawler will be created with
# the provided concurrency, per_host, and respect_robots values, or with defaults.
engine = WXPathEngine(
    # concurrency: int = 16, 
    # per_host: int = 8,
    # respect_robots: bool = True,
    # allowed_response_codes: set[int] = {200},
    # allow_redirects: bool = True,
    crawler=crawler,
)

path_expr = "url('https://en.wikipedia.org/wiki/Expression_language')//url(//main//a/@href)"

items = list(wxpath_async_blocking_iter(path_expr, max_depth=1, engine=engine))
```


## Project Philosophy

### Principles

- Enable declarative, crawling and scraping without boilerplate
- Stay lightweight and composable
- Asynchronous support for high-performance crawls

### Guarantees/Goals

- URLs are deduplicated on a best-effort, per-crawl basis.
- Crawls are intended to terminate once the frontier is exhausted or `max_depth` is reached.
- Requests are performed concurrently.
- Results are streamed as soon as they are available.

### Limitations (for now)

The following features are not yet supported:

- Persistent scheduling or crawl resumption
- Automatic proxy rotation
- Browser-based rendering (JavaScript execution)
- Strict result ordering


## WARNINGS!!!

- Be respectful when crawling websites. A scrapy-inspired throttler is enabled by default.
- Deep crawls (`///`) require user discipline to avoid unbounded expansion (traversal explosion).
- Deadlocks and hangs are possible in certain situations (e.g., all tasks waiting on blocked requests). Please report issues if you encounter such behavior.
- Consider using timeouts, `max_depth`, and XPath predicates and filters to limit crawl scope.


## Commercial support / consulting

If you want help building or operating crawlers/data feeds with wxpath (extraction, scheduling, monitoring, breakage fixes) or other web-scraping needs, please contact me at: rodrigopala91@gmail.com.


### Donate

If you like wxpath and want to support its development, please consider [donating](https://www.paypal.com/donate/?business=WDNDK6J6PJEXY&no_recurring=0&item_name=Thanks+for+using+wxpath%21+Donations+fund+development%2C+docs%2C+and+bug+fixes.+If+wxpath+saved+you+time%2C+a+small+contribution+helps%21&currency_code=USD).

## License

MIT
