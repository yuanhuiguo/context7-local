---
description: Locks the tech stack for context7-local MCP server project
---

# Tech Stack

## Runtime

- **Language**: Python 3.12+
- **MCP SDK**: `mcp` >=1.2.0,<2 (FastMCP decorator API)
- **HTTP Client**: `httpx` >=0.27.0,<1 (async)
- **Transport**: stdio (Cline standard)

## Dev Dependencies

- **Test**: pytest + pytest-asyncio
- **Lint**: ruff (format + check)
- **Build**: uv (package manager + runner)

## Constraints

- **NO frontend** — pure CLI/MCP server
- **NO database** — file-based cache only (`~/.cache/context7-local/`)
- **NO additional runtime deps** without human approval
- **Python stdlib preferred** for text processing (TF-IDF, chunking)
