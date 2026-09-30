"""Browser smoke test for click pagination against a local HTTP server."""

from __future__ import annotations

import asyncio
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from wxpath.core.runtime.engine import WXPathEngine
from wxpath.http.client.crawler import PlaywrightCrawler


class PageHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path == '/one':
            body = b"<html><body><li>one</li><a id='next' href='/two'>Next</a></body></html>"
        elif self.path == '/two':
            body = b'<html><body><li>two</li></body></html>'
        else:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header('Content-Type', 'text/html')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args) -> None:
        return None


@pytest.mark.asyncio
async def test_browser_click_pagination_against_local_pages() -> None:
    pytest.importorskip('playwright.async_api')
    pytest.importorskip('playwright_stealth')

    server = ThreadingHTTPServer(('127.0.0.1', 0), PageHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        url = f'http://127.0.0.1:{server.server_port}/one'
        expression = f"url('{url}')//wx:paginate(//li/text(),click=//a[@id='next'],pages=3)"
        crawler = PlaywrightCrawler(concurrency=1, per_host=1, respect_robots=False)
        engine = WXPathEngine(crawler=crawler)

        rows = await asyncio.wait_for(_collect(engine.run(expression, max_depth=0)), timeout=30)

        assert [str(row) for row in rows] == ['one', 'two']
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


async def _collect(results):
    return [row async for row in results]
