import asyncio
from abc import ABC, abstractmethod
from collections import defaultdict

from wxpath.util.logging import get_logger

log = get_logger(__name__)


# Abstract Base Class
class AbstractThrottler(ABC):
    @abstractmethod
    async def wait(self, host: str):
        pass

    @abstractmethod
    def record_latency(self, host: str, latency: float):
        pass


class AutoThrottler(AbstractThrottler):
    """
    Scrapy-inspired auto-throttle, simplified:
    - increases delay when latency increases
    - decreases delay when responses are fast

    Explanation: 
    - target_concurrency is the desired number of concurrent requests
    - start_delay is the initial delay
    - max_delay is the maximum delay
    - smoothing is the exponential smoothing factor
    """

    def __init__(
        self,
        start_delay: float = 0.25,
        max_delay: float = 10.0,
        target_concurrency: float = 1.0,
        smoothing: float = 0.7,
    ):
        self.start_delay = start_delay
        self.max_delay = max_delay
        self.target_concurrency = target_concurrency
        self.smoothing = smoothing

        self._delay = defaultdict(lambda: start_delay)
        self._latency = defaultdict(lambda: None)

    def record_latency(self, host: str, latency: float):
        prev = self._latency[host]
        if prev is None:
            self._latency[host] = latency
        else:
            self._latency[host] = (
                # exponential smoothing
                self.smoothing * prev + (1 - self.smoothing) * latency
            )

        self._recalculate_delay(host)

    def _recalculate_delay(self, host: str):
        latency = self._latency[host]
        if not latency:
            return

        target_delay = latency / self.target_concurrency
        delay = min(self.max_delay, max(0.0, target_delay))
        self._delay[host] = delay

        log.debug(
            "auto-throttle",
            extra={"host": host, "latency": latency, "delay": delay},
        )

    async def wait(self, host: str):
        delay = self._delay[host]
        if delay > 0:
            await asyncio.sleep(delay)


class ImpoliteThrottle(AbstractThrottler):
    """
    Zero delay throttler
    """

    async def wait(self, host: str):
        pass

    def record_latency(self, host: str, latency: float):
        pass


ZeroWaitThrottler = ImpoliteThrottle


class SimpleThrottler(AbstractThrottler):
    """
    Fixed delay throttler. Optionally provide per-host delays via `per_host_delays`.
    """
    def __init__(self, delay: float, per_host_delays: dict[str, float] = None):
        self.delay = delay
        self._delays = per_host_delays or defaultdict(lambda: delay)

    async def wait(self, host: str):
        if host in self._delays:
            await asyncio.sleep(self._delays[host])
        else:
            await asyncio.sleep(self.delay)
    
    def record_latency(self, host: str, latency: float):
        pass


FixedDelayThrottler = SimpleThrottler