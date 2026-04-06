"""Tests for mcp-observe core functionality."""

import json
import tempfile
from pathlib import Path

from mcp_observe import ObserveMCP, Storage, ToolCallEvent


def test_storage_roundtrip():
    """Events can be stored and retrieved."""
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "test.db"
        storage = Storage(db_path)

        event = ToolCallEvent(
            tool_name="get_stock_quote",
            timestamp=ToolCallEvent.now_iso(),
            duration_ms=142.5,
            success=True,
            params_json=json.dumps({"ticker": "AAPL"}),
            response_size=256,
            server_name="fintools",
        )
        storage.log_call(event)

        calls = storage.get_recent_calls(limit=10)
        assert len(calls) == 1
        assert calls[0].tool_name == "get_stock_quote"
        assert calls[0].success is True
        assert calls[0].duration_ms == 142.5
        assert calls[0].server_name == "fintools"


def test_storage_stats():
    """Tool stats are computed correctly."""
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "test.db"
        storage = Storage(db_path)

        for i in range(5):
            storage.log_call(
                ToolCallEvent(
                    tool_name="get_quote",
                    timestamp=ToolCallEvent.now_iso(),
                    duration_ms=100.0 + i * 10,
                    success=True,
                    server_name="test",
                )
            )
        storage.log_call(
            ToolCallEvent(
                tool_name="get_quote",
                timestamp=ToolCallEvent.now_iso(),
                duration_ms=500.0,
                success=False,
                error_message="ValueError: bad ticker",
                server_name="test",
            )
        )

        stats = storage.get_tool_stats("test")
        assert len(stats) == 1
        s = stats[0]
        assert s.tool_name == "get_quote"
        assert s.total_calls == 6
        assert s.success_count == 5
        assert s.error_count == 1
        assert s.error_rate > 0


def test_storage_server_summary():
    """Server summary aggregates correctly."""
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "test.db"
        storage = Storage(db_path)

        for tool in ["tool_a", "tool_b"]:
            for _ in range(3):
                storage.log_call(
                    ToolCallEvent(
                        tool_name=tool,
                        timestamp=ToolCallEvent.now_iso(),
                        duration_ms=50.0,
                        success=True,
                        server_name="myserver",
                    )
                )

        summary = storage.get_server_summary("myserver")
        assert summary.server_name == "myserver"
        assert summary.total_calls == 6
        assert len(summary.tools) == 2


def test_observe_mcp_wraps_tools():
    """ObserveMCP instruments tool functions."""
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "test.db"
        mcp = ObserveMCP("test-server", db_path=db_path)

        @mcp.tool()
        def add(a: int, b: int) -> str:
            """Add two numbers."""
            return json.dumps({"result": a + b})

        # Call the tool directly (simulating what FastMCP does internally)
        # The wrapper should have logged it
        result = add(2, 3)
        assert json.loads(result)["result"] == 5

        storage = Storage(db_path)
        calls = storage.get_recent_calls()
        assert len(calls) == 1
        assert calls[0].tool_name == "add"
        assert calls[0].success is True


def test_observe_mcp_logs_errors():
    """ObserveMCP captures errors without swallowing them."""
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "test.db"
        mcp = ObserveMCP("test-server", db_path=db_path)

        @mcp.tool()
        def bad_tool() -> str:
            """A tool that fails."""
            raise ValueError("something broke")

        try:
            bad_tool()
        except ValueError:
            pass

        storage = Storage(db_path)
        calls = storage.get_recent_calls()
        assert len(calls) == 1
        assert calls[0].success is False
        assert "ValueError" in calls[0].error_message


def test_multiple_servers():
    """Events from different servers are tracked separately."""
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "test.db"
        storage = Storage(db_path)

        for server in ["server-a", "server-b"]:
            storage.log_call(
                ToolCallEvent(
                    tool_name="ping",
                    timestamp=ToolCallEvent.now_iso(),
                    duration_ms=10.0,
                    success=True,
                    server_name=server,
                )
            )

        servers = storage.get_servers()
        assert set(servers) == {"server-a", "server-b"}

        stats_a = storage.get_tool_stats("server-a")
        assert len(stats_a) == 1
        assert stats_a[0].total_calls == 1
