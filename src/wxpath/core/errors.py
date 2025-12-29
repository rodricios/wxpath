
import collections.abc as cabc
import functools
import inspect
import types
from contextlib import contextmanager
from contextvars import ContextVar
from enum import Enum, auto
from typing import AsyncGenerator

from wxpath.util.logging import get_logger

log = get_logger(__name__)

class ErrorPolicy(Enum):
    IGNORE  = auto()   # swallow completely
    LOG     = auto()   # just log at ERROR
    COLLECT = auto()   # yield {"_error": ..., "_ctx": ...}
    RAISE   = auto()   # re-raise


_GLOBAL_DEFAULT = ErrorPolicy.LOG

# Task-local override (None => fall back to _GLOBAL_DEFAULT)
_CURRENT: ContextVar[ErrorPolicy | None] = ContextVar("wx_err_policy", default=None)


def get_current_error_policy() -> ErrorPolicy:
    return _CURRENT.get() or _GLOBAL_DEFAULT


def set_default_error_policy(policy: ErrorPolicy) -> None:
    global _GLOBAL_DEFAULT
    _GLOBAL_DEFAULT = policy


@contextmanager
def use_error_policy(policy: ErrorPolicy):
    token = _CURRENT.set(policy)
    try:
        yield
    finally:
        _CURRENT.reset(token)
        

def handle_error(exc: Exception, policy: ErrorPolicy, ctx: dict):
    if policy is ErrorPolicy.IGNORE:
        return None

    if policy is ErrorPolicy.LOG:
        log.exception("processing error", extra=ctx)
        return None

    if policy is ErrorPolicy.COLLECT:
        return {"_error": str(exc), "_ctx": ctx}

    # RAISE (safe default)
    raise exc


def _is_gen(obj):     # helper
    return isinstance(obj, (types.GeneratorType, cabc.Generator))


def with_errors():
    """
    Apply the current ErrorPolicy at call time while preserving the callable kind:
      - async generator -> async generator wrapper
      - coroutine       -> async wrapper
      - sync generator  -> sync generator wrapper
      - plain function  -> plain wrapper
    """
    def decorator(fn):
        # --- ASYNC GENERATOR ---
        if inspect.isasyncgenfunction(fn):
            @functools.wraps(fn)
            async def asyncgen_wrapped(*a, **kw) -> AsyncGenerator:
                try:
                    async for item in fn(*a, **kw):
                        yield item
                except Exception as exc:
                    collected = handle_error(exc, get_current_error_policy(),
                                             _ctx_from_sig(fn, a, kw))
                    if collected is not None:
                        yield collected
            return asyncgen_wrapped

        # --- COROUTINE ---
        if inspect.iscoroutinefunction(fn):
            @functools.wraps(fn)
            async def coro_wrapped(*a, **kw):
                try:
                    return await fn(*a, **kw)
                except Exception as exc:
                    return handle_error(exc, get_current_error_policy(),
                                        _ctx_from_sig(fn, a, kw))
            return coro_wrapped

        # --- SYNC GENERATOR ---
        if inspect.isgeneratorfunction(fn):
            @functools.wraps(fn)
            def gen_wrapped(*a, **kw):
                try:
                    for item in fn(*a, **kw):
                        yield item
                except Exception as exc:
                    collected = handle_error(exc, get_current_error_policy(),
                                             _ctx_from_sig(fn, a, kw))
                    if collected is not None:
                        yield collected
            return gen_wrapped

        # --- PLAIN SYNC FUNCTION ---
        @functools.wraps(fn)
        def plain_wrapped(*a, **kw):
            try:
                return fn(*a, **kw)
            except Exception as exc:
                return handle_error(exc, get_current_error_policy(),
                                    _ctx_from_sig(fn, a, kw))
        return plain_wrapped
    return decorator


def _ctx_from_sig(fn, a, kw):
    """Best-effort extraction of depth/url/op for logging."""
    # you already pass these in every handler, so pull by position
    try:
        elem, segs, depth, *_ = a
        op, val = segs[0] if segs else ("?", "?")
        url = getattr(elem, "base_url", None)
        return {"op": op, "depth": depth, "url": url}
    except Exception:
        return {}