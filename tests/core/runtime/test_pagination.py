"""Browser pagination from a wxpath expression through the crawler."""

from __future__ import annotations

import asyncio
import sys
from types import ModuleType, SimpleNamespace

import pytest

from wxpath.core.parser import Click, Pages, Paginate, Xpath, parse
from wxpath.core.runtime.engine import WXPathEngine
from wxpath.http.client.crawler import Crawler, PlaywrightCrawler
from wxpath.http.policy.throttler import ImpoliteThrottle


class FakeControl:
    def __init__(self, page: FakePage) -> None:
        self.page = page
        self.first = self

    async def count(self) -> int:
        return int(self.page.index < len(self.page.pages) - 1)

    async def is_visible(self) -> bool:
        return True

    async def is_enabled(self) -> bool:
        return True

    async def click(self, **kwargs) -> None:
        if self.page.fail_click:
            raise RuntimeError('browser click failed')
        self.page.index += 1


class FakePage:
    def __init__(self, pages: list[str]) -> None:
        self.pages = pages
        self.index = 0
        self.fail_click = False
        self.clicked_xpath: list[str] = []

    @property
    def url(self) -> str:
        return 'https://example.test/page/1'

    async def goto(self, url: str, **kwargs) -> SimpleNamespace:
        return SimpleNamespace(status=200, headers={})

    async def wait_for_load_state(self, state: str, **kwargs) -> None:
        return None

    async def content(self) -> str:
        return self.pages[self.index]

    async def evaluate(self, expression: str) -> str:
        return self.pages[self.index]

    async def wait_for_function(self, expression: str, *, arg: str, **kwargs) -> None:
        if self.pages[self.index] == arg:
            raise TimeoutError('page did not change')

    def locator(self, xpath: str) -> FakeControl:
        self.clicked_xpath.append(xpath)
        return FakeControl(self)


class FakeContext:
    def __init__(self, page: FakePage) -> None:
        self.page = page
        self.closed = False

    async def new_page(self) -> FakePage:
        return self.page

    async def close(self) -> None:
        self.closed = True


class FakeBrowser:
    def __init__(self, context: FakeContext) -> None:
        self.context = context

    async def new_context(self, **kwargs) -> FakeContext:
        return self.context


class FakePlaywrightCrawler(PlaywrightCrawler):
    def __init__(self, pages: list[str]) -> None:
        super().__init__(concurrency=1, respect_robots=False, throttler=ImpoliteThrottle())
        self.page = FakePage(pages)
        self.context = FakeContext(self.page)

    async def __aenter__(self) -> FakePlaywrightCrawler:
        self._browser = FakeBrowser(self.context)
        self._workers = [asyncio.create_task(self._worker())]
        return self

    async def __aexit__(self, *args) -> None:
        self._closed = True
        for worker in self._workers:
            worker.cancel()
        await asyncio.gather(*self._workers, return_exceptions=True)


def _install_fake_playwright(monkeypatch: pytest.MonkeyPatch) -> None:
    module = ModuleType('playwright.async_api')
    module.TimeoutError = TimeoutError
    monkeypatch.setitem(sys.modules, 'playwright', ModuleType('playwright'))
    monkeypatch.setitem(sys.modules, 'playwright.async_api', module)


def test_parse_paginate_with_map_and_nested_xpath() -> None:
    expression = (
        "url('https://example.test')"
        "//wx:paginate(//tr/map{'name':string(td[1]),'score':string(td[2])},"
        "click=//a[@aria-label='Next'],pages=3)"
    )
    segments = parse(expression)

    assert isinstance(segments[1], Paginate)
    assert segments[1].args == [
        Xpath("//tr/map{'name':string(td[1]),'score':string(td[2])}"),
        Click("//a[@aria-label='Next']"),
        Pages(3),
    ]


@pytest.mark.parametrize(
    'limit,expected',
    [(3, ['one', 'two', 'three']), (2, ['one', 'two']), (5, ['one', 'two', 'three'])],
)
@pytest.mark.asyncio
async def test_paginate_streams_once_per_page(
    monkeypatch: pytest.MonkeyPatch, limit: int, expected: list[str]
) -> None:
    _install_fake_playwright(monkeypatch)
    crawler = FakePlaywrightCrawler(
        [f'<html><body><li>{name}</li></body></html>' for name in ['one', 'two', 'three']]
    )
    engine = WXPathEngine(crawler=crawler)
    expression = (
        "url('https://example.test/page/1')"
        "//wx:paginate(//li/text(),click=//a[@id='next'],pages="
        f'{limit})'
    )

    rows = [str(row) async for row in engine.run(expression, max_depth=0)]

    assert rows == expected
    assert crawler.context.closed
    assert all(xpath == "xpath=//a[@id='next']" for xpath in crawler.page.clicked_xpath)


@pytest.mark.asyncio
async def test_paginate_rejects_non_browser_crawler() -> None:
    engine = WXPathEngine(crawler=Crawler(respect_robots=False))
    expression = "url('https://example.test')//wx:paginate(//li,click=//a,pages=2)"

    with pytest.raises(ValueError, match='requires a PlaywrightCrawler'):
        async for _ in engine.run(expression, max_depth=0):
            pass


@pytest.mark.asyncio
async def test_paginate_preserves_first_page_when_next_click_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fake_playwright(monkeypatch)
    crawler = FakePlaywrightCrawler(['<html><li>one</li></html>', '<html><li>two</li></html>'])
    crawler.page.fail_click = True
    engine = WXPathEngine(crawler=crawler)
    expression = "url('https://example.test')//wx:paginate(//li/text(),click=//a,pages=2)"

    rows = [row async for row in engine.run(expression, max_depth=0, yield_errors=True)]

    assert str(rows[0]) == 'one'
    assert rows[1]['reason'] == 'network_error'
    assert 'browser click failed' in rows[1]['exception']
    assert crawler.context.closed


@pytest.mark.asyncio
async def test_paginate_stops_when_click_does_not_change_page(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fake_playwright(monkeypatch)
    crawler = FakePlaywrightCrawler(['<html><li>one</li></html>'] * 2)
    engine = WXPathEngine(crawler=crawler)
    expression = "url('https://example.test')//wx:paginate(//li/text(),click=//a,pages=5)"

    rows = [str(row) async for row in engine.run(expression, max_depth=0)]

    assert rows == ['one']
    assert crawler.context.closed


@pytest.mark.parametrize('option', ['pages=0', 'pages=nope', 'click=', 'pages=2'])
def test_parse_paginate_rejects_invalid_options(option: str) -> None:
    expression = f"url('https://example.test')//wx:paginate(//li,{option})"
    with pytest.raises((SyntaxError, ValueError)):
        parse(expression)
