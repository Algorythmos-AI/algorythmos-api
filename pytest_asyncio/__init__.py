"""Minimal local implementation of pytest-asyncio for offline test runs."""
from __future__ import annotations

import asyncio
import inspect
from collections.abc import Callable, Generator
from functools import wraps
from typing import Any, TypeVar, overload

import pytest

F = TypeVar("F", bound=Callable[..., Any])


@overload
def fixture(__func: F, /) -> F:  # pragma: no cover - typing overload
    ...


@overload
def fixture(*args: Any, **kwargs: Any) -> Callable[[F], F]:  # pragma: no cover - typing overload
    ...


def fixture(*decorator_args: Any, **decorator_kwargs: Any):
    """Replacement for :func:`pytest_asyncio.fixture` using local asyncio loops."""

    if decorator_args and callable(decorator_args[0]) and len(decorator_args) == 1 and not decorator_kwargs:
        func = decorator_args[0]
        return fixture()(func)

    def decorator(func: F) -> F:
        sig = inspect.signature(func)

        if inspect.isasyncgenfunction(func):
            @wraps(func)
            def wrapper(*args: Any, **kwargs: Any) -> Generator[Any, None, None]:
                loop = asyncio.new_event_loop()
                try:
                    asyncio.set_event_loop(loop)
                    agen = func(*args, **kwargs)
                    try:
                        value = loop.run_until_complete(agen.__anext__())
                    except StopAsyncIteration as exc:  # pragma: no cover - defensive
                        raise RuntimeError("Async fixture must yield") from exc
                    try:
                        yield value
                    finally:
                        try:
                            loop.run_until_complete(agen.__anext__())
                        except StopAsyncIteration:
                            pass
                        loop.run_until_complete(agen.aclose())
                finally:
                    asyncio.set_event_loop(None)
                    loop.close()

            wrapper.__signature__ = sig  # type: ignore[attr-defined]
            return pytest.fixture(*decorator_args, **decorator_kwargs)(wrapper)  # type: ignore[return-value]

        if inspect.iscoroutinefunction(func):
            @wraps(func)
            def wrapper(*args: Any, **kwargs: Any) -> Any:
                loop = asyncio.new_event_loop()
                try:
                    asyncio.set_event_loop(loop)
                    return loop.run_until_complete(func(*args, **kwargs))
                finally:
                    asyncio.set_event_loop(None)
                    loop.close()

            wrapper.__signature__ = sig  # type: ignore[attr-defined]
            return pytest.fixture(*decorator_args, **decorator_kwargs)(wrapper)  # type: ignore[return-value]

        return pytest.fixture(*decorator_args, **decorator_kwargs)(func)  # type: ignore[return-value]

    return decorator


def _should_run_async(pyfuncitem: pytest.Function) -> bool:
    if inspect.iscoroutinefunction(pyfuncitem.obj):
        return True
    if pyfuncitem.get_closest_marker("asyncio") is not None:
        return True
    if pyfuncitem.get_closest_marker("anyio") is not None:
        return True
    return False


def pytest_pyfunc_call(pyfuncitem: pytest.Function) -> bool | None:
    if not _should_run_async(pyfuncitem):
        return None

    testfunction = pyfuncitem.obj
    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        sig = inspect.signature(testfunction)
        allowed = set(sig.parameters)
        call_kwargs = {name: value for name, value in pyfuncitem.funcargs.items() if name in allowed}
        result = testfunction(**call_kwargs)
        if inspect.isawaitable(result):
            loop.run_until_complete(result)
        return True
    finally:
        asyncio.set_event_loop(None)
        loop.close()


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "asyncio: run test inside an asyncio event loop")
    config.addinivalue_line("markers", "anyio: run test inside an asyncio event loop")
