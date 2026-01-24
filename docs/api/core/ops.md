# Operations

> **Warning:** pre-1.0.0 - APIs and contracts may change.

Operation handlers that execute wxpath segments. This module follows a dispatcher pattern, where each segment signature (wxpath function name or segment type, and its argument types) is mapped to a handler function.

This module (along with the parser) can both be tightened up in the following ways: 

1. Better type checking.
    1. Specifically, check that next segments are of the correct type.
2. Less intents (`ProcessIntent` may be unnecessary).
3. More intuitive error messages.

## Location

```python
from wxpath.core.ops import get_operator, OPS_REGISTER
```

## get_operator

```python
def get_operator(binary_or_segment: Binary | Segment) -> Callable
```

Retrieve the handler function for a AST node type.

**Parameters:**
- `binary_or_segment` - AST node to find handler for

**Returns:** Handler function

## OPS_REGISTER

Global dictionary mapping segment signatures to handlers.

```python
OPS_REGISTER: dict[tuple, Callable] = {}
```

## Handler Registration

Handlers are registered with the `@register` decorator:

```python
from wxpath.core.ops import register
from wxpath.core.parser import Xpath, String

@register(Xpath)
def handle_xpath(elem, segments, depth):
    # Execute XPath on element
    ...
    return [DataIntent(value=result)]

@register('url', (String,))
def handle_url_literal(elem, segments, depth):
    # Fetch literal URL
    url = segments[0].args[0].value
    return [CrawlIntent(url=url, next_segments=segments[1:])]
```

TODO: Converge on a common function parameter type for the register decorator. Right now it allows for AST node type OR string.

## Registered Handlers

### XPath Handler

Signature: `(Xpath,)`

Executes XPath expressions on elements.

### URL Literal Handler

Signature: `('url', (String,))`

Yields a CrawlIntent for a literal URL. This signal eventually reaches the crawler.

```python
"url('https://example.com')"
```

### URL XPath Handler

Signature: `('url', (Xpath,))`

Yields CrawlIntents for URLs extracted by XPath.

```python
"url(//a/@href)"
```

### URL Query Handler

Signature: `('//url', ...)`

Yields CrawlIntents for URLs extracted by XPath.

```python
"//url(//a/@href)"
```

### URL Crawl Handler

Signature: `('///url', (Xpath,))`

Recursive deep crawling.

```python
"///url(//a/@href)"
```

### URL Crawl with Extraction Handler

Signature: `('///url', (Xpath, str))`

Deep crawl with inline extraction. Yields InfiniteCrawlIntent.

### Binary (Map) Handler

Signature: `(Binary, ...)`

Handles the map operator (`!`). (More to come...)

## Handler Return Values

Handlers return a list of intents:

```python
def my_handler(elem, segments, depth) -> Iterable[Intent]:
    return (
        CrawlIntent(url="...", next_segments=...),
        DataIntent(value={"key": "value"}),
        ProcessIntent(elem=elem, next_segments=...),
    )
```

## RuntimeSetupError

```python
class RuntimeSetupError(Exception):
    pass
```

Raised when handler registration fails (e.g., duplicate signature).
