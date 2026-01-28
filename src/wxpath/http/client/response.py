from dataclasses import dataclass, field
from typing import Optional

from wxpath.http.client.request import Request


@dataclass
class Response:
    request: Request
    status: int
    body: bytes
    headers: dict[str, str] | None = None
    error: Optional[Exception] = field(default=None, kw_only=True)

    request_start: float | None = None
    response_end: float | None = None

    @property
    def latency(self) -> float:
        return self.response_end - self.request_start
