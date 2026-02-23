"""Unit tests for the file-based cache."""

import json
import time

from context7_local import cache


class TestCache:
    def test_save_and_load(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setenv("CACHE_DIR", str(tmp_path))
        cache.save_doc("owner", "repo", "readme.md", "# Hello")
        cache.mark_fetched("owner", "repo")

        docs = cache.load_all_docs("owner", "repo")
        assert "readme.md" in docs
        assert docs["readme.md"] == "# Hello"

    def test_is_cached_returns_true_when_fresh(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setenv("CACHE_DIR", str(tmp_path))
        cache.save_doc("o", "r", "file.md", "content")
        cache.mark_fetched("o", "r")

        assert cache.is_cached("o", "r") is True

    def test_is_cached_returns_false_when_missing(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setenv("CACHE_DIR", str(tmp_path))
        assert cache.is_cached("no", "repo") is False

    def test_is_cached_returns_false_when_expired(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setenv("CACHE_DIR", str(tmp_path))
        monkeypatch.setenv("CACHE_TTL_HOURS", "0.0001")  # ~0.36 seconds

        cache.save_doc("o", "r", "file.md", "content")
        # Write metadata with timestamp in the past
        meta_path = tmp_path / "o" / "r" / "_meta.json"
        meta_path.write_text(json.dumps({"fetched_at": time.time() - 3600}))

        assert cache.is_cached("o", "r") is False

    def test_load_skips_meta_files(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setenv("CACHE_DIR", str(tmp_path))
        cache.save_doc("o", "r", "readme.md", "content")
        cache.mark_fetched("o", "r")

        docs = cache.load_all_docs("o", "r")
        assert "_meta.json" not in docs
        assert "readme.md" in docs

    def test_nested_doc_path(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setenv("CACHE_DIR", str(tmp_path))
        cache.save_doc("o", "r", "docs/guide/intro.md", "# Intro")

        docs = cache.load_all_docs("o", "r")
        assert "docs/guide/intro.md" in docs
