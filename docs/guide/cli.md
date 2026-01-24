# Command-Line Interface

> **Warning:** pre-1.0.0 - APIs and contracts may change.

wxpath provides a CLI for executing expressions directly from the terminal.

## Basic Usage

```bash
wxpath "url('https://quotes.toscrape.com')//a/@href"
```

Output is streamed as newline-delimited JSON (NDJSON).

## Options

| Option | Description | Default |
|--------|-------------|---------|
| `--depth <n>` | Maximum crawl depth | 1 |
| `--verbose` | Enable verbose output | false |
| `--debug` | Enable debug logging | false |
| `--concurrency <n>` | Global concurrent fetches | 16 |
| `--concurrency-per-host <n>` | Per-host concurrent fetches | 8 |
| `--header "Key:Value"` | Add custom header (repeatable) | - |
| `--respect-robots` | Respect robots.txt | true |
| `--cache` | Enable response caching | false |

## Examples

### Simple Link Extraction

```bash
wxpath "url('https://quotes.toscrape.com')//a/@href"
```

### Deep Crawl with Custom Headers

```bash
wxpath --depth 1 \
    --header "User-Agent: my-bot/1.0 (contact: me@example.com)" \
    "url('https://quotes.toscrape.com')///url(//a/@href)//title/text()"
```

### Structured Data Extraction

```bash
wxpath --depth 1 \
    --header "User-Agent: my-app/0.1 (contact: you@example.com)" \
    "url('https://en.wikipedia.org/wiki/Python_(programming_language)') \
    /map{ \
        'title': (//h1//text())[1] ! normalize-space(.), \
        'url': string(base-uri(.)) \
    }"
```

### Wikipedia Crawl with Filters

```bash
wxpath --depth 1 \
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
```

### Cached Crawl

```bash
# Requires wxpath[cache-sqlite] or wxpath[cache-redis]
wxpath --cache --depth 1 \
    "url('https://example.com')///url(//a/@href)//title/text()"
```

## Output Format

The CLI outputs NDJSON (newline-delimited JSON):

```json
{"title": "Page 1", "url": "https://example.com/page1"}
{"title": "Page 2", "url": "https://example.com/page2"}
{"title": "Page 3", "url": "https://example.com/page3"}
```

This format is easy to pipe to other tools:

```bash
# Count results
wxpath "..." | wc -l

# Filter with jq
wxpath "..." | jq 'select(.title != null)'

# Save to file
wxpath "..." > results.jsonl
```

## Environment Variables

| Variable | Description |
|----------|-------------|
| `WXPATH_OUT` | Output file path for JSONLWriter hook |
