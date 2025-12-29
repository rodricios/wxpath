import time
from dataclasses import dataclass, field
from typing import Any, Dict


@dataclass
class Request:
    url: str
    method: str = "GET"
    headers: Dict[str, str] = field(default_factory=dict)
    timeout: float = 15.0

    retries: int = 0
    max_retries: int | None = None
    dont_retry: bool = False

    meta: Dict[str, Any] = field(default_factory=dict)

    created_at: float = field(default_factory=time.monotonic)

    def copy_for_retry(self) -> "Request":
        return Request(
            url=self.url,
            method=self.method,
            headers=self.headers,
            timeout=self.timeout,
            retries=self.retries + 1,
            max_retries=self.max_retries,
            meta=self.meta,
        )
    
    @property
    def hostname(self) -> str:
        from urllib.parse import urlsplit
        return urlsplit(self.url).hostname or ""