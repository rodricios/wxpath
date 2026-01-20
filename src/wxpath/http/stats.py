"""
aiohttp request statistics and tracing hooks.
"""

import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Optional

from aiohttp import TraceConfig


@dataclass
class CrawlerStats:
    # ---- Lifecycle counts ----
    requests_enqueued: int = 0
    requests_started: int = 0
    requests_completed: int = 0
    requests_cache_hit: int = 0

    # ---- Concurrency ----
    in_flight_global: int = 0
    in_flight_per_host: defaultdict[str, int] = field(default_factory=lambda: defaultdict(int))

    # ---- Queueing ----
    queue_size: int = 0
    queue_wait_time_total: float = 0.0

    # ---- Throttling ----
    throttle_waits: int = 0
    throttle_wait_time: float = 0.0
    throttle_waits_by_host: defaultdict[str, int] = field(default_factory=lambda: defaultdict(int))

    # ---- Latency feedback ----
    latency_samples: int = 0
    latency_ewma: float = 0.0
    min_latency: Optional[float] = None
    max_latency: Optional[float] = None

    # ---- Errors / retries ----
    retries_scheduled: int = 0
    retries_executed: int = 0
    errors_by_host: defaultdict[str, int] = field(default_factory=lambda: defaultdict(int))


def build_trace_config(stats: CrawlerStats) -> TraceConfig:
    """
    Returns an aiohttp TraceConfig wired to the given stats instance.
    Tracks detailed per-request, per-host, and queue/throttle metrics.
    """
    trace = TraceConfig()

    async def on_request_start(session, context, params):
        stats.requests_started += 1
        stats.in_flight_global += 1
        host = params.url.host
        stats.in_flight_per_host[host] += 1
        context._start_time = time.monotonic()

    async def on_request_end(session, context, params):
        """
        Update stats on request completion.
        """
        host = params.url.host
        stats.in_flight_global -= 1
        stats.in_flight_per_host[host] -= 1

        latency = time.monotonic() - context._start_time
        stats.latency_samples += 1
        # EWMA update: alpha = 0.3
        alpha = 0.3
        stats.latency_ewma = (alpha * latency) + ((1 - alpha) * stats.latency_ewma)
        stats.min_latency = latency if stats.min_latency is None \
            else min(stats.min_latency, latency)
        stats.max_latency = latency if stats.max_latency is None \
            else max(stats.max_latency, latency)

        status = getattr(params.response, "status", None)
        if status is not None:
            if not hasattr(stats, "status_counts"):
                stats.status_counts = defaultdict(int)
            stats.status_counts[status] += 1

        content_length = getattr(params.response, "content_length", None)
        if content_length:
            if not hasattr(stats, "bytes_received"):
                stats.bytes_received = 0
            stats.bytes_received += content_length
        
        stats.requests_completed += 1

    async def on_request_exception(session, context, params):
        host = params.url.host
        stats.in_flight_global -= 1
        stats.in_flight_per_host[host] -= 1
        stats.errors_by_host[host] += 1

    trace.on_request_start.append(on_request_start)
    trace.on_request_end.append(on_request_end)
    trace.on_request_exception.append(on_request_exception)

    return trace
