"""Shared pytest fixtures for context7-local test suite."""

from __future__ import annotations

import numpy as np
import pytest

from context7_local import embedder


@pytest.fixture(autouse=True)
def mock_embedder(monkeypatch):
    """Patch embedder functions so tests never download a real model.

    embed_texts returns a (N, 4) float32 matrix of random unit vectors.
    embed_query returns a (4,) unit vector [1, 0, 0, 0].
    """

    def fake_embed_texts(texts: list[str]) -> np.ndarray:
        rng = np.random.default_rng(seed=42)
        n = len(texts)
        if n == 0:
            return np.empty((0, 4), dtype=np.float32)
        mat = rng.random((n, 4)).astype(np.float32)
        norms = np.linalg.norm(mat, axis=1, keepdims=True)
        return mat / norms

    def fake_embed_query(query: str) -> np.ndarray:
        return np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float32)

    monkeypatch.setattr(embedder, "embed_texts", fake_embed_texts)
    monkeypatch.setattr(embedder, "embed_query", fake_embed_query)
