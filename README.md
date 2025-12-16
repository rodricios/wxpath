
# wxpath - the extraction language for the web

**wxpath** (short for `webxpath`) is an extended XPath engine for Python that enables declarative web crawling by allowing XPath expressions to seamlessly follow links and traverse multiple HTML pages using a custom `url(...)` operator. It combines familiar XPath syntax with recursive web navigation for advanced data extraction workflows.

If you know XPath, **wxpath** will be easy to pick up!

## Examples

```python
import wxpath

#### EXAMPLE 1 - Simple, single page crawl and link extraction #######
#
# Starting from Expression language's wiki, extract all links (hrefs) 
# from the main section. The `url(...)` operator is used to execute a 
# web request to the specified URL and return the HTML content.
#
path_expr = "url('https://en.wikipedia.org/wiki/Expression_language')//main//a/@href"

items = wxpath.engine.wxpath_async_blocking(path_expr)


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
items = wxpath.engine.wxpath_async_blocking(path_expr, max_depth=1)

#### EXAMPLE 4 - Infinite crawl with field extraction ################
#
# Infinitely crawls Expression language's wiki's child links and 
# childs' child links (recursively) and then, for each child link 
# crawled, extracts objects with the named fields as a dict.
#
path_expr = """url('https://en.wikipedia.org/wiki/Expression_language')
     ///main//a/url(@href)
     /map {
        'title':(//span[contains(@class, "mw-page-title-main")]/text())[1], 
        'short_description':(//div[contains(@class, "shortdescription")]/text())[1],
        'url'://link[@rel='canonical']/@href[1]
    }
"""


# Under the hood of wxpath.core.wxpath, we generate `segments` list, 
# revealing the operations executed to accomplish the crawl.
# >> segments = wxpath.core.parser.parse_wxpath_expr(path_expr); 
# >> segments
# [Segment(op='url', value='https://en.wikipedia.org/wiki/Expression_language'),
#  Segment(op='url_inf', value='///url(//main//a/@href)'),
#  Segment(op='xpath', value='/map {        \'title\':(//span[contains(@class, "mw-page-title-main")]/text())[1],         \'short_description\':(//div[contains(@class, "shortdescription")]/text())[1],        \'url\'://link[@rel=\'canonical\']/@href[1]    }')]
```

## XPath 3.1 By Default

**wxpath** uses the `elementpath` library to provide XPath 3.1 support, enabling advanced XPath features like **maps**, **arrays**, and more. This allows you to write more expressive and powerful XPath queries.

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

## Asynchronous Crawling

Requires `aiohttp` dependency: 

```
pip install -e ".[async]" # or pip install aiohttp
```


**wxpath** provides an asynchronous API for crawling and extracting data, allowing you to take advantage of Python's `asyncio` capabilities for non-blocking I/O operations.

```python
import asyncio
from wxpath.core.async_ import wxpath_async

items = []

async def main():
    path_expr = "url('https://en.wikipedia.org/wiki/Expression_language')///url(@href[starts-with(., '/wiki/')])//a/@href"
    async for item in wxpath_async(path_expr, max_depth=1):
        items.append(item)

asyncio.run(main())
```

### Blocking, Concurrent Requests


**wxpath** also supports concurrent requests using an asyncio-in-sync pattern, allowing you to crawl multiple pages concurrently while maintaining the simplicity of synchronous code. This is particularly useful for large-scale crawls in strictly synchronous execution environments (i.e., not inside an `asyncio` event loop) where performance is a concern.

```python
from wxpath.core.async_ import wxpath_async_blocking_iter

path_expr = "url('https://en.wikipedia.org/wiki/Expression_language')///url(@href[starts-with(., '/wiki/')])//a/@href"
items = list(wxpath_async_blocking_iter(path_expr, max_depth=1))
```


## Hooks

**wxpath** supports a pluggable hook system that allows you to modify the crawling and extraction behavior. You can register hooks to preprocess URLs, post-process HTML, filter extracted values, and more.

```python

from wxpath import hooks

@hooks.register
class OnlyEnglish:
    def post_parse(self, ctx, elem):
        lang = elem.xpath('string(/html/@lang)').lower()[:2]
        return elem if lang in ("en", "") else None

```

### Async usage

NOTE: do not mix sync and async hooks in the same project as it will lead to unexpected behavior.

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

## CLI

**wxpath** provides a command-line interface (CLI) to quickly execute wxpath expressions directly from the terminal.

```bash
> python -m wxpath.cli --depth 1 "\
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


## Install

```
pip install -e .
```

## Goals

- Combine XPath-style syntax with web traversal semantics
- Enable declarative, recursive scraping without boilerplate
- Stay lightweight and composable
- Asynchronous support for high-performance crawls

## License

MIT

## TODO

1. Support `///url('https://en.wikipedia.org/wiki/United_States')` - crawls page and all forward links infinitely
2. ~~Support more infinite crawl filterings:~~
    * ~~`url('https://en.wikipedia.org/wiki/United_States')///main//a/url(@href)`~~
3. Flesh out tests on filtered infinite crawls
4. ~~Extend DSL to support inline, multiple field extractions~~.
    * `url('example.com')//{field_name:<xpath>}`
    * `url('example.com')//xpath/filter/{field_name:<xpath>}`
    * The return object would be a list of dicts with field_name:value (value extracted from the xpath)
    ```
    url('https://en.wikipedia.org/wiki/United_States')/{
        title://span[contains(@class, "mw-page-title-main")]/text(),
        shortdescription://div[contains(@class, "shortdescription")]/text()
    }
    ```
5. Build out pipeline/extention system that allows for (IN PROGRESS):
    1. More precise webpage processing
    2. Finetuned crawling - we can direct an infinite crawl via xpath filtering and xpath operations, 
       however, more complex logic can be implemented to prune the search tree.
    3. Add builtin hooks for common tasks like:
        * Filtering out non-English pages
        * Extracting metadata from pages
        * JSON/YAML/XML output formatting
        * LLM integration for content analysis
6. Flesh out Requesting engine (IN PROGRESS - requires documentation):
    * Support for custom headers, cookies, etc.
    * Support for proxies
    * Support for request throttling
    * Support for request retries
7. ~~XPath 3 support via `elementpath` library~~
