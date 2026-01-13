"""
Pluggable hook system for wxpath.

Write once:

    from wxpath import hooks

    @hooks.register
    class OnlyEnglish:
        def post_parse(self, ctx, elem):
            lang = elem.xpath('string(/html/@lang)').lower()[:2]
            return elem if lang in ("en", "") else None

... and wxpath.engine will call it automatically.
"""

from __future__ import annotations

import functools
from collections.abc import Generator
from dataclasses import dataclass, field
from typing import Any, Iterable, List, Optional, Protocol

from lxml import html

from wxpath.util.logging import get_logger

log = get_logger(__name__)


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
_global_hooks: dict[str, Hook] = dict()


def register(hook: Hook | type) -> Hook:
    """Decorator/helper to add a Hook to the global list.

    Args:
        hook: A Hook class or instance to register.

    Returns:
        The registered hook (instantiated if a class was provided).

    Example:
        >>> @register
        ... class DebugHook:
        ...     def post_fetch(self, ctx, html_bytes):
        ...         print("Fetched", ctx.url)
        ...         return html_bytes
    """

    hook_name = getattr(hook, '__name__', hook.__class__.__name__)
    if hook_name in _global_hooks:
        return hook

    instance = hook() if isinstance(hook, type) else hook
    _global_hooks[hook_name] = instance
    return hook


def get_hooks() -> List[Hook]:
    """Return the list of globally-registered hooks (read-only)."""
    return list(_global_hooks.values())


def iter_post_extract_hooks() -> Iterable[Hook]:
    yield from (h for h in _global_hooks.values() if hasattr(h, "post_extract"))


def pipe_post_extract(gen_func):
    """Wrap a generator function to pipe yielded values through post_extract hooks.

    Args:
        gen_func: A generator function to wrap.

    Returns:
        A wrapped generator that filters values through registered hooks.
    """
    @functools.wraps(gen_func)
    def wrapper(*args, **kwargs) -> Generator:
        for item in gen_func(*args, **kwargs):
            for hook in iter_post_extract_hooks():
                item = hook.post_extract(item)
                if item is None:       # hook decided to drop it
                    break
            if item is not None:
                yield item
    return wrapper


def pipe_post_extract_async(async_gen_func):
    """Wrap an async generator function to pipe yielded values through hooks.

    Args:
        async_gen_func: An async generator function to wrap.

    Returns:
        A wrapped async generator that filters values through registered hooks.
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
