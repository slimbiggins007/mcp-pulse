"""CLI entry point: `mcp-pulse` or `python -m mcp_pulse`."""

from __future__ import annotations

import argparse
import sys


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="mcp-pulse",
        description="Observability dashboard for MCP servers",
    )
    parser.add_argument(
        "--port", type=int, default=8020, help="Dashboard port (default: 8020)"
    )
    parser.add_argument(
        "--host", type=str, default="127.0.0.1", help="Dashboard host (default: 127.0.0.1)"
    )
    parser.add_argument(
        "--db",
        type=str,
        default=None,
        help="Path to SQLite database (default: ~/.mcp-pulse/observe.db)",
    )
    args = parser.parse_args()

    try:
        import uvicorn
    except ImportError:
        print("Dashboard requires extra dependencies:")
        print("  pip install mcp-pulse[dashboard]")
        sys.exit(1)

    from mcp_pulse.dashboard import create_app

    app = create_app(db_path=args.db)
    print(f"mcp-pulse dashboard: http://{args.host}:{args.port}")
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
