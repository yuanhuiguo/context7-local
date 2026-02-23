---
description: QA standards for context7-local
---

# Testing Standards

## Framework

- **pytest** + **pytest-asyncio** for all async tests

## Test Structure

```
tests/
├── test_chunker.py        # Unit: Markdown chunking logic
├── test_cache.py           # Unit: Cache read/write/TTL
├── test_github_client.py   # Unit: GitHub API (mocked with httpx MockTransport)
├── test_tools.py           # Unit: Tool logic
└── test_integration.py     # Integration: MCP client ↔ server roundtrip
```

## Rules

- GitHub API calls MUST be mocked in unit tests (use `httpx.MockTransport`)
- Integration tests may hit real GitHub API (marked with `@pytest.mark.integration`)
- All async functions tested with `@pytest.mark.asyncio`
- Run command: `uv run pytest` (unit) / `uv run pytest -m integration` (integration)
