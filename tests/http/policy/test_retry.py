import pytest

from wxpath.http.policy.retry import RetryPolicy
from wxpath.http.client.request import Request


class DummyResponse:
    def __init__(self, status):
        self.status = status


def test_retry_on_exception():
    policy = RetryPolicy(max_retries=3)
    req = Request("http://example.com")

    assert policy.should_retry(req, exception=RuntimeError())


def test_retry_on_status():
    policy = RetryPolicy(retry_statuses={500})
    req = Request("http://example.com")

    assert policy.should_retry(req, response=DummyResponse(500))
    assert not policy.should_retry(req, response=DummyResponse(200))


def test_retry_stops_at_max():
    policy = RetryPolicy(max_retries=1)
    req = Request("http://example.com")
    req.retries = 1

    assert not policy.should_retry(req)


def test_backoff_increases():
    policy = RetryPolicy()
    req = Request("http://example.com")

    d1 = policy.get_delay(req)
    req.retries += 1
    d2 = policy.get_delay(req)

    assert d2 > d1