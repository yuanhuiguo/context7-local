"""Unit tests for MCP tools (resolve-library-id, query-docs)."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from context7_local import cache, chunker, embedder, github_client
from context7_local.tools import _chunk_id, _rank_chunks_semantic, query_docs, resolve_library_id


class TestResolveLibraryId:
    @pytest.mark.asyncio
    async def test_formats_results(self) -> None:
        mock_repos = [
            github_client.RepoInfo(
                owner="facebook",
                repo="react",
                description="A JS library",
                stars=200000,
                language="JavaScript",
            ),
        ]
        with patch.object(
            github_client, "search_repositories", new_callable=AsyncMock, return_value=mock_repos
        ):
            result = await resolve_library_id("react")
            assert "/facebook/react" in result
            assert "200,000" in result

    @pytest.mark.asyncio
    async def test_no_results(self) -> None:
        with patch.object(
            github_client, "search_repositories", new_callable=AsyncMock, return_value=[]
        ):
            result = await resolve_library_id("nonexistent_xyz_lib")
            assert "No repositories found" in result


class TestQueryDocs:
    @pytest.mark.asyncio
    async def test_invalid_library_id(self) -> None:
        result = await query_docs("invalid-format", "anything")
        assert "Invalid library_id" in result

    @pytest.mark.asyncio
    async def test_returns_ranked_chunks(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setenv("CACHE_DIR", str(tmp_path))

        # Pre-populate cache
        doc = "# Setup\nHow to install\n## Usage\nHow to use the API"
        cache.save_doc("owner", "repo", "readme.md", doc)
        cache.mark_fetched("owner", "repo")

        result = await query_docs("/owner/repo", "install setup")
        assert "Setup" in result or "install" in result.lower()

    @pytest.mark.asyncio
    async def test_fetches_when_not_cached(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setenv("CACHE_DIR", str(tmp_path))

        with (
            patch.object(
                github_client,
                "fetch_readme",
                new_callable=AsyncMock,
                return_value="# README\nHello",
            ),
            patch.object(
                github_client, "list_docs_directory", new_callable=AsyncMock, return_value=[]
            ),
        ):
            result = await query_docs("/owner/repo", "hello")
            assert "Hello" in result


class TestRankChunksSemantic:
    """Tests for the numpy-based semantic ranking function."""

    def test_returns_top_k_chunks(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setenv("CACHE_DIR", str(tmp_path))
        chunks = [
            chunker.Chunk(title="Install", content="pip install foo bar", source="a.md"),
            chunker.Chunk(title="Unrelated", content="nothing relevant here", source="b.md"),
            chunker.Chunk(title="Setup", content="install setup guide step", source="c.md"),
        ]
        ranked = _rank_chunks_semantic("install setup", "owner", "repo", chunks, top_k=2)
        # Should return exactly top_k results (or fewer if chunks < top_k)
        assert len(ranked) == 2
        # All returned chunks must be valid Chunk objects from the original list
        for chunk in ranked:
            assert chunk in chunks

    def test_top_k_exceeds_chunks(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setenv("CACHE_DIR", str(tmp_path))
        chunks = [chunker.Chunk(title="A", content="content", source="a.md")]
        ranked = _rank_chunks_semantic("query", "owner", "repo", chunks, top_k=10)
        assert len(ranked) == 1

    def test_embedding_cache_hit(self, tmp_path, monkeypatch) -> None:
        """Second call with same chunks uses persisted .npy without re-embedding."""
        import numpy as np

        monkeypatch.setenv("CACHE_DIR", str(tmp_path))
        chunks = [chunker.Chunk(title="A", content="content", source="a.md")]

        # First call — populates cache
        _rank_chunks_semantic("q1", "owner", "repo", chunks, top_k=1)

        # Replace embed_texts with a sentinel that should NOT be called on cache hit
        call_count = {"n": 0}

        def counting_embed(texts):
            call_count["n"] += 1
            return np.zeros((len(texts), 4), dtype=np.float32)

        monkeypatch.setattr(embedder, "embed_texts", counting_embed)

        _rank_chunks_semantic("q2", "owner", "repo", chunks, top_k=1)
        assert call_count["n"] == 0, "embed_texts should not be called on cache hit"

    def test_empty_chunks_returns_empty(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setenv("CACHE_DIR", str(tmp_path))
        result = _rank_chunks_semantic("anything", "owner", "repo", [], top_k=5)
        assert result == []

    def test_chunk_id_format(self) -> None:
        chunk = chunker.Chunk(title="My Title", content="content", source="readme.md")
        assert _chunk_id(chunk) == "readme.md::My Title"


class TestFetchAndCacheWithScraper:
    """Test the website-augmented fetch pipeline."""

    @pytest.mark.asyncio
    async def test_scrapes_homepage_when_available(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setenv("CACHE_DIR", str(tmp_path))

        with (
            patch.object(
                github_client,
                "fetch_readme",
                new_callable=AsyncMock,
                return_value="# README\nHello",
            ),
            patch.object(
                github_client, "list_docs_directory", new_callable=AsyncMock, return_value=[]
            ),
            patch.object(
                github_client,
                "fetch_homepage_url",
                new_callable=AsyncMock,
                return_value="https://docs.example.com",
            ),
            patch(
                "context7_local.scraper.scrape_docs_site",
                new_callable=AsyncMock,
                return_value={"index.md": "# Welcome\nScraped content"},
            ),
        ):
            result = await query_docs("/owner/repo", "welcome")
            assert "Welcome" in result or "Scraped content" in result

    @pytest.mark.asyncio
    async def test_skips_github_homepage(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setenv("CACHE_DIR", str(tmp_path))

        with (
            patch.object(
                github_client,
                "fetch_readme",
                new_callable=AsyncMock,
                return_value="# README\nHello",
            ),
            patch.object(
                github_client, "list_docs_directory", new_callable=AsyncMock, return_value=[]
            ),
            patch.object(
                github_client,
                "fetch_homepage_url",
                new_callable=AsyncMock,
                return_value="https://github.com/owner/repo",
            ),
            patch(
                "context7_local.scraper.scrape_docs_site",
                new_callable=AsyncMock,
            ) as mock_scrape,
        ):
            await query_docs("/owner/repo", "hello")
            mock_scrape.assert_not_called()
