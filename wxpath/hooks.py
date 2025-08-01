"""
Pluggable hook system for wxpath.

Write once:

    from wxpath import hooks

    @hooks.register
    class OnlyEnglish:
        def post_parse(self, ctx, elem):
            lang = elem.xpath('string(/html/@lang)').lower()[:2]
            return elem if lang in ("en", "") else None

... and wxpath.core will call it automatically.
"""

from __future__ import annotations

import functools
from collections.abc import Generator
from dataclasses import dataclass, field
from typing import Protocol, List, Optional, Any, Iterable

from lxml import html
from elementpath.serialization import XPathMap, XPathNode


# --------------------------------------------------------------------------- #
# Dataclass describing the crawl context for a single URL
# --------------------------------------------------------------------------- #
@dataclass
class FetchContext:
    url: str
    backlink: Optional[str]
    depth: int
    segments: list        # remaining op/value pairs
    user_data: dict = field(default_factory=dict)


# --------------------------------------------------------------------------- #
# Hook protocol - every method is optional
# --------------------------------------------------------------------------- #
class Hook(Protocol):
    # Return False to abort fetching this URL
    # def pre_fetch(self, ctx: FetchContext) -> bool: ...

    # May return modified HTML bytes or None to drop this branch entirely
    def post_fetch(self, ctx: FetchContext, html_bytes: bytes) -> bytes | None: ...

    # May return modified element or None to drop this branch entirely
    def post_parse(
        self, ctx: FetchContext, elem: html.HtmlElement
    ) -> html.HtmlElement | None: ...

    # Called for every candidate link; return False to prevent enqueueing it
    # def pre_queue(self, ctx: FetchContext, url: str) -> bool: ...

    # Called for every extracted value; may transform or drop it
    def post_extract(self, value: Any) -> Any: ...


# --------------------------------------------------------------------------- #
# Global registry helpers
# --------------------------------------------------------------------------- #
_global_hooks: List[Hook] = []


def register(hook: Hook) -> Hook:
    """
    Decorator / helper to add a Hook to the global list.

    Example
    -------
    >>> @register
    ... class DebugHook:
    ...     def post_fetch(self, ctx, html_bytes):
    ...         print("Fetched", ctx.url)
    ...         return html_bytes
    """
    _global_hooks.append(hook())
    return hook


def get_hooks() -> List[Hook]:
    """Return the list of globally-registered hooks (read-only)."""
    return list(_global_hooks)


def iter_post_extract_hooks() -> Iterable[Hook]:
    yield from (h for h in _global_hooks if hasattr(h, "post_extract"))


def pipe_post_extract(gen_func):
    """
    Decorator: wrap a *generator function* so every yielded value
    is piped through the registered post_extract hooks.
    """
    @functools.wraps(gen_func)
    def wrapper(*args, **kwargs) -> Generator:
        # breakpoint()
        for item in gen_func(*args, **kwargs):
            for hook in iter_post_extract_hooks():
                item = hook.post_extract(item)
                if item is None:       # hook decided to drop it
                    break
            if item is not None:
                yield item
    return wrapper


def pipe_post_extract_async(async_gen_func):
    """
    Async variant - wraps an *async* generator function.
    """
    @functools.wraps(async_gen_func)
    async def wrapper(*args, **kwargs):
        async for item in async_gen_func(*args, **kwargs):
            for hook in iter_post_extract_hooks():
                item = hook.post_extract(item)
                if item is None:
                    break
            if item is not None:
                yield item
    return wrapper


# --------------------------------------------------------------------------- #
# Built-in hooks
# --------------------------------------------------------------------------- #
@register
class SerializeXPathMapAndNodeHook:
    """
    Serialize XPathMap and XPathNode objects to plain Python types.
    This is enabled by default (once this module is imported).
    """
    def post_extract(self, value):
        if isinstance(value, (list, tuple, set)):
            return type(value)(self.post_extract(v) for v in value)
        if isinstance(value, XPathMap):
            return {k: self.post_extract(v) for k, v in value.items()}
        if isinstance(value, XPathNode):
            return self.post_extract(value.obj)
        return value
