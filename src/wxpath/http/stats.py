"""
aiohttp request statistics and tracing hooks.
"""

import time
from aiohttp import TraceConfig


def build_stats():
    return {
        "total_requests": 0,
        "total_time": 0.0,
        "in_flight": 0,
        "status_counts": {},
        "error_count": 0,
        "bytes_received": 0,
        "min_latency": None,
        "max_latency": None,
    }


# ─────────────────────────────────────────────────────────────
# Trace hooks (MUST be async — aiohttp will await them)
# ─────────────────────────────────────────────────────────────

async def on_request_start(session, context, params, request_stats: dict):
    context.start_time = time.monotonic()
    request_stats["total_requests"] += 1
    request_stats["in_flight"] += 1


async def on_request_end(session, context, params, request_stats: dict):
    latency = time.monotonic() - context.start_time
    request_stats["total_time"] += latency
    request_stats["in_flight"] -= 1

    status = getattr(params.response, "status", None)
    if status is not None:
        request_stats["status_counts"][status] = (
            request_stats["status_counts"].get(status, 0) + 1
        )

    content_length = getattr(params.response, "content_length", None)
    if content_length:
        request_stats["bytes_received"] += content_length

    if request_stats["min_latency"] is None or latency < request_stats["min_latency"]:
        request_stats["min_latency"] = latency

    if request_stats["max_latency"] is None or latency > request_stats["max_latency"]:
        request_stats["max_latency"] = latency


async def on_request_exception(session, context, params, request_stats: dict):
    request_stats["error_count"] += 1
    request_stats["in_flight"] -= 1


# ─────────────────────────────────────────────────────────────
# TraceConfig builder
# ─────────────────────────────────────────────────────────────

def build_trace_config(request_stats: dict) -> TraceConfig:
    """
    Build an aiohttp TraceConfig wired to the given stats dict.

    IMPORTANT:
    aiohttp awaits all trace callbacks, so we must only register
    async callables here.
    """
    trace_config = TraceConfig()

    async def _on_start(s, c, p):
        await on_request_start(s, c, p, request_stats)

    async def _on_end(s, c, p):
        await on_request_end(s, c, p, request_stats)

    async def _on_exc(s, c, p):
        await on_request_exception(s, c, p, request_stats)

    trace_config.on_request_start.append(_on_start)
    trace_config.on_request_end.append(_on_end)
    trace_config.on_request_exception.append(_on_exc)

    return trace_config