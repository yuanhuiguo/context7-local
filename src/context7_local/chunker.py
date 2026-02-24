"""Markdown document chunker — splits by headings while preserving code blocks."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import numpy as np

_MAX_CHUNK_CHARS = 2000


@dataclass(frozen=True, slots=True)
class Chunk:
    """A section of a Markdown document."""

    title: str
    content: str
    source: str  # file path or identifier
    embedding: np.ndarray | None = field(default=None, compare=False, hash=False)


def chunk_markdown(text: str, source: str = "") -> list[Chunk]:
    """Split a Markdown document into heading-delimited chunks.

    Rules:
      - Split on ``#`` and ``##`` headings.
      - Never split inside fenced code blocks (``` ... ```).
      - Chunks exceeding *_MAX_CHUNK_CHARS* are hard-truncated.
    """
    lines = text.splitlines(keepends=True)
    chunks: list[Chunk] = []
    current_title = source or "(untitled)"
    current_lines: list[str] = []
    in_code_block = False

    for line in lines:
        stripped = line.strip()

        # Track fenced code blocks
        if stripped.startswith("```"):
            in_code_block = not in_code_block

        # Detect heading boundaries (only outside code blocks)
        if (
            not in_code_block
            and stripped.startswith("#")
            and (stripped.startswith("# ") or stripped.startswith("## "))
        ):
            # Flush previous chunk
            if current_lines:
                chunks.append(_make_chunk(current_title, current_lines, source))
            current_title = stripped.lstrip("#").strip()
            current_lines = []
        else:
            current_lines.append(line)

    # Flush trailing chunk
    if current_lines:
        chunks.append(_make_chunk(current_title, current_lines, source))

    return chunks


def _make_chunk(title: str, lines: list[str], source: str) -> Chunk:
    content = "".join(lines).strip()
    if len(content) > _MAX_CHUNK_CHARS:
        content = content[:_MAX_CHUNK_CHARS] + "\n…(truncated)"
    return Chunk(title=title, content=content, source=source)
