# context7-local

A locally running MCP server providing **Context7-compatible** `resolve-library-id` and `query-docs` tools. Fetches open-source library documentation from GitHub **and official documentation websites**, caches it locally, and serves it to LLM clients (like Cline) over stdio.

## Quick Start

```bash
# Install
uv sync

# Run (stdio mode — used by Cline/MCP clients)
uv run context7-local
```

> [!TIP]
> **Windows Users**: See the [Windows Deployment Guide](docs/deploy_windows.md) for platform-specific setup instructions.

## Cline Configuration

Add to your `cline_mcp_settings.json`:

```json
{
  "mcpServers": {
    "context7-local": {
      "command": "uv",
      "args": ["--directory", "/path/to/context7-local", "run", "context7-local"],
      "disabled": false
    }
  }
}
```

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `GITHUB_TOKEN` | _(none)_ | Optional GitHub PAT for higher rate limits (60/h → 5000/h) |
| `GITHUB_TIMEOUT` | `30` | HTTP request timeout in seconds |
| `CACHE_DIR` | `~/.cache/context7-local/` | Documentation cache directory |
| `CACHE_TTL_HOURS` | `168` (7 days) | Cache expiry in hours |
| `EMBED_MODEL` | `BAAI/bge-small-en-v1.5` | FastEmbed ONNX model used for semantic search |

## Tools

### `resolve-library-id`

Search GitHub for a library by name. Returns top 5 matches with library IDs, descriptions, star counts, and languages.

### `query-docs`

Fetch and search documentation for a library. Uses a 3-stage pipeline:

1. **README** — fetches the repository README
2. **`/docs` directory** — walks the docs tree for Markdown files
3. **Official website** — scrapes the library's documentation site (e.g. `fastapi.tiangolo.com`)

All content is cached locally, split into chunks by heading, and ranked by **Semantic Vector Search** (using `FastEmbed` + Numpy cosine similarity) for high-relevance retrieval.

## Development

```bash
# Run tests
uv run pytest  # 47 tests

# Format & lint
uv run ruff format .
uv run ruff check . --fix
```
