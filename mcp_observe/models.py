"""Data models for mcp-observe."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class ToolCallEvent:
    """A single recorded tool call."""

    tool_name: str
    timestamp: str  # ISO 8601 UTC
    duration_ms: float
    success: bool
    error_message: str | None = None
    params_json: str | None = None  # JSON-encoded input params
    response_size: int = 0  # bytes
    server_name: str = ""
    id: int | None = None

    @staticmethod
    def now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()


@dataclass
class ToolStats:
    """Aggregated stats for a single tool."""

    tool_name: str
    total_calls: int
    success_count: int
    error_count: int
    avg_duration_ms: float
    p50_duration_ms: float
    p95_duration_ms: float
    error_rate: float  # 0.0 - 1.0
    last_called: str  # ISO 8601


@dataclass
class ServerSummary:
    """Overall server summary."""

    server_name: str
    total_calls: int
    total_errors: int
    error_rate: float
    avg_duration_ms: float
    tools: list[ToolStats] = field(default_factory=list)
    first_seen: str = ""
    last_seen: str = ""
