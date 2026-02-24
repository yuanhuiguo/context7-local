"""Embedding engine — wraps FastEmbed with lazy singleton initialization.

FastEmbed uses ONNX Runtime under the hood (CPU-only, no GPU required).
The model is downloaded once to ~/.cache/fastembed/ on first use.

Default model: BAAI/bge-small-en-v1.5
  - Dimension: 384
  - Size: ~130 MB (ONNX quantized)
  - License: MIT
"""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from fastembed import TextEmbedding

log = logging.getLogger("context7-local")

_DEFAULT_MODEL = "BAAI/bge-small-en-v1.5"

# Module-level singleton — initialized on first call to embed()
_model: TextEmbedding | None = None


def _get_model() -> TextEmbedding:
    """Lazy-initialize the embedding model (downloads on first use)."""
    global _model  # noqa: PLW0603
    if _model is None:
        from fastembed import TextEmbedding

        model_name = os.environ.get("EMBED_MODEL", _DEFAULT_MODEL)
        log.info("Loading embedding model: %s", model_name)
        _model = TextEmbedding(model_name=model_name)
        log.info("Embedding model ready.")
    return _model


def embed_texts(texts: list[str]) -> np.ndarray:
    """Return a (N, D) float32 matrix of L2-normalised embeddings.

    Args:
        texts: List of strings to embed. Empty strings are replaced with
               a single space to avoid tokenizer errors.

    Returns:
        numpy array of shape (len(texts), embedding_dim), dtype=float32,
        where each row is an L2-normalised unit vector.
    """
    if not texts:
        return np.empty((0, 384), dtype=np.float32)

    safe_texts = [t if t.strip() else " " for t in texts]
    model = _get_model()
    # fastembed.embed() returns a generator of np.ndarray
    vecs: np.ndarray = np.array(list(model.embed(safe_texts)), dtype=np.float32)

    # L2-normalise so cosine similarity == dot product
    norms = np.linalg.norm(vecs, axis=1, keepdims=True)
    norms = np.where(norms == 0, 1.0, norms)  # avoid div-by-zero
    return (vecs / norms).astype(np.float32)


def embed_query(query: str) -> np.ndarray:
    """Return a (D,) unit vector for a single query string."""
    return embed_texts([query])[0]
