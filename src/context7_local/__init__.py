"""context7-local: Local MCP server for Context7-compatible documentation tools."""

from context7_local.server import mcp


def main() -> None:
    """CLI entry point — starts the MCP server over stdio."""
    mcp.run(transport="stdio")
