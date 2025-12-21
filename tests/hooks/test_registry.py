import pytest
import asyncio

from wxpath.hooks.registry import (
    register,
    get_hooks,
    pipe_post_extract,
    pipe_post_extract_async,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def clear_global_hooks():
    """
    Registry is module-global; tests must isolate state.
    """
    from wxpath.hooks import registry
    registry._global_hooks.clear()


@pytest.fixture(autouse=True)
def _isolate_registry():
    clear_global_hooks()
    yield
    clear_global_hooks()


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

def test_register_class_creates_instance():
    @register
    class MyHook:
        def post_extract(self, value):
            return value

    hooks = get_hooks()
    assert len(hooks) == 1
    assert isinstance(hooks[0], MyHook)


def test_register_instance():
    class MyHook:
        def post_extract(self, value):
            return value

    hook = MyHook()
    register(hook)

    hooks = get_hooks()
    assert hooks == [hook]


def test_register_is_idempotent_by_name():
    @register
    class MyHook:
        def post_extract(self, value):
            return value

    # Register again
    register(MyHook)

    hooks = get_hooks()
    assert len(hooks) == 1


# ---------------------------------------------------------------------------
# pipe_post_extract (sync)
# ---------------------------------------------------------------------------

def test_pipe_post_extract_pass_through():
    @register
    class IdentityHook:
        def post_extract(self, value):
            return value

    @pipe_post_extract
    def gen():
        yield 1
        yield 2

    assert list(gen()) == [1, 2]


def test_pipe_post_extract_transforms_value():
    @register
    class DoubleHook:
        def post_extract(self, value):
            return value * 2

    @pipe_post_extract
    def gen():
        yield 1
        yield 3

    assert list(gen()) == [2, 6]


def test_pipe_post_extract_multiple_hooks_in_order():
    calls = []

    @register
    class HookA:
        def post_extract(self, value):
            calls.append("A")
            return value + 1

    @register
    class HookB:
        def post_extract(self, value):
            calls.append("B")
            return value * 10

    @pipe_post_extract
    def gen():
        yield 1

    assert list(gen()) == [20]
    assert calls == ["A", "B"]


def test_pipe_post_extract_drop_value():
    @register
    class Dropper:
        def post_extract(self, value):
            return None

    @pipe_post_extract
    def gen():
        yield 1
        yield 2

    assert list(gen()) == []


def test_pipe_post_extract_partial_drop():
    @register
    class DropOdds:
        def post_extract(self, value):
            return None if value % 2 else value

    @pipe_post_extract
    def gen():
        yield 1
        yield 2
        yield 3
        yield 4

    assert list(gen()) == [2, 4]


# ---------------------------------------------------------------------------
# pipe_post_extract_async
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_pipe_post_extract_async_basic():
    @register
    class AddOne:
        def post_extract(self, value):
            return value + 1

    @pipe_post_extract_async
    async def agen():
        yield 1
        yield 2

    results = [v async for v in agen()]
    assert results == [2, 3]


@pytest.mark.asyncio
async def test_pipe_post_extract_async_drop():
    @register
    class DropAll:
        def post_extract(self, value):
            return None

    @pipe_post_extract_async
    async def agen():
        yield 1
        yield 2

    results = [v async for v in agen()]
    assert results == []


@pytest.mark.asyncio
async def test_pipe_post_extract_async_order():
    order = []

    @register
    class HookA:
        def post_extract(self, value):
            order.append("A")
            return value + 1

    @register
    class HookB:
        def post_extract(self, value):
            order.append("B")
            return value * 2

    @pipe_post_extract_async
    async def agen():
        yield 1

    results = [v async for v in agen()]
    assert results == [4]
    assert order == ["A", "B"]