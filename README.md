# mcp-observe

Drop-in observability for MCP servers. Track tool calls, latency, errors, and usage with one line of code.

## Install

```bash
pip install mcp-observe
```

## Quick Start

```python
from mcp_observe import ObserveMCP

# Replace FastMCP with ObserveMCP — that's it
mcp = ObserveMCP("my-server")

@mcp.tool()
def my_tool(param: str) -> str:
    """My tool description."""
    return f"result for {param}"

mcp.run(transport="stdio")
```

Every tool call is now automatically tracked — tool name, duration, success/failure, response size.

## Dashboard

```bash
pip install mcp-observe[dashboard]
mcp-observe
```

Opens a web dashboard at `http://localhost:8020` showing:
- Total calls, error rate, avg latency
- Calls per hour chart
- Per-tool breakdown (call count, p50/p95 latency, error rate)
- Recent call log

## Alternative: Wrap an existing server

```python
from mcp.server.fastmcp import FastMCP
from mcp_observe import observe

mcp = FastMCP("my-server")

@mcp.tool()
def my_tool(param: str) -> str:
    return f"result for {param}"

observe(mcp)  # instruments all registered tools
mcp.run(transport="stdio")
```

## Options

```python
mcp = ObserveMCP(
    "my-server",
    db_path="/path/to/custom.db",  # default: ~/.mcp-observe/observe.db
    log_params=True,               # log input parameters (default: False)
)
```

## License

MIT
