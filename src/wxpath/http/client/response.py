# wxpath/http/response.py
from dataclasses import dataclass

from wxpath.http.client.request import Request

@dataclass
class Response:
    request: Request
    status: int
    body: bytes
    headers: dict | None = None