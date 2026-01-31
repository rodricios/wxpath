## 0.1.0
- Initial public release
- Declarative XPath-based crawling
- Async-first engine with streaming results

## 0.2.0
- Introduce `follow=` parameter to `url()` operator

## 0.3.0
- Polite crawling by default
- New Pratt parser
- Add DSL grammar design document

## 0.4.0
- Settings module
- Persistence and caching
- Progress bar

## 0.4.1
- Add `yield_errors` runtime option - return error dicts for failed requests
- Fix cache backend: Redis backend no longer requires SQLite backend

## 0.5.0
- Add `depth` parameter to `url()` operator
- Add two-panel TUI for interactive testing and exporting
  - Settings for concurrency, per-host, respect robots, verify_ssl and headers
  - Persistent crawls with SQLite
  - Export to CSV, JSON