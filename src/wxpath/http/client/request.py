import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Request:
    """HTTP request envelope used by the crawler."""
    url: str
    method: str = "GET"
    headers: dict[str, str] = field(default_factory=dict)
    timeout: float | None = None

    retries: int = 0
    max_retries: int | None = None
    dont_retry: bool = False

    meta: dict[str, Any] = field(default_factory=dict)

    created_at: float = field(default_factory=time.monotonic)

    def copy_for_retry(self) -> "Request":
        """Create a copy incrementing the retry counter for scheduling."""
        return Request(
            url=self.url,
            method=self.method,
            headers=self.headers,
            timeout=self.timeout,
            retries=self.retries + 1,
            max_retries=self.max_retries,
            dont_retry=self.dont_retry,
            meta=self.meta,
        )
    
    @property
    def hostname(self) -> str:
        from urllib.parse import urlsplit
        return urlsplit(self.url).hostname or ""