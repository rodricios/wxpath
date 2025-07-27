
# wxpath

**wxpath** is an extended XPath engine for Python that enables declarative web crawling by allowing XPath expressions to seamlessly follow links and traverse multiple HTML pages using a custom `url(...)` operator. It combines familiar XPath syntax with recursive web navigation for advanced data extraction workflows.

## Examples

```python
import wxpath

## EXAMPLE 1
# Starting from Expression language's wiki, infinitely crawl all child links (and child's child's links recursively).
path_expr = "url('https://en.wikipedia.org/wiki/Expression_language')///main//a/url(@href)"
# The same expression written differently:
path_expr = "url('https://en.wikipedia.org/wiki/Expression_language')///url(//main//a/@href)"

# Modify max_depth to limit the BFS tree (crawl depth).
items = list(wxpath.core.wxpath(path_expr, max_depth=1))


## EXAMPLE 2
# Starting from Expression language's wiki, crawl all child links, and extract all each child's links (hrefs).
path_expr = "url('https://en.wikipedia.org/wiki/Expression_language')//url(@href[starts-with(., '/wiki/')])//a/@href"


## EXAMPLE 3
# Infinitely crawls Expression language's wiki's child links and childs' child links (recursively)
# and then, for each child link crawled, extracts objects with the named fields as a dict.
 path_expr = """url('https://en.wikipedia.org/wiki/Expression_language')
     ///main//a/url(@href)
     /{
     title://span[contains(@class, "mw-page-title-main")]/text()[0],
     shortdescription://div[contains(@class, "shortdescription")]/text()[0],
     url://link[@rel='canonical']/@href[0]
 }"""


# Under the hood of wxpath.core.wxpath, we generate `segments` list, revealing the operations executed to
# accomplish the crawl.
segments = wxpath.core.parse_wxpath_expr(path_expr); segments

results = []
for r in wxpath.core.evaluate_wxpath_bfs_iter(None, segments, max_depth=2):
    print(r)
    results.append(r)
```

## Install

```
pip install -e .
```

## Goals

- Combine XPath-style syntax with web traversal semantics
- Enable declarative, recursive scraping without boilerplate
- Stay lightweight and composable

## License

MIT

## TODO

1. Support `///url('https://en.wikipedia.org/wiki/United_States') - crawls page and all forward links infinitely
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
5. Build out pipeline/extention system that allows for:
    1. More precise webpage processing
    2. Finetuned crawling - we can direct an infinite crawl via xpath filtering and xpath operations, 
       however, more complex logic can be implemented to prune the search tree.


## Roadmap (rough and subject to drastic change)

1. Tighten up core.py
    * ~~Remove or hide (behind a flag) debug print statements~~
    * Refactor parsing code into separate submodule
    * Standardize operations ("op" in "op, val" pairs) related to xpath'ing and crawling instructions
2. Create sample projects that utilize its crawling features
    * Neo4J addon and dashboards displaying wxpath's capabilities of crawling, extracting, and uploading (via the pipelining decorator) data.