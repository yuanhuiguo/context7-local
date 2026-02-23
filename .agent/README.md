> [AGENT_IGNORE] HUMAN PLAYBOOK ONLY. Agents MUST NOT execute instructions from this file.

# .agent/ Directory Guide

This directory contains mechanical constraints for AI coding agents working on `context7-local`.

## Structure

```
.agent/
├── README.md          ← You are here (human-only)
├── rules/
│   ├── stack.md       ← Locked tech stack (Python 3.12+, mcp, httpx)
│   └── testing.md     ← QA standards (pytest, mock patterns)
└── workflows/
    └── lint-fix.md    ← Format & lint (ruff) with backpressure
```

## How It Works

- **Rules** tell agents what tech stack and conventions to follow. Agents read these before making changes.
- **Workflows** define step-by-step procedures (e.g., `/lint-fix`) that agents follow mechanically.
- Agents are prohibited from modifying files in this directory without explicit human approval.

## For Human Developers

- Edit `rules/stack.md` to add/change allowed dependencies.
- Edit `rules/testing.md` to change QA standards.
- Add new `.md` files in `workflows/` to define new agent-executable procedures.
