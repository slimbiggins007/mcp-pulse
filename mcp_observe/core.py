"""Core observability wrapper for MCP servers.

Two ways to use:

    # Option 1: Drop-in replacement (recommended)
    from mcp_observe import ObserveMCP
    mcp = ObserveMCP("my-server")

    # Option 2: Wrap an existing server
    from mcp.server.fastmcp import FastMCP
    from mcp_observe import observe
    mcp = FastMCP("my-server")
    observe(mcp)
"""

from __future__ import annotations

import functools
import inspect
import json
import time
from typing import Any, Callable

from mcp.server.fastmcp import FastMCP

from mcp_observe.models import ToolCallEvent
from mcp_observe.storage import Storage


class ObserveMCP(FastMCP):
    """FastMCP subclass that automatically instruments every tool.

    Usage:
        mcp = ObserveMCP("my-server")

        @mcp.tool()
        def my_tool(param: str) -> str:
            ...  # automatically tracked

        mcp.run(transport="stdio")
    """

    def __init__(
        self,
        name: str = "",
        *,
        db_path: str | None = None,
        log_params: bool = False,
        **kwargs: Any,
    ) -> None:
        super().__init__(name, **kwargs)
        self._observe_storage = Storage(db_path)
        self._observe_server_name = name
        self._observe_log_params = log_params

    def tool(self, *args: Any, **kwargs: Any) -> Callable:
        parent_decorator = super().tool(*args, **kwargs)

        def wrapper(func: Callable) -> Callable:
            instrumented = _wrap_function(
                func,
                storage=self._observe_storage,
                server_name=self._observe_server_name,
                log_params=self._observe_log_params,
            )
            return parent_decorator(instrumented)

        return wrapper


def observe(
    server: FastMCP,
    *,
    db_path: str | None = None,
    log_params: bool = False,
) -> FastMCP:
    """Patch an existing FastMCP server to add observability.

    Usage:
        mcp = FastMCP("my-server")

        @mcp.tool()
        def my_tool(param: str) -> str:
            ...

        observe(mcp)  # instruments all registered tools
        mcp.run(transport="stdio")
    """
    storage = Storage(db_path)
    server_name = server.name

    # Wrap the tool() method so future registrations are also tracked
    original_tool = server.tool

    def observed_tool(*args: Any, **kwargs: Any) -> Callable:
        parent_decorator = original_tool(*args, **kwargs)

        def wrapper(func: Callable) -> Callable:
            instrumented = _wrap_function(
                func,
                storage=storage,
                server_name=server_name,
                log_params=log_params,
            )
            return parent_decorator(instrumented)

        return wrapper

    server.tool = observed_tool  # type: ignore[method-assign]

    # Also wrap any already-registered tools
    _patch_existing_tools(server, storage, server_name, log_params)

    return server


def _wrap_function(
    func: Callable,
    *,
    storage: Storage,
    server_name: str,
    log_params: bool,
) -> Callable:
    """Wrap a tool function with timing and logging."""

    if inspect.iscoroutinefunction(func):

        @functools.wraps(func)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            return await _execute_and_log(
                func, args, kwargs, storage, server_name, log_params, is_async=True
            )

        return async_wrapper

    @functools.wraps(func)
    def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
        return _run_sync_and_log(
            func, args, kwargs, storage, server_name, log_params
        )

    return sync_wrapper


def _run_sync_and_log(
    func: Callable,
    args: tuple,
    kwargs: dict,
    storage: Storage,
    server_name: str,
    log_params: bool,
) -> Any:
    """Execute a sync function and log the result."""
    start = time.perf_counter()
    error_msg = None
    success = True
    result = None

    try:
        result = func(*args, **kwargs)
        return result
    except Exception as e:
        success = False
        error_msg = f"{type(e).__name__}: {e}"
        raise
    finally:
        duration_ms = (time.perf_counter() - start) * 1000
        params_json = None
        if log_params and kwargs:
            try:
                params_json = json.dumps(kwargs, default=str)
            except (TypeError, ValueError):
                params_json = None

        event = ToolCallEvent(
            tool_name=func.__name__,
            timestamp=ToolCallEvent.now_iso(),
            duration_ms=round(duration_ms, 2),
            success=success,
            error_message=error_msg,
            params_json=params_json,
            response_size=len(str(result)) if result is not None else 0,
            server_name=server_name,
        )
        try:
            storage.log_call(event)
        except Exception:
            pass  # never let logging break the tool


async def _execute_and_log(
    func: Callable,
    args: tuple,
    kwargs: dict,
    storage: Storage,
    server_name: str,
    log_params: bool,
    *,
    is_async: bool = False,
) -> Any:
    """Execute an async function and log the result."""
    start = time.perf_counter()
    error_msg = None
    success = True
    result = None

    try:
        result = await func(*args, **kwargs)
        return result
    except Exception as e:
        success = False
        error_msg = f"{type(e).__name__}: {e}"
        raise
    finally:
        duration_ms = (time.perf_counter() - start) * 1000
        params_json = None
        if log_params and kwargs:
            try:
                params_json = json.dumps(kwargs, default=str)
            except (TypeError, ValueError):
                params_json = None

        event = ToolCallEvent(
            tool_name=func.__name__,
            timestamp=ToolCallEvent.now_iso(),
            duration_ms=round(duration_ms, 2),
            success=success,
            error_message=error_msg,
            params_json=params_json,
            response_size=len(str(result)) if result is not None else 0,
            server_name=server_name,
        )
        try:
            storage.log_call(event)
        except Exception:
            pass  # never let logging break the tool


def _patch_existing_tools(
    server: FastMCP,
    storage: Storage,
    server_name: str,
    log_params: bool,
) -> None:
    """Wrap tools that were registered before observe() was called."""
    # Access FastMCP's internal tool manager
    if not hasattr(server, "_tool_manager"):
        return

    manager = server._tool_manager
    if not hasattr(manager, "_tools"):
        return

    for name, tool in manager._tools.items():
        if hasattr(tool, "fn") and not getattr(tool.fn, "_mcp_observed", False):
            original_fn = tool.fn
            wrapped = _wrap_function(
                original_fn,
                storage=storage,
                server_name=server_name,
                log_params=log_params,
            )
            wrapped._mcp_observed = True  # type: ignore[attr-defined]
            tool.fn = wrapped
