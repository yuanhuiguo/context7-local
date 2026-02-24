"""File-based documentation cache with TTL expiry.

Cache layout:
    ~/.cache/context7-local/{owner}/{repo}/
        _meta.json          ← { "fetched_at": <epoch> }
        _embeddings.npy     ← float32 matrix (N, D) of chunk embeddings
        _chunk_ids.json     ← list of chunk source+title identifiers
        readme.md
        docs/path/to/file.md
"""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path

import numpy as np

log = logging.getLogger("context7-local")

_DEFAULT_CACHE_DIR = Path.home() / ".cache" / "context7-local"
_DEFAULT_TTL_HOURS = 7 * 24  # 7 days


def _cache_dir() -> Path:
    return Path(os.environ.get("CACHE_DIR", str(_DEFAULT_CACHE_DIR)))


def _ttl_seconds() -> float:
    hours = float(os.environ.get("CACHE_TTL_HOURS", str(_DEFAULT_TTL_HOURS)))
    return hours * 3600


def _meta_path(owner: str, repo: str) -> Path:
    return _cache_dir() / owner / repo / "_meta.json"


def is_cached(owner: str, repo: str) -> bool:
    """Return True if docs for this repo are cached and not expired."""
    meta = _meta_path(owner, repo)
    if not meta.exists():
        return False
    try:
        data = json.loads(meta.read_text())
        fetched_at = data.get("fetched_at", 0)
        return (time.time() - fetched_at) < _ttl_seconds()
    except (json.JSONDecodeError, OSError):
        return False


def save_doc(owner: str, repo: str, relative_path: str, content: str) -> None:
    """Save a single document to the cache."""
    dest = _cache_dir() / owner / repo / relative_path
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(content, encoding="utf-8")


def mark_fetched(owner: str, repo: str) -> None:
    """Write or update the metadata timestamp for a cached repo."""
    meta = _meta_path(owner, repo)
    meta.parent.mkdir(parents=True, exist_ok=True)
    meta.write_text(json.dumps({"fetched_at": time.time()}))


def load_all_docs(owner: str, repo: str) -> dict[str, str]:
    """Load all cached Markdown files for a repo.

    Returns a dict mapping relative paths to their text content.
    """
    base = _cache_dir() / owner / repo
    if not base.exists():
        return {}
    result: dict[str, str] = {}
    for md_file in base.rglob("*.md"):
        rel = str(md_file.relative_to(base))
        if rel.startswith("_"):
            continue  # skip metadata
        result[rel] = md_file.read_text(encoding="utf-8", errors="replace")
    return result


# ---------------------------------------------------------------------------
# Vector embedding cache
# ---------------------------------------------------------------------------

_EMBED_MATRIX_FILE = "_embeddings.npy"
_EMBED_IDS_FILE = "_chunk_ids.json"


def save_embeddings(
    owner: str,
    repo: str,
    chunk_ids: list[str],
    matrix: np.ndarray,
) -> None:
    """Persist chunk embeddings alongside markdown files.

    Args:
        owner: GitHub owner/organisation.
        repo: GitHub repository name.
        chunk_ids: List of stable identifiers for each chunk row (source + title).
        matrix: float32 numpy array of shape (len(chunk_ids), embedding_dim).
    """
    base = _cache_dir() / owner / repo
    base.mkdir(parents=True, exist_ok=True)
    np.save(str(base / _EMBED_MATRIX_FILE), matrix)
    (base / _EMBED_IDS_FILE).write_text(
        json.dumps(chunk_ids, ensure_ascii=False), encoding="utf-8"
    )


def load_embeddings(
    owner: str,
    repo: str,
) -> tuple[list[str], np.ndarray] | None:
    """Load persisted chunk embeddings.

    Returns:
        (chunk_ids, matrix) if cache files exist, otherwise None.
    """
    base = _cache_dir() / owner / repo
    matrix_path = base / _EMBED_MATRIX_FILE
    ids_path = base / _EMBED_IDS_FILE
    if not matrix_path.exists() or not ids_path.exists():
        return None
    try:
        matrix: np.ndarray = np.load(str(matrix_path))
        chunk_ids: list[str] = json.loads(ids_path.read_text(encoding="utf-8"))
        return chunk_ids, matrix
    except (OSError, ValueError):
        log.warning("Failed to load embedding cache for %s/%s", owner, repo, exc_info=True)
        return None
