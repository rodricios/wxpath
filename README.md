
# wxpath

**wxpath** is an extended XPath engine for Python that enables declarative web crawling by allowing XPath expressions to seamlessly follow links and traverse multiple HTML pages using a custom `url(...)` operator. It combines familiar XPath syntax with recursive web navigation for advanced data extraction workflows.

## Examples

```python
import wxpath

path_expr = "url('https://en.wikipedia.org/wiki/Expression_language')//url(@href[starts-with(., '/wiki/')])//a/@href"

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
2. Support more infinite crawl filterings:
    * `url('https://en.wikipedia.org/wiki/United_States')///main//a/url(@href[child])`
3. Flesh out tests on filtered infinite crawls

## Roadmap (rough and subject to drastic change)

1. Tighten up core.py
    * Remove or hide (behind a flag) debug print statements
    * Refactor parsing code into separate submodule
    * Standardize operations ("op" in "op, val" pairs) related to xpath'ing and crawling instructions
2. Create sample projects that utilize its crawling features
    * Neo4J addon and dashboards displaying wxpath's capabilities of crawling, extracting, and uploading (via the pipelining decorator) data.