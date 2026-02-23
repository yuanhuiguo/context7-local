# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [0.1.0] - 2026-02-23

### Added

- MCP server with `stdio` transport via FastMCP (`server.py`)
- `resolve-library-id` tool — searches GitHub repositories by name, returns top 5 matches with library IDs, descriptions, star counts, and languages
- `query-docs` tool — fetches README + `/docs` Markdown files from GitHub, caches locally, chunks by heading, and ranks by TF-IDF relevance
- Async GitHub REST API client (`github_client.py`) with optional `GITHUB_TOKEN` for higher rate limits
- File-based documentation cache (`cache.py`) with configurable TTL (default 7 days) at `~/.cache/context7-local/`
- Markdown chunker (`chunker.py`) — splits on H1/H2 headings, preserves fenced code blocks, hard-truncates at 2000 chars
- CLI entry point: `uv run context7-local` or `python -m context7_local`
- Cline MCP configuration example in README
- 22 unit tests covering all modules (cache, chunker, github_client, tools)

### Changed

- `github_client.py` — shared httpx client factory (`_make_client`) replaces per-request client creation
- `github_client.py` — automatic retry with exponential backoff (3 attempts, 1→2→4s) for transient network errors
- `github_client.py` — timeout configurable via `GITHUB_TIMEOUT` env var (default 30s)
- `github_client.py` — `_walk_tree` receives `client` parameter to reuse connection during recursive directory traversal
- `tools.py` — both tools now catch `httpx.HTTPError` and return user-friendly error messages instead of crashing the MCP server
