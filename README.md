
# wxpath - declarative web crawling with XPath

**wxpath** is a declarative web crawler where traversal is expressed directly in XPath. Instead of writing imperative crawl loops, you describe what to follow and what to extract in a single expression. **wxpath** evaluates that expression concurrently, breadth-first-*ish*, and streams results as they are discovered.

By introducing the `url(...)` operator and the `///` syntax, **wxpath**'s engine is able to perform deep, recursive web crawling and extraction.

NOTE: This project is in early development. Core concepts are stable, but the API and features may change. Please report issues - in particular, deadlocked crawls or unexpected behavior - and any features you'd like to see (no guarantee they'll be implemented).

## Contents

- [Example](#example)
- [`url(...)` and `///` Explained](#url-and---explained)
- [General flow](#general-flow)
- [Asynchronous Crawling](#asynchronous-crawling)
- [Output types](#output-types)
- [XPath 3.1 support](#xpath-31-support)
- [CLI](#cli)
- [Hooks (Experimental)](#hooks-experimental)
- [Install](#install)
- [More Examples](#more-examples)
- [Advanced: Engine & Crawler Configuration](#advanced-engine--crawler-configuration)
- [Project Philosophy](#project-philosophy)
- [Warnings](#warnings)
- [License](#license)

## Example

```python
import wxpath

path = """
url('https://en.wikipedia.org/wiki/Expression_language')
 ///main//a/@href[starts-with(., '/wiki/') and not(contains(., ':'))]/url(.)
 /map{
    'title':(//span[contains(@class, "mw-page-title-main")]/text())[1],
    'url':string(base-uri(.)),
    'short_description':(//div[contains(@class, 'shortdescription')]/text())[1]
 }
"""

for item in wxpath.wxpath_async_blocking_iter(path, max_depth=1):
    print(item)
```

Output:

```python
map{'title': TextNode('Computer language'), 'url': 'https://en.wikipedia.org/wiki/Computer_language', 'short_description': TextNode('Formal language for communicating with a computer')}
map{'title': TextNode('Machine-readable medium and data'), 'url': 'https://en.wikipedia.org/wiki/Machine_readable', 'short_description': TextNode('Medium capable of storing data in a format readable by a machine')}
map{'title': TextNode('Advanced Boolean Expression Language'), 'url': 'https://en.wikipedia.org/wiki/Advanced_Boolean_Expression_Language', 'short_description': TextNode('Hardware description language and software')}
map{'title': TextNode('Jakarta Expression Language'), 'url': 'https://en.wikipedia.org/wiki/Jakarta_Expression_Language', 'short_description': TextNode('Computer programming language')}
map{'title': TextNode('Data Analysis Expressions'), 'url': 'https://en.wikipedia.org/wiki/Data_Analysis_Expressions', 'short_description': TextNode('Formula and data query language')}
map{'title': TextNode('Domain knowledge'), 'url': 'https://en.wikipedia.org/wiki/Domain_knowledge', 'short_description': TextNode('Specialist knowledge within a specific field')}
map{'title': TextNode('Rights Expression Language'), 'url': 'https://en.wikipedia.org/wiki/Rights_Expression_Language', 'short_description': TextNode('Machine-processable language used to express intellectual property rights (such as copyright)')}
map{'title': TextNode('Computer science'), 'url': 'https://en.wikipedia.org/wiki/Computer_science', 'short_description': TextNode('Study of computation')}
```

The above expression does the following:

1. Starts at the specified URL, `https://en.wikipedia.org/wiki/Expression_language`.
2. Filters for links in the `<main>` section that start with `/wiki/` and do not contain a colon (`:`).
3. For each link found, 
    * it follows the link and extracts the title, URL, and short description of the page.
    * it repeats step 2 until the maximum depth is reached.
4. Streams the extracted data as it is discovered.


## `url(...)` and `///` Explained

- `url(...)` is a custom operator that fetches the content of the user-specified or internally generated URL and returns it as an `lxml.html.HtmlElement` for further XPath processing.
- `///` indicates infinite/recursive traversal. It tells **wxpath** to continue following links indefinitely, up to the specified `max_depth`. Unlike repeated `url()` hops, it allows a single expression to describe unbounded graph exploration. WARNING: Use with caution and constraints (via `max_depth` or XPath predicates) to avoid traversal explosion.

## General flow

**wxpath** evaluates an expression as a list of traversal and extraction steps (internally referred to as `Segment`s).

`url(...)` creates crawl tasks either statically (via a fixed URL) or dynamically (via a URL derived from the XPath expression). **URLs are deduplicated globally, not per-depth and on a best-effort basis**.

XPath segments operate on fetched documents (fetched via the immediately preceding `url(...)` operations).

`///` indicates infinite/recursive traversal - it proceeds breadth-first-*ish* up to `max_depth`.

Results are yielded as soon as they are ready.


## Asynchronous Crawling


**wxpath** is `asyncio/aiohttp`-first, providing an asynchronous API for crawling and extracting data.

```python
import asyncio
from wxpath import wxpath_async

items = []

async def main():
    path_expr = "url('https://en.wikipedia.org/wiki/Expression_language')///url(@href[starts-with(., '/wiki/')])//a/@href"
    async for item in wxpath_async(path_expr, max_depth=1):
        items.append(item)

asyncio.run(main())
```

### Blocking, Concurrent Requests


**wxpath** also supports concurrent requests using an asyncio-in-sync pattern, allowing you to crawl multiple pages concurrently while maintaining the simplicity of synchronous code. This is particularly useful for crawls in strictly synchronous execution environments (i.e., not inside an `asyncio` event loop) where performance is a concern.

```python
from wxpath import wxpath_async_blocking_iter

path_expr = "url('https://en.wikipedia.org/wiki/Expression_language')///url(@href[starts-with(., '/wiki/')])//a/@href"
items = list(wxpath_async_blocking_iter(path_expr, max_depth=1))
```

## Output types

The wxpath Python API yields structured objects, not just strings.

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
    ///div[@id='mw-content-text']//a/url(@href)
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

```bash
> wxpath --depth 1 "\
    url('https://en.wikipedia.org/wiki/Expression_language')\
    ///div[@id='mw-content-text'] \
    //a/url(@href[starts-with(., '/wiki/') \
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

```
pip install wxpath
```


## More Examples

```python
import wxpath

#### EXAMPLE 1 - Simple, single page crawl and link extraction #######
#
# Starting from Expression language's wiki, extract all links (hrefs) 
# from the main section. The `url(...)` operator is used to execute a 
# web request to the specified URL and return the HTML content.
#
path_expr = "url('https://en.wikipedia.org/wiki/Expression_language')//main//a/@href"

items = wxpath.wxpath_async_blocking(path_expr)


#### EXAMPLE 2 - Two-deep crawl and link extraction ##################
#
# Starting from Expression language's wiki, crawl all child links 
# starting with '/wiki/', and extract each child's links (hrefs). The
# `url(...)` operator is pipe'd arguments from the evaluated XPath.
#
path_expr = "url('https://en.wikipedia.org/wiki/Expression_language')//url(@href[starts-with(., '/wiki/')])//a/@href"

#### EXAMPLE 3 - Infinite crawl with BFS tree depth limit ############
#
# Starting from Expression language's wiki, infinitely crawl all child
# links (and child's child's links recursively). The `///` syntax is
# used to indicate an infinite crawl. 
# Returns lxml.html.HtmlElement objects.
#
path_expr = "url('https://en.wikipedia.org/wiki/Expression_language')///main//a/url(@href)"

# The same expression written differently:
path_expr = "url('https://en.wikipedia.org/wiki/Expression_language')///url(//main//a/@href)"

# Modify (inclusive) max_depth to limit the BFS tree (crawl depth).
items = wxpath.wxpath_async_blocking(path_expr, max_depth=1)

#### EXAMPLE 4 - Infinite crawl with field extraction ################
#
# Infinitely crawls Expression language's wiki's child links and 
# childs' child links (recursively) and then, for each child link 
# crawled, extracts objects with the named fields as a dict.
#
path_expr = """
    url('https://en.wikipedia.org/wiki/Expression_language')
     ///main//a/url(@href)
     /map {
        'title':(//span[contains(@class, "mw-page-title-main")]/text())[1], 
        'short_description':(//div[contains(@class, "shortdescription")]/text())[1],
        'url'://link[@rel='canonical']/@href[1],
        'backlink':wx:backlink(.),
        'depth':wx:depth(.)
    }
"""

# Under the hood of wxpath.core.wxpath, we generate `segments` list, 
# revealing the operations executed to accomplish the crawl.
# >> segments = wxpath.core.parser.parse_wxpath_expr(path_expr); 
# >> segments
# [Segment(op='url', value='https://en.wikipedia.org/wiki/Expression_language'),
#  Segment(op='url_inf', value='///url(//main//a/@href)'),
#  Segment(op='xpath', value='/map {        \'title\':(//span[contains(@class, "mw-page-title-main")]/text())[1],         \'short_description\':(//div[contains(@class, "shortdescription")]/text())[1],        \'url\'://link[@rel=\'canonical\']/@href[1]    }')]

#### EXAMPLE 5 = Seeding from XPath function expression + mapping operator (`!`)
#
# Functionally create 10 Amazon book search result page URLs, map each URL to 
# the url(.) operator, and for each page, extract the title, price, and link of
# each book listed.
# 
base_url = "https://www.amazon.com/s?k=books&i=stripbooks&page="

path_expr = f"""
    (1 to 10) ! ('{base_url}' || .) !
    url(.)
        //span[@data-component-type='s-search-results']//*[@role='listitem']
            /map {{
                'title': (.//h2/span/text())[1],
                'price': (.//span[@class='a-price']/span[@class='a-offscreen']/text())[1],
                'link': (.//a[@aria-describedby='price-link']/@href)[1]
            }}
"""

items = list(wxpath.wxpath_async_blocking_iter(path_expr, max_depth=1))
```

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
)

# If `crawler` is not specified, a default Crawler will be created with
# the provided concurrency and per_host values, or with defaults.
engine = WXPathEngine(
    # concurrency=16,
    # per_host=8, 
    crawler=crawler,
)

path_expr = "url('https://en.wikipedia.org/wiki/Expression_language')///main//a/url(@href)"

items = list(wxpath_async_blocking_iter(path_expr, max_depth=1, engine=engine))
```


## Project Philosophy

### Principles

- Enable declarative, recursive scraping without boilerplate
- Stay lightweight and composable
- Asynchronous support for high-performance crawls

### Guarantees/Goals

- URLs are deduplicated on a best-effort, per-crawl basis.
- Crawls are intended to terminate once the frontier is exhausted or `max_depth` is reached.
- Requests are performed concurrently.
- Results are streamed as soon as they are available.

### Non-Goals/Limitations (for now)

- Strict result ordering
- Persistent scheduling or crawl resumption
- Automatic proxy rotation
- Browser-based rendering (JavaScript execution)

## WARNINGS!!!

- Be respectful when crawling websites. A scrapy-inspired throttler is enabled by default.
- Recursive (`///`) crawls require user discipline to avoid unbounded expansion (traversal explosion).
- Deadlocks and hangs are possible in certain situations (e.g., all tasks waiting on blocked requests). Please report issues if you encounter such behavior.
- Consider using timeouts, `max_depth`, and XPath predicates and filters to limit crawl scope.

## License

MIT
