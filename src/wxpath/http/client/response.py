# wxpath/http/response.py
from dataclasses import dataclass, field
from typing import Optional

from wxpath.http.client.request import Request


@dataclass
class Response:
    request: Request
    status: int
    body: bytes
    headers: dict | None = None
    error: Optional[Exception] = field(default=None, kw_only=True)
