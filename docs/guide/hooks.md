# Hooks (Experimental)

> **Warning:** pre-1.0.0 - APIs and contracts may change.

wxpath provides a pluggable hook system for customizing crawl and extraction behavior.

## Hook Lifecycle

Hooks can intercept at three points:

1. **post_fetch** - After HTTP response, before parsing
2. **post_parse** - After HTML parsing, before extraction
3. **post_extract** - After value extraction, before yielding

## Creating Hooks

### Basic Hook

```python
from wxpath import hooks

@hooks.register
class MyHook:
    def post_fetch(self, ctx, html_bytes):
        """Transform or filter response body."""
        # Return bytes to continue, None to drop
        return html_bytes

    def post_parse(self, ctx, elem):
        """Transform or filter parsed element."""
        # Return element to continue, None to drop
        return elem

    def post_extract(self, value):
        """Transform or filter extracted value."""
        # Return value to yield, None to drop
        return value
```

### Async Hooks

```python
from wxpath import hooks

@hooks.register
class AsyncHook:
    async def post_fetch(self, ctx, html_bytes):
        # Async operations supported
        return html_bytes

    async def post_parse(self, ctx, elem):
        return elem

    async def post_extract(self, value):
        return value
```

> **Note:** All hooks in a project should use the same style (sync or async). Mixing is not supported.

## FetchContext

Hook methods receive a `FetchContext` with crawl metadata:

```python
from wxpath.hooks.registry import FetchContext

# FetchContext fields:
# - url: str          - Current URL being processed
# - backlink: str     - URL that linked to this page
# - depth: int        - Current crawl depth
# - segments: list    - Remaining expression segments
# - user_data: dict   - Custom data storage
```

## Example Hooks

### Language Filter

```python
@hooks.register
class OnlyEnglish:
    def post_parse(self, ctx, elem):
        lang = elem.xpath('string(/html/@lang)').lower()[:2]
        return elem if lang in ("en", "") else None
```

### URL Logger

```python
@hooks.register
class URLLogger:
    def post_fetch(self, ctx, html_bytes):
        print(f"Fetched: {ctx.url} (from {ctx.backlink})")
        return html_bytes
```

### Value Transformer

```python
@hooks.register
class CleanText:
    def post_extract(self, value):
        if isinstance(value, str):
            return value.strip()
        return value
```

### Content Filter

```python
@hooks.register
class SkipErrors:
    def post_fetch(self, ctx, html_bytes):
        if b'error' in html_bytes.lower():
            return None  # Drop this response
        return html_bytes
```

## Built-in Hooks

### SerializeXPathMapAndNodeHook

Converts `XPathMap` and `XPathNode` objects to plain Python types:

```python
from wxpath.hooks import SerializeXPathMapAndNodeHook
from wxpath import hooks

hooks.register(SerializeXPathMapAndNodeHook)
```

### JSONLWriter / NDJSONWriter

Writes extracted data to a newline-delimited JSON file:

```python
from wxpath import hooks

hooks.register(hooks.JSONLWriter)
```

Output file can be configured via `WXPATH_OUT` environment variable.

Features:
- Non-blocking writes via background thread
- Queue-based buffering
- Automatic JSON serialization

## Hook Registration

### Decorator Style

```python
@hooks.register
class MyHook:
    pass
```

### Instance Registration

```python
hooks.register(MyHook())
```

### Class Registration

```python
hooks.register(MyHook)  # Instantiated automatically
```

## Accessing Registered Hooks

```python
from wxpath.hooks.registry import get_hooks

for hook in get_hooks():
    print(type(hook).__name__)
```

## Execution Order

Hooks execute in registration order. Each hook can:
- **Transform** the value and pass to next hook
- **Drop** the value by returning `None` (stops pipeline)

```python
# First registered, first executed
@hooks.register
class Hook1:
    def post_extract(self, value):
        return value.upper()

@hooks.register
class Hook2:
    def post_extract(self, value):
        return value.strip()

# Result: value.upper().strip()
```
