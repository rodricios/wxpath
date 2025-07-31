# """
# wxpath.hooks
# ============

# Pluggable hook system for wxpath.

# Write once:

#     from wxpath import hooks

#     @hooks.register
#     class OnlyEnglish:
#         def post_parse(self, ctx, elem):
#             lang = elem.xpath('string(/html/@lang)').lower()[:2]
#             return elem if lang in ("en", "") else None

# ... and wxpath.core will call it automatically.
# """

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, List, Optional, Any

from lxml import html


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
    # def post_extract(self, value: Any, ctx: FetchContext) -> Any: ...


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
    _global_hooks.append(hook)
    return hook


def get_hooks() -> List[Hook]:
    """Return the list of globally-registered hooks (read-only)."""
    return list(_global_hooks)
