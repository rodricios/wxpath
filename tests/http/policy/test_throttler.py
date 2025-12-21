import asyncio
import pytest

from wxpath.http.policy.throttler import AutoThrottler


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

@pytest.fixture
def fake_sleep(monkeypatch):
    """
    Monkeypatch asyncio.sleep so tests are fast and deterministic.
    Captures requested sleep durations.
    """
    sleeps = []

    async def _fake_sleep(delay):
        sleeps.append(delay)

    monkeypatch.setattr(asyncio, "sleep", _fake_sleep)
    return sleeps


# ---------------------------------------------------------------------------
# Unit tests: pure throttle math
# ---------------------------------------------------------------------------

def test_initial_delay_is_start_delay():
    t = AutoThrottler(start_delay=0.25)
    assert t._delay["example.com"] == 0.25


def test_record_latency_sets_initial_latency():
    t = AutoThrottler()
    t.record_latency("example.com", 1.0)

    assert t._latency["example.com"] == 1.0
    assert t._delay["example.com"] == 1.0  # latency / target_concurrency


def test_latency_is_exponentially_smoothed():
    t = AutoThrottler(smoothing=0.5)

    t.record_latency("example.com", 1.0)
    t.record_latency("example.com", 3.0)

    # smoothed = 0.5 * 1.0 + 0.5 * 3.0
    assert t._latency["example.com"] == pytest.approx(2.0)


def test_delay_increases_with_latency():
    t = AutoThrottler()

    t.record_latency("example.com", 0.5)
    d1 = t._delay["example.com"]

    t.record_latency("example.com", 1.0)
    d2 = t._delay["example.com"]

    assert d2 > d1


def test_delay_decreases_when_latency_drops():
    t = AutoThrottler(smoothing=0.0)  # no smoothing for determinism

    t.record_latency("example.com", 2.0)
    d1 = t._delay["example.com"]

    t.record_latency("example.com", 0.5)
    d2 = t._delay["example.com"]

    assert d2 < d1


def test_delay_is_scaled_by_target_concurrency():
    t = AutoThrottler(target_concurrency=2.0)

    t.record_latency("example.com", 2.0)

    # delay = latency / concurrency
    assert t._delay["example.com"] == 1.0


def test_delay_is_never_negative():
    t = AutoThrottler()

    t.record_latency("example.com", 0.0)

    assert t._delay["example.com"] >= 0.0


def test_delay_is_capped_by_max_delay():
    t = AutoThrottler(max_delay=1.0)

    t.record_latency("example.com", 10.0)

    assert t._delay["example.com"] == 1.0


# ---------------------------------------------------------------------------
# Async behavior tests (wait)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_wait_sleeps_for_current_delay(fake_sleep):
    t = AutoThrottler(start_delay=0.3)

    await t.wait("example.com")

    assert fake_sleep == [0.3]


@pytest.mark.asyncio
async def test_wait_uses_updated_delay(fake_sleep):
    t = AutoThrottler()

    t.record_latency("example.com", 0.8)

    await t.wait("example.com")

    assert fake_sleep == [0.8]


@pytest.mark.asyncio
async def test_wait_does_not_sleep_when_delay_is_zero(fake_sleep):
    t = AutoThrottler(start_delay=0.0)

    await t.wait("example.com")

    assert fake_sleep == []


# ---------------------------------------------------------------------------
# Multi-host isolation
# ---------------------------------------------------------------------------

def test_hosts_are_tracked_independently():
    t = AutoThrottler()

    t.record_latency("a.com", 1.0)
    t.record_latency("b.com", 0.2)

    assert t._delay["a.com"] != t._delay["b.com"]
    assert t._delay["a.com"] == 1.0
    assert t._delay["b.com"] == 0.2


@pytest.mark.asyncio
async def test_wait_only_affects_requested_host(fake_sleep):
    t = AutoThrottler()

    t.record_latency("a.com", 1.0)
    t.record_latency("b.com", 0.2)

    await t.wait("b.com")

    assert fake_sleep == [0.2]


# ---------------------------------------------------------------------------
# Regression / stability tests
# ---------------------------------------------------------------------------

def test_multiple_updates_do_not_exceed_max_delay():
    t = AutoThrottler(max_delay=2.0)

    for _ in range(10):
        t.record_latency("example.com", 10.0)

    assert t._delay["example.com"] == 2.0


def test_latency_none_does_not_crash():
    t = AutoThrottler()
    # internal default latency is None
    assert t._latency["example.com"] is None
    # accessing delay should still work
    assert t._delay["example.com"] == t.start_delay