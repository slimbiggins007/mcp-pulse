"""CLI entry point: `mcp-observe` or `python -m mcp_observe`."""

from __future__ import annotations

import argparse
import sys


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="mcp-observe",
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
        help="Path to SQLite database (default: ~/.mcp-observe/observe.db)",
    )
    args = parser.parse_args()

    try:
        import uvicorn
    except ImportError:
        print("Dashboard requires extra dependencies:")
        print("  pip install mcp-observe[dashboard]")
        sys.exit(1)

    from mcp_observe.dashboard import create_app

    app = create_app(db_path=args.db)
    print(f"mcp-observe dashboard: http://{args.host}:{args.port}")
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
