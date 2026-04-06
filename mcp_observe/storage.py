"""SQLite storage for tool call events."""

from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path

from mcp_observe.models import ToolCallEvent, ToolStats, ServerSummary

DEFAULT_DB_PATH = Path.home() / ".mcp-observe" / "observe.db"


class Storage:
    """Thread-safe SQLite storage for tool call events."""

    def __init__(self, db_path: str | Path | None = None) -> None:
        self.db_path = Path(db_path) if db_path else DEFAULT_DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._local = threading.local()
        self._init_db()

    @property
    def _conn(self) -> sqlite3.Connection:
        if not hasattr(self._local, "conn"):
            self._local.conn = sqlite3.connect(
                str(self.db_path), check_same_thread=False
            )
            self._local.conn.row_factory = sqlite3.Row
        return self._local.conn

    def _init_db(self) -> None:
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS tool_calls (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tool_name TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                duration_ms REAL NOT NULL,
                success INTEGER NOT NULL,
                error_message TEXT,
                params_json TEXT,
                response_size INTEGER DEFAULT 0,
                server_name TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_tool_calls_tool
                ON tool_calls(tool_name);
            CREATE INDEX IF NOT EXISTS idx_tool_calls_ts
                ON tool_calls(timestamp);
            CREATE INDEX IF NOT EXISTS idx_tool_calls_server
                ON tool_calls(server_name);
            """
        )
        self._conn.commit()

    def log_call(self, event: ToolCallEvent) -> None:
        self._conn.execute(
            """
            INSERT INTO tool_calls
                (tool_name, timestamp, duration_ms, success,
                 error_message, params_json, response_size, server_name)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event.tool_name,
                event.timestamp,
                event.duration_ms,
                1 if event.success else 0,
                event.error_message,
                event.params_json,
                event.response_size,
                event.server_name,
            ),
        )
        self._conn.commit()

    def get_recent_calls(
        self, limit: int = 50, server_name: str | None = None
    ) -> list[ToolCallEvent]:
        query = "SELECT * FROM tool_calls"
        params: list = []
        if server_name:
            query += " WHERE server_name = ?"
            params.append(server_name)
        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)

        rows = self._conn.execute(query, params).fetchall()
        return [
            ToolCallEvent(
                id=r["id"],
                tool_name=r["tool_name"],
                timestamp=r["timestamp"],
                duration_ms=r["duration_ms"],
                success=bool(r["success"]),
                error_message=r["error_message"],
                params_json=r["params_json"],
                response_size=r["response_size"],
                server_name=r["server_name"],
            )
            for r in rows
        ]

    def get_tool_stats(self, server_name: str | None = None) -> list[ToolStats]:
        where = "WHERE server_name = ?" if server_name else ""
        params = [server_name] if server_name else []

        rows = self._conn.execute(
            f"""
            SELECT
                tool_name,
                COUNT(*) as total_calls,
                SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END) as success_count,
                SUM(CASE WHEN success = 0 THEN 1 ELSE 0 END) as error_count,
                AVG(duration_ms) as avg_duration_ms,
                MAX(timestamp) as last_called
            FROM tool_calls
            {where}
            GROUP BY tool_name
            ORDER BY total_calls DESC
            """,
            params,
        ).fetchall()

        stats = []
        for r in rows:
            # Get percentiles with a sub-query
            durations = self._conn.execute(
                f"""
                SELECT duration_ms FROM tool_calls
                WHERE tool_name = ? {"AND server_name = ?" if server_name else ""}
                ORDER BY duration_ms
                """,
                [r["tool_name"]] + params,
            ).fetchall()

            ds = [d["duration_ms"] for d in durations]
            p50 = ds[len(ds) // 2] if ds else 0
            p95 = ds[int(len(ds) * 0.95)] if ds else 0

            total = r["total_calls"]
            errors = r["error_count"]

            stats.append(
                ToolStats(
                    tool_name=r["tool_name"],
                    total_calls=total,
                    success_count=r["success_count"],
                    error_count=errors,
                    avg_duration_ms=round(r["avg_duration_ms"], 2),
                    p50_duration_ms=round(p50, 2),
                    p95_duration_ms=round(p95, 2),
                    error_rate=round(errors / total, 4) if total > 0 else 0,
                    last_called=r["last_called"],
                )
            )
        return stats

    def get_server_summary(self, server_name: str) -> ServerSummary:
        row = self._conn.execute(
            """
            SELECT
                COUNT(*) as total_calls,
                SUM(CASE WHEN success = 0 THEN 1 ELSE 0 END) as total_errors,
                AVG(duration_ms) as avg_duration_ms,
                MIN(timestamp) as first_seen,
                MAX(timestamp) as last_seen
            FROM tool_calls
            WHERE server_name = ?
            """,
            (server_name,),
        ).fetchone()

        total = row["total_calls"] or 0
        errors = row["total_errors"] or 0
        tools = self.get_tool_stats(server_name)

        return ServerSummary(
            server_name=server_name,
            total_calls=total,
            total_errors=errors,
            error_rate=round(errors / total, 4) if total > 0 else 0,
            avg_duration_ms=round(row["avg_duration_ms"] or 0, 2),
            tools=tools,
            first_seen=row["first_seen"] or "",
            last_seen=row["last_seen"] or "",
        )

    def get_calls_per_hour(
        self, server_name: str | None = None, hours: int = 24
    ) -> list[dict]:
        where = "WHERE server_name = ? AND" if server_name else "WHERE"
        params: list = []
        if server_name:
            params.append(server_name)

        rows = self._conn.execute(
            f"""
            SELECT
                strftime('%Y-%m-%dT%H:00:00', timestamp) as hour,
                COUNT(*) as calls,
                SUM(CASE WHEN success = 0 THEN 1 ELSE 0 END) as errors,
                AVG(duration_ms) as avg_ms
            FROM tool_calls
            {where} timestamp >= datetime('now', '-{hours} hours')
            GROUP BY hour
            ORDER BY hour
            """,
            params,
        ).fetchall()

        return [
            {
                "hour": r["hour"],
                "calls": r["calls"],
                "errors": r["errors"],
                "avg_ms": round(r["avg_ms"], 2),
            }
            for r in rows
        ]

    def get_servers(self) -> list[str]:
        rows = self._conn.execute(
            "SELECT DISTINCT server_name FROM tool_calls ORDER BY server_name"
        ).fetchall()
        return [r["server_name"] for r in rows]
