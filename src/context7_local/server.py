"""MCP Server definition — registers all tools via FastMCP."""

from mcp.server.fastmcp import FastMCP

mcp = FastMCP(
    name="context7-local",
    instructions=(
        "Local Context7 MCP server. Provides resolve-library-id and query-docs tools "
        "that fetch open-source library documentation from GitHub and cache locally."
    ),
)

# Import tools module so @mcp.tool() decorators execute at import time.
import context7_local.tools as _tools  # noqa: F401, E402
