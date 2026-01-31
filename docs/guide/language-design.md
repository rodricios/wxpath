# Language Design

> **Warning:** pre-1.0.0 - APIs and contracts may change.

wxpath extends XPath with URL-fetching operators, enabling declarative web traversal expressed directly in path syntax.

## Core Operators

### `url(literal)`

Fetches content from a literal URL string:

```python
"url('https://example.com')"
```

Returns an `lxml.html.HtmlElement` representing the parsed HTML document.

### `url(xpath)`

Fetches content from URLs extracted by an XPath expression:

```python
"url('https://example.com')//url(//a/@href)"
```

The inner XPath (`//a/@href`) extracts URLs from the current document, which are then fetched.

### `///url(xpath)` - Deep Crawl (starting from descendants)

Indicates recursive<sup>*</sup> crawling. The engine follows links extracted by the XPath expression up to `max_depth`:

<sup>*</sup> The term "recursive" is used informally in this document, however, I do not mean DFS-style recursion. `wxpath` uses a FIFO queue, and we expand that queue by visiting the URLs present in the _current document_.

```python
"""
url('https://example.com')
  ///url(//a/@href)
    //title/text()
"""
```

###  `url('...', follow=...)` - Deep Crawl (starting from root)

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
```

###  `url('...', follow=..., depth=...)` - Deep Crawl (starting from root) with depth limit

The `depth` parameter allows you to specify the maximum depth of the crawl. This is useful when you want to limit the depth of the crawl to a specific number of levels.

## Expression Structure

A wxpath expression is a sequence of **segments**:

```
url(start) [///url(follow)] [extraction]
```

Where:
- `url(start)` - Initial URL(s) to fetch
- `///url(follow)` - Optional recursive crawl pattern
- `extraction` - XPath to extract data from fetched pages

### Segment Types

| Segment | Description |
|---------|-------------|
| `url('...')` | Fetch from literal URL |
| `/url(xpath)` | Fetch from XPath-extracted URLs |
| `//url(xpath)` | One-hop link following |
| `///url(xpath)` | Recursive deep crawl |
| XPath | Standard XPath 3.1 expression |

## XPath 3.1 Features

wxpath uses `elementpath` for XPath 3.1 support, enabling:

### Maps

```python
"/map{ 'key1': //xpath1, 'key2': //xpath2 }"
```

### Arrays

```python
"/array{ //item1, //item2 }"
```

### Built-in Functions

Standard XPath 3.1 functions plus wxpath-specific:

| Function | Description |
|----------|-------------|
| `base-uri(.)` | Current document URL |
| `wx:backlink(.)` | URL that linked to current page |
| `wx:depth(.)` | Current crawl depth |

## Examples

### Extract Links with Context

```python
"""
url('https://example.com')
  //a/map{
    'text': string(.),
    'href': @href,
    'source': string(base-uri(.))
  }
"""
```

### Filtered Deep Crawl

```python
"""
url('https://en.wikipedia.org/wiki/Main_Page')
  ///url(
    //a/@href[
      starts-with(., '/wiki/')
      and not(contains(., ':'))
    ]
  )
  /map{
    'title': //h1/span/text() ! normalize-space(.),
    'url': string(base-uri(.))
  }
"""
```

### Pagination Pattern

```python
"""
url('https://example.com/page/1')
  ///url(//a[@class='next']/@href)
    //div[@class='item']/text()
"""
```

## Execution Model

1. **Parse** - Expression is parsed into an AST of segments
2. **Seed** - Initial `url('...')` creates the first crawl tasks
3. **BFS-ish Traversal** - Tasks are processed breadth-first with deduplication
4. **Extraction** - XPath segments extract data from fetched documents
6. **Streaming** - Results are yielded as soon as available

The engine handles:
- URL deduplication (best-effort, per-crawl)
- Concurrent fetching with configurable limits
- robots.txt compliance
- Adaptive throttling
- Retry policies

## Best Practices

1. **Use XPath predicates** to filter links early and avoid traversal explosion
2. **Set appropriate `max_depth`** to bound crawl scope
3. **Add `User-Agent` headers** for polite crawling
4. **Use caching** for development and resumable crawls
