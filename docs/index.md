<div class="logo-container">
<svg width="100%" height="100%" viewBox="0 0 600 120" xmlns="http://www.w3.org/2000/svg">
  <style>
    /* Added broader font stack for better alignment on Mac/Windows/Linux */
    text { 
      font-family: SFMono-Regular, Consolas, 'Liberation Mono', 'Courier New', monospace; 
      font-weight: bold; 
      font-size: 14px; 
    }
  </style>
  <foreignObject width="100%" height="100%">
    <div xmlns="http://www.w3.org/1999/xhtml">
      <pre class="logo-text" style="margin:0; line-height: 1.2;">                            __  __  
 _      ___  ______  ____ _/ /_/ /_ 
| | /| / / |/_/ __ \/ __ `/ __/ __ \
| |/ |/ /&gt;  &lt;/ /_/ / /_/ / /_/ / / /
|__/|__/_/|_/ .___/\__,_/\__/_/ /_/ 
           /_/</pre>
    </div>
  </foreignObject>
</svg>
</div>

# Declarative web graph traversal with XPath

> **Warning:** pre-1.0.0 - APIs and contracts may change.

**wxpath** is a declarative web crawler where traversal is expressed directly in XPath. Instead of writing imperative crawl loops, wxpath lets you describe what to follow and what to extract in a single expression.

## Quick Start

```python
import wxpath

expr = "url('https://quotes.toscrape.com')//a/@href"

for link in wxpath.wxpath_async_blocking_iter(expr):
    print(link)
```

## Key Features

- **Declarative Traversal** - Express web crawling logic in XPath-like syntax
- **Concurrent Execution** - Async-first design with automatic concurrency management
- **XPath 3.1 Support** - Full XPath 3.1 features including maps and arrays via `elementpath`
- **Polite Crawling** - Built-in robots.txt respect and adaptive throttling
- **Extensible Hooks** - Pluggable pipeline for transforming responses and extracted data
- **Persistent Crawls** - Optional SQLite or Redis backends for persistent crawl results

## Installation

```bash
pip install wxpath
```

For caching/persistence support:

```bash
pip install wxpath[cache-sqlite]
# or
pip install wxpath[cache-redis]
```

## Core Concepts

### The `url(...)` Operator

The `url(...)` operator fetches content from a URL and returns it as an `lxml.html.HtmlElement` for further XPath processing:

```python
# Fetch a page and extract all links
"url('https://example.com')//a/@href"
```

### Deep Crawling 

#### `///url(...)`

The `///url(...)` syntax enables recursive crawling up to a specified `max_depth`:

```python
path_expr = """
url('https://quotes.toscrape.com')
  ///url(//a/@href)
    //a/@href
"""

for item in wxpath.wxpath_async_blocking_iter(path_expr, max_depth=1):
    print(item)
```


####  `url('...', follow=...)`

The `follow` parameter allows you to specify a follow path for recursive crawling at the root node. While this may seem redundant and duplicated behavior found with the `///url` syntax, it is not. The `follow` parameter allows you to initiate, yes, a recursive crawl, however it also allows you to begin extracting data from the root node. This is useful in cases where you want to paginate through search pages.

```python
path_expr = """
url('https://quotes.toscrape.com/tag/humor/', follow=//li[@class='next']/a/@href)
  //div[@class='quote']
    /map{
      'author': (./span/small/text())[1],
      'text': (./span[@class='text']/text())[1]
      }
"""

### XPath 3.1 Maps

Extract structured data using XPath 3.1 map syntax:

```python
path_expr = """
url('https://example.com')
  /map{
    'title': //title/text() ! string(.),
    'url': string(base-uri(.))
  }
"""
```

## Next Steps

- [Getting Started](getting-started.md) - Detailed setup and first crawl
- [Language Design](guide/language-design.md) - Understanding wxpath expressions
- [API Reference](api/index.md) - Complete API documentation
- [Examples](examples.md) - More usage examples
