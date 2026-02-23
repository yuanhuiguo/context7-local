---
description: Run ruff format + check with auto-fix, with backpressure guard
---

# WORKFLOW: /lint-fix

## Steps

1. Count changed files:

```bash
uv run ruff check --diff src/ tests/ | grep "^---" | wc -l
```

1. **BACKPRESSURE GUARD**: If >20 files affected, HALT and ask human to scope.

// turbo
3. Auto-format:

```bash
uv run ruff format src/ tests/
```

// turbo
4. Auto-fix lint:

```bash
uv run ruff check --fix src/ tests/
```

1. Report remaining unfixable issues:

```bash
uv run ruff check src/ tests/
```

1. If zero issues: `[STATUS: LINT_CLEAN]`. Otherwise present remaining issues to human.
